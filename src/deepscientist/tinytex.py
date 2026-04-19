from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .shared import utf8_text_subprocess_kwargs, which

_TINYTEX_DOC_URL = "https://yihui.org/tinytex/"
_TINYTEX_CHINESE_DOC_URL = "https://yihui.org/tinytex/cn/"
_TINYTEX_UNIX_INSTALLER_URL = "https://tinytex.yihui.org/install-bin-unix.sh"
_TINYTEX_WINDOWS_INSTALLER_URL = "https://tinytex.yihui.org/install-bin-windows.bat"


def _unique_paths(paths: list[Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path.expanduser())
    return ordered


def _home_tools_root(home: Path | None) -> Path | None:
    if home is None:
        return None
    return home / "runtime" / "tools"


def tinytex_root_candidates(home: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("DEEPSCIENTIST_TINYTEX_ROOT", "DS_TINYTEX_ROOT", "TINYTEX_DIR"):
        raw = str(os.environ.get(env_name) or "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())

    tools_root = _home_tools_root(home)
    if tools_root is not None:
        candidates.append(tools_root / "TinyTeX")

    if sys.platform.startswith("darwin"):
        candidates.append(Path.home() / "Library" / "TinyTeX")
    elif sys.platform.startswith("win"):
        appdata_root = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        candidates.append(appdata_root / "TinyTeX")
    else:
        candidates.append(Path.home() / ".TinyTeX")

    return _unique_paths(candidates)


def _binary_names(binary: str) -> list[str]:
    normalized = str(binary or "").strip()
    if not normalized:
        return []
    if sys.platform.startswith("win"):
        return [f"{normalized}.exe", f"{normalized}.bat", f"{normalized}.cmd", normalized]
    return [normalized]


def _tinytex_bin_dirs(root: Path) -> list[Path]:
    bin_root = root / "bin"
    if not bin_root.exists():
        return []
    child_dirs = sorted(path for path in bin_root.iterdir() if path.is_dir())
    return child_dirs or ([bin_root] if bin_root.is_dir() else [])


def resolve_tinytex_binary(binary: str, home: Path | None = None) -> dict[str, Any]:
    normalized = str(binary or "").strip()
    if not normalized:
        return {"binary": None, "path": None, "source": None, "root": None, "bin_dir": None}
    for root in tinytex_root_candidates(home):
        for bin_dir in _tinytex_bin_dirs(root):
            for name in _binary_names(normalized):
                candidate = bin_dir / name
                if candidate.exists():
                    return {
                        "binary": normalized,
                        "path": str(candidate),
                        "source": "tinytex",
                        "root": str(root),
                        "bin_dir": str(bin_dir),
                    }
    return {
        "binary": normalized,
        "path": None,
        "source": None,
        "root": None,
        "bin_dir": None,
    }


def resolve_latex_binary(binary: str, home: Path | None = None) -> dict[str, Any]:
    tinytex_match = resolve_tinytex_binary(binary, home)
    if tinytex_match.get("path"):
        return tinytex_match
    system_path = which(binary)
    return {
        "binary": str(binary or "").strip() or None,
        "path": system_path,
        "source": "path" if system_path else None,
        "root": None,
        "bin_dir": None,
    }


def inspect_latex_runtime(home: Path | None = None) -> dict[str, Any]:
    pdflatex = resolve_latex_binary("pdflatex", home)
    xelatex = resolve_latex_binary("xelatex", home)
    lualatex = resolve_latex_binary("lualatex", home)
    bibtex = resolve_latex_binary("bibtex", home)
    tinytex = resolve_tinytex_binary("pdflatex", home)

    guidance: list[str] = []
    warnings: list[str] = []
    available = bool(pdflatex.get("path"))
    bibtex_available = bool(bibtex.get("path"))

    if not available:
        warnings.append("Local PDF compilation is optional and currently unavailable because `pdflatex` is missing.")
        guidance.append("Install a lightweight TinyTeX runtime with `ds latex install-runtime`.")
        guidance.append(
            "Or install a system LaTeX distribution that provides `pdflatex` and `bibtex`."
        )
    elif not bibtex_available:
        warnings.append("`pdflatex` is available, but `bibtex` is missing. Bibliography builds may fail.")
        guidance.append("Install TinyTeX with `ds latex install-runtime` or add `bibtex` to your system LaTeX distribution.")

    summary = "A local `pdflatex` runtime is available for paper builds." if available else "Local `pdflatex` is not available."
    if pdflatex.get("source") == "tinytex":
        summary = "A TinyTeX-managed `pdflatex` runtime is available for paper builds."

    return {
        "ok": available,
        "summary": summary,
        "warnings": warnings,
        "guidance": guidance,
        "tinytex": {
            "installed": bool(tinytex.get("path")),
            "root": tinytex.get("root"),
            "bin_dir": tinytex.get("bin_dir"),
            "doc_url": _TINYTEX_DOC_URL,
            "doc_url_zh": _TINYTEX_CHINESE_DOC_URL,
            "installer_url": _TINYTEX_WINDOWS_INSTALLER_URL if sys.platform.startswith("win") else _TINYTEX_UNIX_INSTALLER_URL,
        },
        "binaries": {
            "pdflatex": pdflatex,
            "xelatex": xelatex,
            "lualatex": lualatex,
            "bibtex": bibtex,
        },
    }


def _download_installer(url: str) -> tuple[bool, str]:
    request = Request(url, headers={"User-Agent": "DeepScientist TinyTeX bootstrap"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            payload = response.read()
    except (OSError, TimeoutError, URLError) as exc:
        return False, str(exc)
    suffix = ".bat" if url.endswith(".bat") else ".sh"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        return True, handle.name


def install_tinytex(home: Path | None = None) -> dict[str, Any]:
    current = inspect_latex_runtime(home)
    if current.get("tinytex", {}).get("installed"):
        return {
            "ok": True,
            "changed": False,
            "summary": "TinyTeX-managed pdflatex is already installed.",
            "runtime": current,
        }

    if sys.platform.startswith("win"):
        ok, installer_path_or_error = _download_installer(_TINYTEX_WINDOWS_INSTALLER_URL)
        if not ok:
            return {
                "ok": False,
                "changed": False,
                "summary": "Failed to download the TinyTeX Windows installer.",
                "errors": [installer_path_or_error],
                "guidance": [f"Open {_TINYTEX_DOC_URL} for the official manual install instructions."],
            }
        command = ["cmd", "/c", installer_path_or_error]
    else:
        if not which("sh"):
            return {
                "ok": False,
                "changed": False,
                "summary": "TinyTeX installation requires `/bin/sh` or a compatible shell.",
                "errors": ["`sh` is not available on PATH."],
                "guidance": [f"Install TinyTeX manually from {_TINYTEX_DOC_URL}."],
            }
        if not which("perl"):
            return {
                "ok": False,
                "changed": False,
                "summary": "TinyTeX installation requires Perl on Linux and macOS.",
                "errors": ["`perl` is not available on PATH."],
                "guidance": [
                    "Install Perl first, then rerun `ds latex install-runtime`.",
                    f"Official docs: {_TINYTEX_DOC_URL}",
                ],
            }
        ok, installer_path_or_error = _download_installer(_TINYTEX_UNIX_INSTALLER_URL)
        if not ok:
            return {
                "ok": False,
                "changed": False,
                "summary": "Failed to download the TinyTeX installer.",
                "errors": [installer_path_or_error],
                "guidance": [f"Open {_TINYTEX_DOC_URL} for the official manual install instructions."],
            }
        command = ["sh", installer_path_or_error]

    installer_path = Path(installer_path_or_error)
    try:
        result = subprocess.run(command, capture_output=True, check=False, **utf8_text_subprocess_kwargs())
    finally:
        installer_path.unlink(missing_ok=True)
    refreshed = inspect_latex_runtime(home)

    stdout_tail = "\n".join(str(result.stdout or "").splitlines()[-40:])
    stderr_tail = "\n".join(str(result.stderr or "").splitlines()[-40:])
    if result.returncode != 0:
        return {
            "ok": False,
            "changed": False,
            "summary": "TinyTeX installer exited with a non-zero status.",
            "errors": [stderr_tail or stdout_tail or f"Installer exited with status {result.returncode}."],
            "guidance": [
                "Retry `ds latex install-runtime` after checking network connectivity.",
                f"Official docs: {_TINYTEX_DOC_URL}",
            ],
            "exit_code": result.returncode,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "runtime": refreshed,
        }

    if not refreshed.get("tinytex", {}).get("installed"):
        return {
            "ok": False,
            "changed": False,
            "summary": "TinyTeX installer finished, but DeepScientist could not find the managed pdflatex runtime afterward.",
            "errors": ["Installation did not expose a discoverable TinyTeX `pdflatex` binary."],
            "guidance": [
                "Open the TinyTeX documentation and verify the install location.",
                f"Official docs: {_TINYTEX_DOC_URL}",
            ],
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "runtime": refreshed,
        }

    return {
        "ok": True,
        "changed": True,
        "summary": "TinyTeX-managed pdflatex is ready.",
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "runtime": refreshed,
    }
