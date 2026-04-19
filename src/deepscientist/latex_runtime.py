from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from .runtime_tools import RuntimeToolService
from .shared import ensure_dir, generate_id, resolve_within, utc_now, utf8_text_subprocess_kwargs, write_json

_QUEST_DIR_PREFIX = "quest-dir::"
_QUEST_FILE_PREFIX = "quest-file::"
_VALID_COMPILERS = {"pdflatex", "xelatex", "lualatex"}
_TRANSIENT_SOURCE_SUFFIXES = {
    ".aux",
    ".bbl",
    ".bcf",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".lof",
    ".log",
    ".lot",
    ".nav",
    ".out",
    ".run.xml",
    ".snm",
    ".synctex.gz",
    ".toc",
    ".vrb",
}


def _encode_relative(value: str) -> str:
    return quote(value, safe="")


def _decode_relative(value: str) -> str:
    return unquote(str(value or "")).strip().lstrip("/")


def _encode_quest_dir_id(project_id: str, relative_path: str) -> str:
    return f"{_QUEST_DIR_PREFIX}{project_id}::{_encode_relative(relative_path)}"


def _encode_quest_file_id(project_id: str, relative_path: str) -> str:
    document_id = f"path::{relative_path}"
    return (
        f"{_QUEST_FILE_PREFIX}{project_id}"
        f"::{_encode_relative(document_id)}"
        f"::{_encode_relative(relative_path)}"
    )


def _sanitize_folder_key(relative_path: str) -> str:
    normalized = str(relative_path or "").strip().replace("\\", "/")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower() or "latex"
    checksum = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned[:48]}-{checksum}"


def _parse_file_line_issues(log_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    log_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_source = None
    for raw_line in str(log_text or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        file_line_match = re.match(r"^(?P<file>.+?):(?P<line>\d+):\s(?P<message>.+)$", line)
        if file_line_match:
            current_source = file_line_match.group("file").strip()
            message = file_line_match.group("message").strip()
            lowered = message.lower()
            severity = "warning" if "warning" in lowered else "error"
            item = {
                "severity": severity,
                "file": current_source,
                "line": int(file_line_match.group("line")),
                "message": message,
                "raw": line,
            }
            identity = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if identity not in seen:
                seen.add(identity)
                log_items.append(item)
                if severity == "error":
                    errors.append(
                        {
                            "path": item["file"],
                            "line": item["line"],
                            "message": item["message"],
                            "severity": item["severity"],
                        }
                    )
            continue
        warning_match = re.match(r"^(?:LaTeX|Package .*?) Warning:\s(?P<message>.+)$", line)
        if warning_match:
            item = {
                "severity": "warning",
                "file": current_source,
                "line": None,
                "message": warning_match.group("message").strip(),
                "raw": line,
            }
            identity = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if identity not in seen:
                seen.add(identity)
                log_items.append(item)
            continue
        error_match = re.match(r"^!\s(?P<message>.+)$", line)
        if error_match:
            item = {
                "severity": "error",
                "file": current_source,
                "line": None,
                "message": error_match.group("message").strip(),
                "raw": line,
            }
            identity = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if identity not in seen:
                seen.add(identity)
                log_items.append(item)
                errors.append(
                    {
                        "path": item["file"],
                        "line": item["line"],
                        "message": item["message"],
                        "severity": item["severity"],
                    }
                )
    return errors, log_items


class QuestLatexService:
    def __init__(self, quest_service: Any) -> None:
        self.quest_service = quest_service

    def _quest_root(self, project_id: str) -> Path:
        return self.quest_service._quest_root(project_id)

    def _workspace_root(self, project_id: str) -> Path:
        quest_root = self._quest_root(project_id)
        return self.quest_service.active_workspace_root(quest_root)

    @staticmethod
    def _parse_folder_relative(project_id: str, folder_id: str) -> str:
        raw = str(folder_id or "").strip()
        if not raw:
            raise ValueError("`folder_id` is required.")
        if raw.startswith(_QUEST_DIR_PREFIX):
            payload = raw[len(_QUEST_DIR_PREFIX) :]
            owner, _, encoded_path = payload.partition("::")
            if owner and owner != project_id:
                raise ValueError("Folder does not belong to the target quest.")
            relative = _decode_relative(encoded_path)
            if not relative:
                raise ValueError("Folder path is empty.")
            return relative
        return _decode_relative(raw)

    @staticmethod
    def _parse_file_relative(project_id: str, file_id: str | None) -> str | None:
        raw = str(file_id or "").strip()
        if not raw:
            return None
        if raw.startswith(_QUEST_FILE_PREFIX):
            payload = raw[len(_QUEST_FILE_PREFIX) :]
            owner, _, remainder = payload.partition("::")
            if owner and owner != project_id:
                raise ValueError("File does not belong to the target quest.")
            encoded_document_id, _, encoded_path = remainder.partition("::")
            relative = _decode_relative(encoded_path)
            if relative:
                return relative
            document_id = _decode_relative(encoded_document_id)
            if document_id.startswith("path::"):
                return document_id.split("::", 1)[1].lstrip("/") or None
            if document_id.startswith("questpath::"):
                return document_id.split("::", 1)[1].lstrip("/") or None
            return None
        return _decode_relative(raw)

    def _resolve_folder_path(self, project_id: str, folder_id: str) -> tuple[Path, str]:
        relative = self._parse_folder_relative(project_id, folder_id)
        quest_root = self._quest_root(project_id)
        workspace_root = self._workspace_root(project_id)
        candidates: list[Path] = []
        for root in [workspace_root, quest_root]:
            try:
                candidates.append(resolve_within(root, relative))
            except ValueError:
                continue
        for candidate in candidates:
            if candidate.exists():
                if not candidate.is_dir():
                    raise FileNotFoundError(f"LaTeX folder `{relative}` is not a directory.")
                return candidate, relative
        fallback = candidates[0] if candidates else resolve_within(workspace_root, relative)
        if not fallback.exists():
            raise FileNotFoundError(f"LaTeX folder `{relative}` does not exist.")
        if not fallback.is_dir():
            raise FileNotFoundError(f"LaTeX folder `{relative}` is not a directory.")
        return fallback, relative

    def _resolve_main_tex(self, project_id: str, folder_path: Path, folder_relative: str, main_file_id: str | None) -> tuple[Path, str]:
        relative = self._parse_file_relative(project_id, main_file_id)
        if relative:
            if relative == folder_relative:
                raise ValueError("`main_file_id` must point to a file, not the folder.")
            path = resolve_within(self._workspace_root(project_id), relative)
            if not path.exists():
                path = resolve_within(self._quest_root(project_id), relative)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Main TeX file `{relative}` does not exist.")
            if folder_path not in path.resolve().parents:
                raise ValueError("`main_file_id` must belong to the selected LaTeX folder.")
            return path, relative
        preferred = folder_path / "main.tex"
        if preferred.exists():
            return preferred, f"{folder_relative.rstrip('/')}/main.tex"
        tex_candidates = sorted(folder_path.glob("*.tex"))
        if not tex_candidates:
            raise FileNotFoundError("No `.tex` file found in the LaTeX folder.")
        chosen = tex_candidates[0]
        return chosen, f"{folder_relative.rstrip('/')}/{chosen.name}"

    def _folder_build_root(self, project_id: str, folder_relative: str) -> Path:
        quest_root = self._quest_root(project_id)
        return ensure_dir(quest_root / ".ds" / "latex_builds" / _sanitize_folder_key(folder_relative))

    def _build_record_path(self, project_id: str, folder_relative: str, build_id: str) -> Path:
        return self._folder_build_root(project_id, folder_relative) / "builds" / build_id / "build.json"

    def _list_build_records(self, project_id: str, folder_relative: str) -> list[dict[str, Any]]:
        builds_root = self._folder_build_root(project_id, folder_relative) / "builds"
        if not builds_root.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(builds_root.glob("*/build.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def _write_compile_report(self, project_id: str, folder_relative: str, build: dict[str, Any]) -> None:
        if not folder_relative.startswith("paper/"):
            return
        quest_root = self._quest_root(project_id)
        report_path = quest_root / "paper" / "build" / "compile_report.json"
        existing = {}
        if report_path.exists():
            try:
                existing = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        payload = {
            **existing,
            "updated_at": utc_now(),
            "build_id": build.get("build_id"),
            "folder_id": build.get("folder_id"),
            "folder_path": build.get("folder_path"),
            "main_file_path": build.get("main_file_path"),
            "compiler": build.get("compiler"),
            "status": build.get("status"),
            "exit_code": build.get("exit_code"),
            "pdf_ready": build.get("pdf_ready"),
            "log_ready": build.get("log_ready"),
            "pdf_path": build.get("output_pdf_path"),
            "errors": build.get("errors") or [],
            "log_items": build.get("log_items") or [],
        }
        write_json(report_path, payload)

    def init_project(
        self,
        project_id: str,
        *,
        name: str,
        parent_id: str | None = None,
        template: str | None = None,
        compiler: str | None = None,
    ) -> dict[str, Any]:
        quest_root = self._quest_root(project_id)
        workspace_root = self._workspace_root(project_id)
        parent_relative = self._parse_folder_relative(project_id, parent_id) if parent_id else ""
        parent_path = resolve_within(workspace_root, parent_relative) if parent_relative else workspace_root
        if not parent_path.exists():
            raise FileNotFoundError("Parent folder does not exist.")
        folder_name = str(name or "").strip()
        if not folder_name:
            raise ValueError("`name` is required.")
        folder_path = parent_path / folder_name
        if folder_path.exists():
            raise FileExistsError(f"`{folder_name}` already exists.")
        ensure_dir(folder_path)
        title = folder_name
        main_tex = folder_path / "main.tex"
        refs_bib = folder_path / "refs.bib"
        compiler_name = str(compiler or "pdflatex").strip().lower()
        selected_template = str(template or "article").strip().lower() or "article"
        if compiler_name not in _VALID_COMPILERS:
            compiler_name = "pdflatex"
        if selected_template == "article":
            main_tex.write_text(
                "\n".join(
                    [
                        r"\documentclass{article}",
                        r"\usepackage[utf8]{inputenc}",
                        r"\usepackage{hyperref}",
                        r"\title{" + title.replace("{", "").replace("}", "") + "}",
                        r"\author{DeepScientist}",
                        r"\date{\today}",
                        r"",
                        r"\begin{document}",
                        r"\maketitle",
                        r"",
                        r"\begin{abstract}",
                        r"Write the abstract here.",
                        r"\end{abstract}",
                        r"",
                        r"\section{Introduction}",
                        r"Start writing.",
                        r"",
                        r"\bibliographystyle{plain}",
                        r"\bibliography{refs}",
                        r"",
                        r"\end{document}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        else:
            main_tex.write_text(
                "\n".join(
                    [
                        r"\documentclass{article}",
                        r"\begin{document}",
                        title,
                        r"\end{document}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        refs_bib.write_text("% Add BibTeX entries here.\n", encoding="utf-8")
        relative_folder = folder_path.relative_to(workspace_root).as_posix()
        relative_main = main_tex.relative_to(workspace_root).as_posix()
        return {
            "folder_id": _encode_quest_dir_id(project_id, relative_folder),
            "main_file_id": _encode_quest_file_id(project_id, relative_main),
            "created": [
                {
                    "id": _encode_quest_dir_id(project_id, relative_folder),
                    "name": folder_name,
                    "type": "folder",
                },
                {
                    "id": _encode_quest_file_id(project_id, relative_main),
                    "name": "main.tex",
                    "type": "file",
                },
                {
                    "id": _encode_quest_file_id(project_id, refs_bib.relative_to(workspace_root).as_posix()),
                    "name": "refs.bib",
                    "type": "file",
                },
            ],
            "compiler": compiler_name,
            "quest_root": str(quest_root),
        }

    def compile(
        self,
        project_id: str,
        folder_id: str,
        *,
        compiler: str | None = None,
        main_file_id: str | None = None,
        stop_on_first_error: bool | None = None,
        auto: bool | None = None,
    ) -> dict[str, Any]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        main_tex_path, main_tex_relative = self._resolve_main_tex(project_id, folder_path, folder_relative, main_file_id)
        build_id = generate_id("latex")
        build_dir = ensure_dir(self._build_record_path(project_id, folder_relative, build_id).parent)
        log_path = build_dir / "compile.log"
        pdf_copy_path = build_dir / f"{main_tex_path.stem}.pdf"
        metadata_path = build_dir / "build.json"
        selected_compiler = str(compiler or "pdflatex").strip().lower() or "pdflatex"
        if selected_compiler not in _VALID_COMPILERS:
            raise ValueError("`compiler` must be one of: pdflatex, xelatex, lualatex.")

        build: dict[str, Any] = {
            "build_id": build_id,
            "project_id": project_id,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "main_file_id": main_file_id,
            "main_file_path": main_tex_relative,
            "compiler": selected_compiler,
            "compiler_binary": None,
            "compiler_source": None,
            "status": "running",
            "created_at": utc_now(),
            "started_at": utc_now(),
            "finished_at": None,
            "exit_code": None,
            "error_message": None,
            "pdf_ready": False,
            "log_ready": False,
            "errors": [],
            "log_items": [],
            "output_pdf_path": None,
            "log_path": None,
            "bibtex_binary": None,
            "auto": bool(auto),
            "stop_on_first_error": bool(stop_on_first_error),
        }
        write_json(metadata_path, build)

        runtime_tools = RuntimeToolService(self.quest_service.home)
        compiler_match = runtime_tools.resolve_binary(selected_compiler, preferred_tools=("tinytex",))
        compiler_bin = compiler_match.get("path")
        build["compiler_binary"] = compiler_bin
        build["compiler_source"] = compiler_match.get("source")
        if not compiler_bin:
            build.update(
                {
                    "status": "error",
                    "finished_at": utc_now(),
                    "error_message": (
                        f"`{selected_compiler}` is not installed on this machine. "
                        "Install TinyTeX with `ds latex install-runtime` or install a system LaTeX distribution."
                    ),
                    "log_ready": True,
                    "log_path": str(log_path),
                }
            )
            log_path.write_text(build["error_message"] + "\n", encoding="utf-8")
            write_json(metadata_path, build)
            self._write_compile_report(project_id, folder_relative, build)
            return build

        bibtex_match = runtime_tools.resolve_binary("bibtex", preferred_tools=("tinytex",))
        bibtex_bin = bibtex_match.get("path")
        build["bibtex_binary"] = bibtex_bin
        command = [
            compiler_bin,
            "-interaction=nonstopmode",
            "-file-line-error",
            *([] if stop_on_first_error is False else ["-halt-on-error"]),
            main_tex_path.name,
        ]
        log_segments: list[str] = []
        exit_code = 0

        def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
            header = f"$ {' '.join(args)}\n"
            body = (result.stdout or "") + (result.stderr or "")
            log_segments.append(header + body + ("\n" if body and not body.endswith("\n") else ""))
            return result

        first_result = _run(command, folder_path)
        exit_code = first_result.returncode

        if exit_code == 0:
            aux_path = folder_path / f"{main_tex_path.stem}.aux"
            has_bib_inputs = any(folder_path.glob("*.bib"))
            if bibtex_bin and aux_path.exists() and has_bib_inputs:
                bibtex_result = _run([bibtex_bin, main_tex_path.stem], folder_path)
                exit_code = bibtex_result.returncode
                if exit_code == 0:
                    second_result = _run(command, folder_path)
                    exit_code = second_result.returncode
                if exit_code == 0:
                    third_result = _run(command, folder_path)
                    exit_code = third_result.returncode

        compile_log_text = "".join(log_segments)
        generated_log_path = folder_path / f"{main_tex_path.stem}.log"
        if generated_log_path.exists():
            try:
                compile_log_text += (
                    "\n[latex log]\n" + generated_log_path.read_text(encoding="utf-8", errors="ignore")
                )
            except OSError:
                pass
        log_path.write_text(compile_log_text, encoding="utf-8")
        errors, log_items = _parse_file_line_issues(compile_log_text)

        generated_pdf = folder_path / f"{main_tex_path.stem}.pdf"
        pdf_ready = exit_code == 0 and generated_pdf.exists()
        if pdf_ready:
            shutil.copy2(generated_pdf, pdf_copy_path)

        build.update(
            {
                "status": "success" if pdf_ready else "error",
                "finished_at": utc_now(),
                "exit_code": exit_code,
                "error_message": None if pdf_ready else (errors[0]["message"] if errors else "LaTeX compilation failed."),
                "pdf_ready": pdf_ready,
                "log_ready": True,
                "errors": errors,
                "log_items": log_items,
                "output_pdf_path": str(pdf_copy_path) if pdf_ready else None,
                "log_path": str(log_path),
            }
        )
        write_json(metadata_path, build)
        self._write_compile_report(project_id, folder_relative, build)
        return build

    def list_builds(self, project_id: str, folder_id: str, limit: int = 10) -> list[dict[str, Any]]:
        folder_relative = self._parse_folder_relative(project_id, folder_id)
        resolved_limit = max(1, min(int(limit), 50))
        return self._list_build_records(project_id, folder_relative)[:resolved_limit]

    def get_build(self, project_id: str, folder_id: str, build_id: str) -> dict[str, Any]:
        folder_relative = self._parse_folder_relative(project_id, folder_id)
        metadata_path = self._build_record_path(project_id, folder_relative, build_id)
        if not metadata_path.exists():
            raise FileNotFoundError(f"Unknown LaTeX build `{build_id}`.")
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileNotFoundError(f"LaTeX build `{build_id}` is unreadable.") from exc
        if not isinstance(payload, dict):
            raise FileNotFoundError(f"LaTeX build `{build_id}` is invalid.")
        return payload

    def get_build_pdf(self, project_id: str, folder_id: str, build_id: str) -> tuple[bytes, str]:
        build = self.get_build(project_id, folder_id, build_id)
        output_pdf_path = str(build.get("output_pdf_path") or "").strip()
        if not output_pdf_path:
            raise FileNotFoundError("PDF output is not available for this build.")
        pdf_path = Path(output_pdf_path)
        if not pdf_path.exists() or not pdf_path.is_file():
            raise FileNotFoundError("PDF output is missing.")
        return pdf_path.read_bytes(), pdf_path.name

    def get_build_log_text(self, project_id: str, folder_id: str, build_id: str) -> str:
        build = self.get_build(project_id, folder_id, build_id)
        log_path = str(build.get("log_path") or "").strip()
        if not log_path:
            raise FileNotFoundError("Compile log is not available for this build.")
        path = Path(log_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Compile log is missing.")
        return path.read_text(encoding="utf-8", errors="ignore")

    def create_sources_archive(self, project_id: str, folder_id: str) -> tuple[bytes, str]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        archive_name = f"{Path(folder_relative).name or 'latex-sources'}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder_path.rglob("*")):
                if not path.is_file():
                    continue
                if any(part.startswith(".git") for part in path.relative_to(folder_path).parts):
                    continue
                suffix = path.suffix.lower()
                if suffix in _TRANSIENT_SOURCE_SUFFIXES:
                    continue
                archive.write(path, arcname=path.relative_to(folder_path).as_posix())
        return buffer.getvalue(), archive_name
