from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import unicodedata
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from .file_lock import advisory_file_lock
from .gitops import compare_refs, head_commit
from .runtime_tools import RuntimeToolService
from .shared import (
    ensure_dir,
    generate_id,
    read_json,
    resolve_within,
    run_command,
    run_command_bytes,
    utc_now,
    utf8_text_subprocess_kwargs,
    write_json,
)

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
_LATEX_EDITABLE_SUFFIXES = {
    ".tex",
    ".bib",
    ".cls",
    ".sty",
    ".bst",
    ".bbx",
    ".cbx",
}
_LATEX_RESOURCE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".eps",
}
_LATEX_MANIFEST_SUFFIXES = _LATEX_EDITABLE_SUFFIXES | _LATEX_RESOURCE_SUFFIXES
_LATEX_INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_LATEX_BIB_RE = re.compile(r"\\(?:bibliography|addbibresource)\{([^}]+)\}")
_LATEX_VERSION_TRAILER_PREFIX = "DeepScientist-Latex-"
_LATEX_VERSION_TRAILERS = {
    "Version",
    "Folder",
    "Main",
    "Source",
    "Author",
    "Build",
    "Label",
    "Description",
    "Base",
    "Reason",
    "Hidden",
}
_LATEX_AUTO_VERSION_POLICY_VERSION = "auto-v1"
_LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS = 5 * 60
_LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS = 15 * 60
_LATEX_AUTO_VERSION_SIGNIFICANT_LINES = 30
_LATEX_AUTO_VERSION_SIGNIFICANT_CHARS = 1500
_LATEX_AUTO_VERSION_SIGNIFICANT_FILES = 2


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


def _parse_synctex_records(output: str) -> dict[str, str]:
    records: dict[str, str] = {}
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in {"output", "input", "line", "column", "offset", "context"}:
            records[key] = value.strip()
    return records


def _normalize_latex_match_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = (
        text.replace("ﬁ", "fi")
        .replace("ﬂ", "fl")
        .replace("ﬀ", "ff")
        .replace("ﬃ", "ffi")
        .replace("ﬄ", "ffl")
    )
    text = text.casefold()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"}).strip("_-")


def _latex_token_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "-"}


_LATEX_COMMENT_BEGIN_RE = re.compile(r"\\begin\s*\{\s*comment\s*\}")
_LATEX_COMMENT_END_RE = re.compile(r"\\end\s*\{\s*comment\s*\}")
_LATEX_MACRO_DEFINITION_LINE_RE = re.compile(r"\\(?:newcommand|renewcommand|providecommand|def)\b")
_LATEX_SOURCE_SYNTAX_COMMANDS = {
    "addbibresource",
    "begin",
    "bibliography",
    "bibliographystyle",
    "documentclass",
    "end",
    "graphicspath",
    "include",
    "input",
    "label",
    "usepackage",
}


def _unescaped_percent_index(value: str, start: int = 0) -> int | None:
    index = max(0, int(start or 0))
    while True:
        found = value.find("%", index)
        if found < 0:
            return None
        backslashes = 0
        cursor = found - 1
        while cursor >= 0 and value[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return found
        index = found + 1


def _latex_visible_segments_for_line(raw: str, in_comment_environment: bool) -> tuple[list[tuple[int, str]], bool]:
    segments: list[tuple[int, str]] = []
    cursor = 0
    source = str(raw or "")
    in_comment = bool(in_comment_environment)
    while cursor < len(source):
        if in_comment:
            end_match = _LATEX_COMMENT_END_RE.search(source, cursor)
            if not end_match:
                return segments, True
            cursor = end_match.end()
            in_comment = False
            continue

        percent_index = _unescaped_percent_index(source, cursor)
        begin_match = _LATEX_COMMENT_BEGIN_RE.search(source, cursor)
        begin_index = begin_match.start() if begin_match else None
        stop_candidates = [
            candidate for candidate in [percent_index, begin_index] if candidate is not None
        ]
        stop = min(stop_candidates) if stop_candidates else len(source)
        if stop > cursor:
            segments.append((cursor, source[cursor:stop]))
        if percent_index is not None and percent_index == stop:
            return segments, False
        if begin_match is not None and begin_match.start() == stop:
            cursor = begin_match.end()
            in_comment = True
            continue
        break
    return segments, in_comment


def _latex_visible_line_max_column(source_text: str, line: int) -> int:
    lines = str(source_text or "").splitlines()
    if not lines:
        return 1
    target = min(max(1, int(line or 1)), len(lines))
    in_comment = False
    visible_end = 0
    for line_number, raw in enumerate(lines, start=1):
        segments, in_comment = _latex_visible_segments_for_line(raw, in_comment)
        if line_number == target:
            visible_end = max((start + len(text) for start, text in segments), default=0)
            break
    return visible_end + 1


def _line_col_for_offset(source_text: str, offset: int) -> tuple[int, int]:
    text = str(source_text or "")
    safe_offset = min(max(0, int(offset or 0)), len(text))
    line = text.count("\n", 0, safe_offset) + 1
    previous_newline = text.rfind("\n", 0, safe_offset)
    column = safe_offset + 1 if previous_newline < 0 else safe_offset - previous_newline
    return line, max(1, column)


def _latex_balanced_group_span(value: str, open_index: int) -> tuple[int, int, int] | None:
    source = str(value or "")
    if open_index < 0 or open_index >= len(source) or source[open_index] != "{":
        return None
    depth = 0
    index = open_index
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_index + 1, index, index + 1
        index += 1
    return None


def _skip_latex_spaces(value: str, index: int) -> int:
    source = str(value or "")
    cursor = max(0, int(index or 0))
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    return cursor


def _skip_latex_optional_group(value: str, index: int) -> int:
    source = str(value or "")
    cursor = _skip_latex_spaces(source, index)
    if cursor >= len(source) or source[cursor] != "[":
        return index
    depth = 0
    while cursor < len(source):
        char = source[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return index


def _skip_latex_command_arguments(value: str, index: int, *, max_required: int = 2) -> int:
    source = str(value or "")
    cursor = _skip_latex_optional_group(source, index)
    required = 0
    while required < max_required:
        cursor = _skip_latex_spaces(source, cursor)
        if cursor >= len(source) or source[cursor] != "{":
            break
        span = _latex_balanced_group_span(source, cursor)
        if not span:
            break
        cursor = span[2]
        required += 1
    return cursor


def _latex_approximate_text(value: str) -> str:
    source = str(value or "")

    def parse(cursor: int, end_char: str | None = None) -> tuple[str, int]:
        pieces: list[str] = []
        while cursor < len(source):
            char = source[cursor]
            if end_char and char == end_char:
                return "".join(pieces), cursor + 1
            if char == "\\":
                command_start = cursor
                cursor += 1
                if cursor < len(source) and (source[cursor].isalpha() or source[cursor] == "@"):
                    name_start = cursor
                    cursor += 1
                    while cursor < len(source) and (source[cursor].isalpha() or source[cursor] in {"@", "*"}):
                        cursor += 1
                    name = source[name_start:cursor].rstrip("*").lower()
                    cursor = _skip_latex_spaces(source, cursor)
                    if name in {"mbox", "mathrm", "mathtt", "textrm", "text", "textbf", "textit", "emph"}:
                        if cursor < len(source) and source[cursor] == "{":
                            inner, cursor = parse(cursor + 1, "}")
                            pieces.append(inner)
                        continue
                    if name == "textcolor":
                        if cursor < len(source) and source[cursor] == "{":
                            _, cursor = parse(cursor + 1, "}")
                            cursor = _skip_latex_spaces(source, cursor)
                        if cursor < len(source) and source[cursor] == "{":
                            inner, cursor = parse(cursor + 1, "}")
                            pieces.append(inner)
                        continue
                    if name in {"xspace", "protect"}:
                        continue
                    # Unknown commands are often formatting macros.  Keep their grouped
                    # argument visible by not consuming the following group.
                    if command_start + 1 == cursor:
                        pieces.append(source[command_start:cursor])
                    continue
                if cursor < len(source):
                    escaped = source[cursor]
                    cursor += 1
                    if escaped in {"%", "$", "&", "#", "_", "{", "}", "\\", "-"}:
                        pieces.append("-" if escaped == "-" else escaped)
                    continue
                continue
            if char == "{":
                inner, cursor = parse(cursor + 1, "}")
                pieces.append(inner)
                continue
            if char in {"}", "$"}:
                cursor += 1
                continue
            if char == "~":
                pieces.append(" ")
            else:
                pieces.append(char)
            cursor += 1
        return "".join(pieces), cursor

    return re.sub(r"\s+", " ", parse(0)[0]).strip()


def _latex_macro_aliases(source_text: str) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    source = str(source_text or "")
    # \newcommand{\name}{...}, \renewcommand{\name}[1]{...}, \providecommand...
    command_re = re.compile(r"\\(?:re)?newcommand\s*\{\s*\\([A-Za-z@]+)\s*\}|\\providecommand\s*\{\s*\\([A-Za-z@]+)\s*\}")
    for match in command_re.finditer(source):
        name = match.group(1) or match.group(2)
        cursor = match.end()
        cursor = _skip_latex_optional_group(source, cursor)
        cursor = _skip_latex_optional_group(source, cursor)
        cursor = _skip_latex_spaces(source, cursor)
        if cursor >= len(source) or source[cursor] != "{":
            continue
        span = _latex_balanced_group_span(source, cursor)
        if not span:
            continue
        expansion = source[span[0] : span[1]]
        plain = _latex_approximate_text(expansion)
        normalized_values = [
            _normalize_latex_match_text(plain),
            *[
                _normalize_latex_match_text(part)
                for part in re.split(r"\s+", plain)
                if part.strip()
            ],
        ]
        cleaned = [value for value in normalized_values if value]
        if cleaned:
            aliases.setdefault(name, [])
            for value in cleaned:
                if value not in aliases[name]:
                    aliases[name].append(value)
    return aliases


def _latex_source_tokens(
    source_text: str,
    *,
    min_line: int = 1,
    max_line: int | None = None,
    macro_aliases: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    lines = str(source_text or "").splitlines()
    lower_bound = max(1, int(min_line or 1))
    upper_bound = len(lines) if max_line is None else min(len(lines), max(1, int(max_line)))
    aliases = macro_aliases if macro_aliases is not None else _latex_macro_aliases(source_text)
    in_comment_environment = False
    for line_number in range(1, upper_bound + 1):
        raw = lines[line_number - 1] if 0 <= line_number - 1 < len(lines) else ""
        segments, in_comment_environment = _latex_visible_segments_for_line(raw, in_comment_environment)
        if line_number < lower_bound:
            continue
        for segment_start, segment in segments:
            if _LATEX_MACRO_DEFINITION_LINE_RE.search(segment):
                continue
            index = 0
            while index < len(segment):
                char = segment[index]
                if char == "\\":
                    # Do not match LaTeX command names such as \section or \textbf as PDF words.
                    if index + 1 < len(segment) and (segment[index + 1].isalpha() or segment[index + 1] == "@"):
                        command_start = index
                        index += 2
                        while index < len(segment) and (segment[index].isalpha() or segment[index] in {"@", "*"}):
                            index += 1
                        command_name = segment[command_start + 1 : index].rstrip("*")
                        command_name_lower = command_name.lower()
                        if command_name_lower in _LATEX_SOURCE_SYNTAX_COMMANDS:
                            index = _skip_latex_command_arguments(segment, index, max_required=2)
                            continue
                        command_aliases = aliases.get(command_name) or []
                        if command_aliases:
                            tokens.append(
                                {
                                    "text": "\\" + command_name,
                                    "normalized": command_aliases[0],
                                    "aliases": command_aliases,
                                    "line": line_number,
                                    "start_column": segment_start + command_start + 1,
                                    "end_column": segment_start + index + 1,
                                }
                            )
                        continue
                    # Escaped punctuation is layout/source syntax rather than a useful word target.
                    index += 2
                    continue
                if _latex_token_char(char):
                    start = index
                    index += 1
                    while index < len(segment) and _latex_token_char(segment[index]):
                        index += 1
                    text = segment[start:index].strip("_-")
                    if text:
                        normalized = _normalize_latex_match_text(text)
                        if normalized:
                            tokens.append(
                                {
                                    "text": text,
                                    "normalized": normalized,
                                    "line": line_number,
                                    "start_column": segment_start + start + 1,
                                    "end_column": segment_start + index + 1,
                                }
                            )
                    continue
                index += 1
    return tokens


def _line_max_column(source_text: str, line: int) -> int:
    lines = str(source_text or "").splitlines()
    if not lines:
        return 1
    line_index = min(max(1, int(line or 1)), len(lines)) - 1
    return len(lines[line_index]) + 1


def _token_normalized_values(token: dict[str, Any]) -> list[str]:
    values = [str(token.get("normalized") or "")]
    aliases = token.get("aliases")
    if isinstance(aliases, list):
        values.extend(str(alias or "") for alias in aliases)
    cleaned: list[str] = []
    for value in values:
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _line_start_selection(target_line: int, reason: str, *, confidence: float = 0.1, score: float = 30.0) -> dict[str, Any]:
    return {
        "start_line": target_line,
        "start_column": 1,
        "end_line": target_line,
        "end_column": 1,
        "text": "",
        "precision": "line_start",
        "confidence": confidence,
        "score": score,
        "reason": reason,
    }


def _is_low_information_pdf_word_for_selection(value: str) -> bool:
    normalized = _normalize_latex_match_text(value)
    if not normalized:
        return False
    # Tiny rendered words carry little lexical evidence by themselves.  They can
    # be legitimate source tokens ("2" in prose), but they are also commonly
    # produced by citations, footnotes, list labels, equation markers, and page
    # artifacts.  Do not reject them outright; require independent column or
    # surrounding-word support before selecting a concrete source token.
    return len(normalized) <= 1 or (normalized.isdigit() and len(normalized) <= 3)


def _latex_front_matter_render_kinds(source_text: str, target_line: int) -> set[str]:
    lines = str(source_text or "").splitlines()
    if not lines:
        return set()
    safe_line = min(max(1, int(target_line or 1)), len(lines))
    line = lines[safe_line - 1].casefold()
    kinds: set[str] = set()
    if re.search(r"\\maketitle\b", line):
        kinds.update({"title", "author", "date"})
    if re.search(r"\\ieeedisplaynontitleabstractindextext\b", line):
        kinds.update({"abstract", "keywords"})
    if re.search(r"\\ieeepeerreviewmaketitle\b", line):
        kinds.update({"abstract", "keywords"})
    if re.search(r"\\ieeetitleabstractindextext\b", line):
        kinds.update({"abstract", "keywords"})
    return kinds


def _latex_command_region(source_text: str, command: str, kind: str, priority: float) -> dict[str, Any] | None:
    source = str(source_text or "")
    match = re.search(rf"\\{re.escape(command)}\b", source)
    if not match:
        return None
    cursor = _skip_latex_optional_group(source, match.end())
    cursor = _skip_latex_spaces(source, cursor)
    if cursor >= len(source) or source[cursor] != "{":
        return None
    span = _latex_balanced_group_span(source, cursor)
    if not span:
        return None
    start_line, start_column = _line_col_for_offset(source, span[0])
    end_line, end_column = _line_col_for_offset(source, span[1])
    return {
        "kind": kind,
        "priority": priority,
        "start_line": start_line,
        "start_column": start_column,
        "end_line": end_line,
        "end_column": end_column,
    }


def _latex_environment_regions(source_text: str, environment: str, kind: str, priority: float) -> list[dict[str, Any]]:
    source = str(source_text or "")
    begin_re = re.compile(rf"\\begin\s*\{{\s*{re.escape(environment)}\s*\}}", re.IGNORECASE)
    end_re = re.compile(rf"\\end\s*\{{\s*{re.escape(environment)}\s*\}}", re.IGNORECASE)
    regions: list[dict[str, Any]] = []
    cursor = 0
    while True:
        begin_match = begin_re.search(source, cursor)
        if not begin_match:
            break
        end_match = end_re.search(source, begin_match.end())
        if not end_match:
            break
        start_line, start_column = _line_col_for_offset(source, begin_match.end())
        end_line, end_column = _line_col_for_offset(source, end_match.start())
        regions.append(
            {
                "kind": kind,
                "priority": priority,
                "start_line": start_line,
                "start_column": start_column,
                "end_line": end_line,
                "end_column": end_column,
            }
        )
        cursor = end_match.end()
    return regions


def _latex_front_matter_regions(source_text: str, target_line: int) -> list[dict[str, Any]]:
    render_kinds = _latex_front_matter_render_kinds(source_text, target_line)
    if not render_kinds:
        return []
    regions: list[dict[str, Any]] = []
    if "title" in render_kinds:
        for command, kind, priority in [
            ("title", "title", 220.0),
            ("author", "author", 160.0),
            ("date", "date", 100.0),
        ]:
            region = _latex_command_region(source_text, command, kind, priority)
            if region:
                regions.append(region)
        # Some classes render title and abstract together from \maketitle.
        for region in _latex_environment_regions(source_text, "abstract", "abstract", 90.0):
            regions.append(region)
    if "abstract" in render_kinds:
        regions.extend(_latex_environment_regions(source_text, "abstract", "abstract", 240.0))
    if "keywords" in render_kinds:
        regions.extend(_latex_environment_regions(source_text, "IEEEkeywords", "keywords", 160.0))
        regions.extend(_latex_environment_regions(source_text, "keywords", "keywords", 140.0))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, int, int]] = set()
    for region in regions:
        key = (
            str(region["kind"]),
            int(region["start_line"]),
            int(region["start_column"]),
            int(region["end_line"]),
            int(region["end_column"]),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(region)
    return deduped


def _tokens_for_latex_regions(source_text: str, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not regions:
        return []
    aliases = _latex_macro_aliases(source_text)
    all_tokens = _latex_source_tokens(
        source_text,
        min_line=min(int(region["start_line"]) for region in regions),
        max_line=max(int(region["end_line"]) for region in regions),
        macro_aliases=aliases,
    )
    tokens: list[dict[str, Any]] = []
    for token in all_tokens:
        token_line = int(token.get("line") or 0)
        token_start = int(token.get("start_column") or 0)
        token_end = int(token.get("end_column") or 0)
        for region in regions:
            start_line = int(region["start_line"])
            end_line = int(region["end_line"])
            if token_line < start_line or token_line > end_line:
                continue
            if token_line == start_line and token_end <= int(region["start_column"]):
                continue
            if token_line == end_line and token_start > int(region["end_column"]):
                continue
            enriched = dict(token)
            enriched["region_kind"] = region.get("kind")
            enriched["region_priority"] = float(region.get("priority") or 0)
            tokens.append(enriched)
            break
    return tokens


def _source_selection_for_synctex(
    source_text: str,
    *,
    line: int | None,
    column: int | None,
    pdf_word: str | None = None,
    pdf_context_words: list[str] | None = None,
    pdf_context_index: int | None = None,
) -> dict[str, Any]:
    lines = str(source_text or "").splitlines()
    max_line = max(1, len(lines))
    target_line = min(max(1, int(line or 1)), max_line)
    try:
        raw_column = int(column) if column is not None else None
    except (TypeError, ValueError):
        raw_column = None
    has_reliable_column = raw_column is not None and raw_column > 0
    target_column = raw_column if has_reliable_column else 1
    target_column = min(
        max(1, target_column),
        min(_line_max_column(source_text, target_line), _latex_visible_line_max_column(source_text, target_line)),
    )
    target_word = _normalize_latex_match_text(pdf_word)
    low_information_word = _is_low_information_pdf_word_for_selection(target_word)
    context_words = [
        normalized
        for normalized in (_normalize_latex_match_text(word) for word in (pdf_context_words or []))
        if normalized
    ]
    try:
        context_index = int(pdf_context_index) if pdf_context_index is not None else -1
    except (TypeError, ValueError):
        context_index = -1
    if context_index < 0 or context_index >= len(context_words):
        context_index = -1

    def context_score_for(token_list: list[dict[str, Any]], token_index: int) -> float:
        if context_index < 0 or not context_words:
            return 0.0
        score = 0.0
        for pdf_index, expected in enumerate(context_words):
            source_index = token_index + (pdf_index - context_index)
            if source_index < 0 or source_index >= len(token_list):
                continue
            actual_values = _token_normalized_values(token_list[source_index])
            if expected in actual_values:
                score += 36.0
            elif any(actual and expected and (actual in expected or expected in actual) for actual in actual_values):
                score += 14.0
        return min(score, 220.0)

    def token_match(token: dict[str, Any]) -> tuple[float, str] | None:
        if not target_word:
            return None
        normalized_values = _token_normalized_values(token)
        if target_word in normalized_values:
            return 1000.0, "exact_word"
        if len(target_word) <= 1:
            return None
        if any(value.startswith(target_word) or target_word.startswith(value) for value in normalized_values):
            return 650.0, "nearest_token"
        if any(target_word in value or value in target_word for value in normalized_values):
            return 500.0, "nearest_token"
        return None

    front_matter_tokens = _tokens_for_latex_regions(
        source_text,
        _latex_front_matter_regions(source_text, target_line),
    )
    front_matter_scored: list[tuple[float, dict[str, Any], str]] = []
    if target_word:
        for token_index, token in enumerate(front_matter_tokens):
            match = token_match(token)
            if not match:
                continue
            match_score, precision = match
            # SyncTeX points at the rendering macro (\maketitle / IEEE display
            # macro), not at the declaration.  Treat front-matter regions as a
            # virtual local neighborhood and let PDF text context disambiguate
            # abstract vs. keywords when repeated words exist.
            local_penalty = abs(int(token.get("line") or target_line) - target_line) * 2.0
            score = (
                match_score
                + context_score_for(front_matter_tokens, token_index)
                + float(token.get("region_priority") or 0)
                - local_penalty
            )
            front_matter_scored.append((score, token, precision))
    if front_matter_scored:
        score, token, precision = max(front_matter_scored, key=lambda item: item[0])
        if precision == "exact_word" or score >= 700:
            return {
                "start_line": int(token["line"]),
                "start_column": int(token["start_column"]),
                "end_line": int(token["line"]),
                "end_column": int(token["end_column"]),
                "text": token["text"],
                "precision": precision,
                "confidence": max(0.0, min(1.0, score / 1000.0)),
                "score": score,
                "strategy": "front_matter",
                "region": token.get("region_kind"),
            }

    window = 8 if target_word else 2
    macro_aliases = _latex_macro_aliases(source_text)
    tokens = _latex_source_tokens(
        source_text,
        min_line=max(1, target_line - window),
        max_line=min(max_line, target_line + window),
        macro_aliases=macro_aliases,
    )

    def token_distance(token: dict[str, Any]) -> float:
        line_distance = abs(int(token["line"]) - target_line)
        token_center = (int(token["start_column"]) + int(token["end_column"])) / 2
        column_distance = abs(token_center - target_column) if int(token["line"]) == target_line else 80
        return line_distance * 120 + column_distance

    def token_has_column_support(token: dict[str, Any]) -> bool:
        if not has_reliable_column or int(token.get("line") or 0) != target_line:
            return False
        token_start = int(token.get("start_column") or 1)
        token_end = int(token.get("end_column") or token_start)
        token_width = max(1, token_end - token_start)
        token_center = (token_start + token_end) / 2
        tolerance = max(3.0, min(12.0, token_width + 2.0))
        return (
            token_start - 2 <= target_column <= token_end + 2
            or abs(token_center - target_column) <= tolerance
        )

    scored: list[tuple[float, dict[str, Any], str, int, float, float]] = []
    if target_word:
        for token_index, token in enumerate(tokens):
            match = token_match(token)
            if not match:
                continue
            match_score, precision = match
            context_support = context_score_for(tokens, token_index)
            scored.append(
                (
                    match_score + context_support - token_distance(token),
                    token,
                    precision,
                    token_index,
                    context_support,
                    match_score,
                )
            )

    if not scored and low_information_word and not has_reliable_column:
        return _line_start_selection(
            target_line,
            "low_information_pdf_word_without_source_match",
            confidence=0.08,
            score=20.0,
        )

    if not scored and tokens:
        if target_word and len(target_word) <= 1:
            scored = []
        else:
            same_line = [token for token in tokens if int(token["line"]) == target_line]
            nearest_pool = same_line or tokens
            for token in nearest_pool:
                scored.append((250.0 - token_distance(token), token, "nearest_token", -1, 0.0, 0.0))

    if scored:
        score, token, precision, _token_index, context_support, _match_score = max(scored, key=lambda item: item[0])
        confidence = max(0.0, min(1.0, score / 1000.0))
        if low_information_word:
            column_support = token_has_column_support(token)
            context_support_is_strong = context_support >= 72.0
            exact_matches = [
                item
                for item in scored
                if item[2] == "exact_word" and target_word in _token_normalized_values(item[1])
            ]
            plausible_exact_matches = [
                item
                for item in exact_matches
                if item[0] >= score - 80.0
            ]
            has_independent_support = column_support or context_support_is_strong
            if precision != "exact_word" or not has_independent_support:
                return _line_start_selection(
                    target_line,
                    "low_information_pdf_word_insufficient_evidence",
                    confidence=0.1,
                    score=30.0,
                )
            if len(plausible_exact_matches) > 1 and not column_support and not context_support_is_strong:
                return _line_start_selection(
                    target_line,
                    "low_information_pdf_word_ambiguous_matches",
                    confidence=0.1,
                    score=30.0,
                )
        if precision == "exact_word" and confidence < 0.55:
            precision = "nearest_token"
        return {
            "start_line": int(token["line"]),
            "start_column": int(token["start_column"]),
            "end_line": int(token["line"]),
            "end_column": int(token["end_column"]),
            "text": token["text"],
            "precision": precision,
            "confidence": confidence,
            "score": score,
        }

    precision = "line_column" if column else "line_only"
    return {
        "start_line": target_line,
        "start_column": target_column,
        "end_line": target_line,
        "end_column": target_column,
        "text": "",
        "precision": precision,
        "confidence": 0.15 if column else 0.05,
        "score": 40.0 if column else 10.0,
    }


def _number_from_mapping(mapping: Any, keys: tuple[str, ...]) -> float | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    return None


def _coerce_pdf_word_bbox(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    left = _number_from_mapping(value, ("left", "x1", "x"))
    top = _number_from_mapping(value, ("top", "y1", "y"))
    right = _number_from_mapping(value, ("right", "x2"))
    bottom = _number_from_mapping(value, ("bottom", "y2"))
    width = _number_from_mapping(value, ("width", "w"))
    height = _number_from_mapping(value, ("height", "h"))
    if right is None and left is not None and width is not None:
        right = left + width
    if bottom is None and top is not None and height is not None:
        bottom = top + height
    if left is None or top is None or right is None or bottom is None:
        return None
    x1, x2 = sorted((left, right))
    y1, y2 = sorted((top, bottom))
    if x2 <= x1 or y2 <= y1:
        return None
    return {"left": x1, "top": y1, "right": x2, "bottom": y2}


def _coerce_pdf_word_center(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    x = _number_from_mapping(value, ("x", "left"))
    y = _number_from_mapping(value, ("y", "top"))
    if x is None or y is None:
        return None
    return x, y


def _synctex_sample_points(
    x: float,
    y: float,
    *,
    pdf_word_bbox: Any = None,
    pdf_word_center: Any = None,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    def add(kind: str, px: float | None, py: float | None, priority: float) -> None:
        if px is None or py is None or px < 0 or py < 0:
            return
        key = (round(px * 1000), round(py * 1000))
        if key in seen:
            return
        seen.add(key)
        points.append({"kind": kind, "x": float(px), "y": float(py), "priority": priority})

    bbox = _coerce_pdf_word_bbox(pdf_word_bbox)
    center = _coerce_pdf_word_center(pdf_word_center)
    if bbox:
        bbox_center = ((bbox["left"] + bbox["right"]) / 2, (bbox["top"] + bbox["bottom"]) / 2)
        center = center or bbox_center
    if center:
        add("word_center", center[0], center[1], 60.0)
    add("click", x, y, 45.0)
    if bbox:
        left, top, right, bottom = bbox["left"], bbox["top"], bbox["right"], bbox["bottom"]
        mid_x = (left + right) / 2
        mid_y = (top + bottom) / 2
        inset_x = max((right - left) * 0.18, 0.5)
        inset_y = max((bottom - top) * 0.18, 0.5)
        for kind, px, py, priority in [
            ("word_left", left + inset_x, mid_y, 38.0),
            ("word_right", right - inset_x, mid_y, 38.0),
            ("word_top", mid_x, top + inset_y, 32.0),
            ("word_bottom", mid_x, bottom - inset_y, 32.0),
            ("word_q1", left + (right - left) * 0.25, mid_y, 28.0),
            ("word_q3", left + (right - left) * 0.75, mid_y, 28.0),
        ]:
            add(kind, px, py, priority)
    return points or [{"kind": "click", "x": x, "y": y, "priority": 45.0}]


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
        tex_candidates = sorted(folder_path.glob("*.tex"))
        if not tex_candidates:
            raise FileNotFoundError("No `.tex` file found in the LaTeX folder.")
        for candidate in tex_candidates:
            if candidate.name.lower() == "main.tex":
                return candidate, f"{folder_relative.rstrip('/')}/{candidate.name}"
        chosen = tex_candidates[0]
        return chosen, f"{folder_relative.rstrip('/')}/{chosen.name}"

    def _folder_build_root(self, project_id: str, folder_relative: str) -> Path:
        quest_root = self._quest_root(project_id)
        return ensure_dir(quest_root / ".ds" / "latex_builds" / _sanitize_folder_key(folder_relative))

    def _folder_version_root(self, project_id: str, folder_relative: str) -> Path:
        quest_root = self._quest_root(project_id)
        return ensure_dir(quest_root / ".ds" / "latex_versions" / _sanitize_folder_key(folder_relative))

    def _folder_version_index_path(self, project_id: str, folder_relative: str) -> Path:
        return self._folder_version_root(project_id, folder_relative) / "index.json"

    def _folder_auto_version_state_path(self, project_id: str, folder_relative: str) -> Path:
        return self._folder_version_root(project_id, folder_relative) / "auto_state.json"

    def _folder_version_lock_path(self, project_id: str, folder_relative: str) -> Path:
        return self._folder_version_root(project_id, folder_relative) / "version.lock"

    def _build_record_path(self, project_id: str, folder_relative: str, build_id: str) -> Path:
        return self._folder_build_root(project_id, folder_relative) / "builds" / build_id / "build.json"

    @staticmethod
    def _git_stdout(repo: Path, args: list[str]) -> str:
        result = run_command(["git", *args], cwd=repo, check=False)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Git command failed.").strip())
        return result.stdout

    @staticmethod
    def _git_bytes(repo: Path, args: list[str]) -> bytes:
        result = run_command_bytes(["git", *args], cwd=repo, check=False)
        if result.returncode != 0:
            message = ""
            try:
                message = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
            except Exception:
                message = "Git command failed."
            raise RuntimeError(message or "Git command failed.")
        return result.stdout

    @staticmethod
    def _commit_exists(repo: Path, commit: str | None) -> bool:
        raw = str(commit or "").strip()
        if not raw:
            return False
        result = run_command(["git", "cat-file", "-e", f"{raw}^{{commit}}"], cwd=repo, check=False)
        return result.returncode == 0

    @staticmethod
    def _clean_version_text(value: Any, *, fallback: str = "", max_length: int = 500) -> str:
        text = str(value or "").strip()
        if not text:
            text = fallback
        text = re.sub(r"[\r\n]+", " ", text).strip()
        if len(text) > max_length:
            text = text[: max_length - 1].rstrip() + "…"
        return text

    @staticmethod
    def _parse_latex_version_trailers(message: str) -> dict[str, str]:
        trailers: dict[str, str] = {}
        for raw_line in str(message or "").splitlines():
            line = raw_line.strip()
            if not line.startswith(_LATEX_VERSION_TRAILER_PREFIX):
                continue
            key, _, value = line.partition(":")
            trailer_key = key[len(_LATEX_VERSION_TRAILER_PREFIX) :].strip()
            if trailer_key in _LATEX_VERSION_TRAILERS:
                trailers[trailer_key.lower()] = value.strip()
        return trailers

    @staticmethod
    def _is_truthy_trailer(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_utc_timestamp(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _latex_version_commit_message(
        self,
        *,
        version_id: str,
        folder_relative: str,
        main_file_relative: str | None,
        label: str,
        description: str | None,
        source: str,
        author: str | None,
        build_id: str | None,
        base_commit: str | None = None,
        reason: str | None = None,
        hidden: bool = False,
    ) -> str:
        title = self._clean_version_text(label, fallback="LaTeX version", max_length=120)
        body_lines = [f"latex: {title}", ""]
        if description:
            body_lines.extend([self._clean_version_text(description, max_length=500), ""])
        trailers = {
            "Version": version_id,
            "Folder": folder_relative,
            "Main": main_file_relative or "",
            "Source": source,
            "Author": author or "user",
            "Build": build_id or "",
            "Label": title,
            "Description": self._clean_version_text(description or "", max_length=500),
            "Base": self._clean_version_text(base_commit or "", max_length=80),
            "Reason": self._clean_version_text(reason or "", max_length=80),
            "Hidden": "true" if hidden else "false",
        }
        for key, value in trailers.items():
            body_lines.append(f"{_LATEX_VERSION_TRAILER_PREFIX}{key}: {value}")
        return "\n".join(body_lines).rstrip() + "\n"

    def _folder_has_git_changes(self, repo: Path, folder_relative: str) -> bool:
        result = run_command(["git", "status", "--porcelain", "--", folder_relative], cwd=repo, check=False)
        return bool((result.stdout or "").strip())

    @staticmethod
    def _is_transient_latex_artifact_path(relative: str) -> bool:
        path = Path(str(relative or ""))
        name = path.name
        lower_name = name.lower()
        suffix = path.suffix.lower()
        return suffix in _TRANSIENT_SOURCE_SUFFIXES or any(
            lower_name.endswith(transient_suffix) for transient_suffix in _TRANSIENT_SOURCE_SUFFIXES
        )

    @classmethod
    def _is_latex_version_file(cls, relative: str, main_file_relative: str | None = None) -> bool:
        normalized = str(relative or "").strip().lstrip("/")
        if not normalized:
            return False
        path = Path(normalized)
        if any(part.startswith(".git") for part in path.parts):
            return False
        if path.name.startswith("."):
            return False
        if cls._is_transient_latex_artifact_path(normalized):
            return False
        if main_file_relative:
            main_pdf = Path(main_file_relative).with_suffix(".pdf").as_posix()
            if normalized == main_pdf:
                return False
        return path.suffix.lower() in _LATEX_MANIFEST_SUFFIXES

    def _latex_version_paths(self, repo: Path, folder_path: Path, folder_relative: str, main_file_relative: str | None) -> list[str]:
        paths: set[str] = set()
        for path in sorted(folder_path.rglob("*")):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(repo).as_posix()
            except ValueError:
                continue
            if self._is_latex_version_file(relative, main_file_relative):
                paths.add(relative)

        status = run_command(["git", "status", "--porcelain", "--", folder_relative], cwd=repo, check=False)
        if status.returncode == 0:
            for raw_line in status.stdout.splitlines():
                if len(raw_line) < 4:
                    continue
                raw_path = raw_line[3:].strip()
                candidates = [raw_path]
                if " -> " in raw_path:
                    candidates = [part.strip() for part in raw_path.split(" -> ", 1)]
                for candidate in candidates:
                    if self._is_latex_version_file(candidate, main_file_relative):
                        paths.add(candidate)
        return sorted(paths)

    @staticmethod
    def _paths_have_git_changes(repo: Path, paths: list[str]) -> bool:
        if not paths:
            return False
        result = run_command(["git", "status", "--porcelain", "--", *paths], cwd=repo, check=False)
        return bool((result.stdout or "").strip())

    def _create_empty_latex_version_commit(self, repo: Path, message: str) -> tuple[bool, str | None, str | None]:
        head = head_commit(repo)
        if not head:
            return False, None, "Cannot create an empty LaTeX version before the quest repository has an initial commit."
        tree = self._git_stdout(repo, ["rev-parse", f"{head}^{{tree}}"]).strip()
        result = run_command(["git", "commit-tree", tree, "-p", head, "-m", message], cwd=repo, check=False)
        if result.returncode != 0:
            return False, head, (result.stderr or result.stdout or "Failed to create LaTeX version.").strip()
        commit = (result.stdout or "").strip()
        if not commit:
            return False, head, "Git did not return a commit id for the LaTeX version."
        update = run_command(["git", "update-ref", "HEAD", commit], cwd=repo, check=False)
        if update.returncode != 0:
            return False, head, (update.stderr or update.stdout or "Failed to update HEAD.").strip()
        return True, commit, None

    def _latex_range_stats(
        self,
        repo: Path,
        folder_relative: str,
        base_ref: str | None,
        head_ref: str | None = None,
        main_file_relative: str | None = None,
    ) -> dict[str, Any]:
        args = ["diff", "--find-renames", "--numstat"]
        if base_ref and head_ref:
            args.extend([base_ref, head_ref])
        elif base_ref:
            args.append(base_ref)
        else:
            args.append("HEAD")
        args.extend(["--", folder_relative])
        result = run_command(["git", *args], cwd=repo, check=False)
        raw = result.stdout if result.returncode == 0 else ""

        changed_paths: list[str] = []
        seen_paths: set[str] = set()
        added_total = 0
        removed_total = 0
        binary_files = 0
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added_raw, removed_raw, file_path = parts[0], parts[1], parts[-1]
            file_path = file_path.strip()
            if not file_path:
                continue
            if not self._is_latex_version_file(file_path, main_file_relative):
                continue
            if file_path not in seen_paths:
                seen_paths.add(file_path)
                changed_paths.append(file_path)
            if added_raw.isdigit():
                added_total += int(added_raw)
            elif added_raw == "-":
                binary_files += 1
            if removed_raw.isdigit():
                removed_total += int(removed_raw)

        untracked_count = 0
        untracked_bytes = 0
        if head_ref is None:
            untracked = run_command(
                ["git", "ls-files", "--others", "--exclude-standard", "--", folder_relative],
                cwd=repo,
                check=False,
            )
            if untracked.returncode == 0:
                for raw_path in untracked.stdout.splitlines():
                    file_path = raw_path.strip()
                    if not file_path or file_path in seen_paths:
                        continue
                    if not self._is_latex_version_file(file_path, main_file_relative):
                        continue
                    path = repo / file_path
                    if not path.exists() or not path.is_file():
                        continue
                    seen_paths.add(file_path)
                    changed_paths.append(file_path)
                    untracked_count += 1
                    try:
                        size = path.stat().st_size
                    except OSError:
                        size = 0
                    untracked_bytes += max(0, size)
                    if path.suffix.lower() in _LATEX_EDITABLE_SUFFIXES:
                        try:
                            text = path.read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            text = ""
                        added_total += len(text.splitlines()) or (1 if text else 0)

        changed_lines = added_total + removed_total
        changed_chars = changed_lines * 80 + untracked_bytes
        score = changed_lines + min(changed_chars // 80, 100) + len(changed_paths) * 10 + binary_files * 10
        significant = (
            changed_lines >= _LATEX_AUTO_VERSION_SIGNIFICANT_LINES
            or changed_chars >= _LATEX_AUTO_VERSION_SIGNIFICANT_CHARS
            or len(changed_paths) >= _LATEX_AUTO_VERSION_SIGNIFICANT_FILES
            or score >= 40
        )
        return {
            "changed_paths": changed_paths,
            "file_count": len(changed_paths),
            "changed_files": len(changed_paths),
            "added": added_total,
            "removed": removed_total,
            "changed_lines": changed_lines,
            "changed_chars": changed_chars,
            "binary_files": binary_files,
            "untracked_files": untracked_count,
            "score": score,
            "significant": significant,
            "has_changes": bool(changed_paths or changed_lines or changed_chars),
            "base": base_ref,
            "head": head_ref,
        }

    def _latex_commit_stats(self, repo: Path, commit: str, folder_relative: str, main_file_relative: str | None = None) -> dict[str, Any]:
        try:
            raw = self._git_stdout(
                repo,
                ["show", "--find-renames", "--numstat", "--format=", commit, "--", folder_relative],
            )
        except Exception:
            raw = ""
        changed_paths: list[str] = []
        added_total = 0
        removed_total = 0
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added_raw, removed_raw, file_path = parts[0], parts[1], parts[-1]
            file_path = file_path.strip()
            if not file_path:
                continue
            if not self._is_latex_version_file(file_path, main_file_relative):
                continue
            changed_paths.append(file_path)
            if added_raw.isdigit():
                added_total += int(added_raw)
            if removed_raw.isdigit():
                removed_total += int(removed_raw)
        return {
            "changed_paths": changed_paths,
            "file_count": len(changed_paths),
            "added": added_total,
            "removed": removed_total,
        }

    def _version_summary_from_commit(
        self,
        repo: Path,
        *,
        project_id: str,
        folder_id: str,
        folder_relative: str,
        commit: str,
    ) -> dict[str, Any] | None:
        try:
            raw = self._git_stdout(repo, ["show", "-s", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1f%B", commit])
        except Exception:
            return None
        parts = raw.split("\x1f", 5)
        if len(parts) < 6:
            return None
        sha, short_sha, author_name, authored_at, subject, message = [part.strip() for part in parts]
        trailers = self._parse_latex_version_trailers(message)
        version_folder = trailers.get("folder")
        if version_folder != folder_relative:
            return None
        version_id = trailers.get("version") or sha
        label = trailers.get("label") or subject.removeprefix("latex:").strip() or short_sha
        description = trailers.get("description") or None
        main_file_relative = trailers.get("main") or None
        source = trailers.get("source") or "manual"
        hidden = self._is_truthy_trailer(trailers.get("hidden")) or (
            source == "compile" and "hidden" not in trailers
        )
        parent_raw = run_command(["git", "rev-list", "--parents", "-n", "1", sha], cwd=repo, check=False)
        parent_parts = (parent_raw.stdout or "").strip().split()
        parents = parent_parts[1:] if len(parent_parts) > 1 else []
        trailer_base = trailers.get("base") or None
        if trailer_base and not self._commit_exists(repo, trailer_base):
            trailer_base = None
        compare_base = trailer_base or (parents[0] if parents else None)
        if compare_base:
            stats = self._latex_range_stats(repo, folder_relative, compare_base, sha, main_file_relative=main_file_relative)
        else:
            stats = self._latex_commit_stats(repo, sha, folder_relative, main_file_relative=main_file_relative)
        return {
            "version_id": version_id,
            "commit": sha,
            "short_commit": short_sha or sha[:7],
            "parents": parents,
            "compare_base": compare_base,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "main_file_path": main_file_relative,
            "label": label,
            "description": description,
            "source": source,
            "author": trailers.get("author") or author_name or None,
            "created_at": authored_at or utc_now(),
            "build_id": trailers.get("build") or None,
            "reason": trailers.get("reason") or None,
            "hidden": hidden,
            **stats,
        }

    def _remember_latex_version(self, project_id: str, folder_relative: str, summary: dict[str, Any]) -> None:
        path = self._folder_version_index_path(project_id, folder_relative)
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
        versions = existing.get("versions") if isinstance(existing.get("versions"), list) else []
        version_id = str(summary.get("version_id") or "")
        versions = [item for item in versions if not (isinstance(item, dict) and item.get("version_id") == version_id)]
        versions.insert(0, summary)
        write_json(
            path,
            {
                "schema_version": 1,
                "folder_path": folder_relative,
                "updated_at": utc_now(),
                "versions": versions[:200],
            },
        )

    def _read_latex_auto_version_state(self, project_id: str, folder_relative: str) -> dict[str, Any]:
        payload = read_json(self._folder_auto_version_state_path(project_id, folder_relative), default={})
        return payload if isinstance(payload, dict) else {}

    def _write_latex_auto_version_state(self, project_id: str, folder_relative: str, state: dict[str, Any]) -> None:
        payload = {
            "schema_version": 1,
            "policy_version": _LATEX_AUTO_VERSION_POLICY_VERSION,
            "folder_path": folder_relative,
            "updated_at": utc_now(),
            **state,
        }
        write_json(self._folder_auto_version_state_path(project_id, folder_relative), payload)

    def _remember_latex_visible_version(self, project_id: str, folder_relative: str, summary: dict[str, Any]) -> None:
        if summary.get("hidden"):
            return
        commit = str(summary.get("commit") or "").strip()
        if not commit:
            return
        state = self._read_latex_auto_version_state(project_id, folder_relative)
        created_at = str(summary.get("created_at") or utc_now())
        state.update(
            {
                "last_visible_version_commit": commit,
                "last_visible_version_id": summary.get("version_id"),
                "last_visible_version_at": created_at,
                "last_visible_source": summary.get("source"),
            }
        )
        if str(summary.get("source") or "").lower() in {"auto", "ai"}:
            state.update(
                {
                    "last_auto_version_commit": commit,
                    "last_auto_version_id": summary.get("version_id"),
                    "last_auto_version_at": created_at,
                    "last_auto_reason": summary.get("reason"),
                }
            )
        self._write_latex_auto_version_state(project_id, folder_relative, state)

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
            "synctex_ready": build.get("synctex_ready"),
            "pdf_path": build.get("output_pdf_path"),
            "synctex_path": build.get("synctex_path"),
            "errors": build.get("errors") or [],
            "log_items": build.get("log_items") or [],
        }
        write_json(report_path, payload)

    @staticmethod
    def _manifest_role_for(path: Path, main_tex_path: Path) -> str:
        if path.resolve() == main_tex_path.resolve():
            return "main"
        suffix = path.suffix.lower()
        if suffix == ".tex":
            return "tex"
        if suffix == ".bib":
            return "bib"
        if suffix in {".cls", ".sty", ".bst", ".bbx", ".cbx"}:
            return "style"
        if suffix in _LATEX_RESOURCE_SUFFIXES:
            return "resource"
        return "other"

    @staticmethod
    def _is_manifest_file(path: Path) -> bool:
        name = path.name
        if name.startswith("."):
            return False
        suffix = path.suffix.lower()
        if suffix in _TRANSIENT_SOURCE_SUFFIXES:
            return False
        return suffix in _LATEX_MANIFEST_SUFFIXES

    def _latest_compiler_for_folder(self, project_id: str, folder_relative: str) -> str:
        for record in self._list_build_records(project_id, folder_relative):
            compiler = str(record.get("compiler") or "").strip().lower()
            if compiler in _VALID_COMPILERS:
                return compiler
        return "pdflatex"

    def _resolve_latex_dependency(
        self,
        folder_path: Path,
        source_path: Path,
        raw_value: str,
        *,
        suffix: str,
    ) -> str | None:
        token = str(raw_value or "").strip()
        if not token:
            return None
        # \bibliography can contain comma-separated names.
        token = token.split(",", 1)[0].strip()
        if not token:
            return None
        candidate = Path(token.replace("\\", "/"))
        if candidate.suffix == "":
            candidate = candidate.with_suffix(suffix)
        search_roots = [source_path.parent, folder_path]
        for root in search_roots:
            try:
                resolved = (root / candidate).resolve()
            except OSError:
                continue
            try:
                resolved.relative_to(folder_path.resolve())
            except ValueError:
                continue
            if resolved.exists():
                return resolved.relative_to(folder_path).as_posix()
        return candidate.as_posix()

    def _manifest_dependencies(self, folder_path: Path, file_path: Path) -> list[dict[str, str]]:
        if file_path.suffix.lower() != ".tex":
            return []
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        deps: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for match in _LATEX_INPUT_RE.finditer(text):
            target = self._resolve_latex_dependency(folder_path, file_path, match.group(1), suffix=".tex")
            if not target:
                continue
            key = ("input", target)
            if key in seen:
                continue
            seen.add(key)
            deps.append({"kind": "input", "path": target})
        for match in _LATEX_BIB_RE.finditer(text):
            target = self._resolve_latex_dependency(folder_path, file_path, match.group(1), suffix=".bib")
            if not target:
                continue
            key = ("bibliography", target)
            if key in seen:
                continue
            seen.add(key)
            deps.append({"kind": "bibliography", "path": target})
        return deps

    def manifest(self, project_id: str, folder_id: str) -> dict[str, Any]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        main_tex_path, main_tex_relative = self._resolve_main_tex(project_id, folder_path, folder_relative, None)
        workspace_root = self._workspace_root(project_id)
        files: list[dict[str, Any]] = []

        for path in sorted(folder_path.rglob("*")):
            if not path.is_file():
                continue
            try:
                relative_to_folder = path.relative_to(folder_path).as_posix()
            except ValueError:
                continue
            if any(part.startswith(".git") for part in Path(relative_to_folder).parts):
                continue
            if not self._is_manifest_file(path):
                continue
            try:
                relative_to_workspace = path.relative_to(workspace_root).as_posix()
            except ValueError:
                relative_to_workspace = path.relative_to(self._quest_root(project_id)).as_posix()
            role = self._manifest_role_for(path, main_tex_path)
            editable = role in {"main", "tex", "bib", "style"}
            files.append(
                {
                    "id": _encode_quest_file_id(project_id, relative_to_workspace),
                    "name": path.name,
                    "path": relative_to_workspace,
                    "relative_path": relative_to_folder,
                    "role": role,
                    "editable": editable,
                    "size": path.stat().st_size,
                    "dependencies": self._manifest_dependencies(folder_path, path) if editable else [],
                }
            )

        files.sort(
            key=lambda item: (
                0 if item.get("role") == "main" else 1,
                str(item.get("relative_path") or item.get("path") or "").lower(),
            )
        )
        return {
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "folder_name": folder_path.name,
            "main_file_id": _encode_quest_file_id(project_id, main_tex_relative),
            "main_file_path": main_tex_relative,
            "compiler": self._latest_compiler_for_folder(project_id, folder_relative),
            "files": files,
        }

    def create_version(
        self,
        project_id: str,
        folder_id: str,
        *,
        label: str | None = None,
        description: str | None = None,
        source: str | None = None,
        author: str | None = None,
        build_id: str | None = None,
        allow_empty: bool = True,
        hidden: bool = False,
        reason: str | None = None,
        base_commit: str | None = None,
    ) -> dict[str, Any]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        _main_tex_path, main_tex_relative = self._resolve_main_tex(project_id, folder_path, folder_relative, None)
        repo = self._workspace_root(project_id)
        version_id = generate_id("latex-version")
        resolved_source = self._clean_version_text(source, fallback="manual", max_length=40).lower().replace(" ", "_")
        if resolved_source not in {"manual", "auto", "compile", "ai", "restore"}:
            resolved_source = "manual"
        default_label = {
            "manual": "Manual version",
            "auto": "Auto version",
            "compile": "Compile source",
            "ai": "AI edit",
            "restore": "Restore version",
        }.get(resolved_source, "LaTeX version")
        resolved_label = self._clean_version_text(label, fallback=default_label, max_length=120)
        resolved_description = self._clean_version_text(description, max_length=500) if description else None
        message = self._latex_version_commit_message(
            version_id=version_id,
            folder_relative=folder_relative,
            main_file_relative=main_tex_relative,
            label=resolved_label,
            description=resolved_description,
            source=resolved_source,
            author=author,
            build_id=build_id,
            base_commit=base_commit,
            reason=reason,
            hidden=hidden,
        )

        version_paths = self._latex_version_paths(repo, folder_path, folder_relative, main_tex_relative)
        has_changes = self._paths_have_git_changes(repo, version_paths)
        previous_head = head_commit(repo)
        if not has_changes and not allow_empty:
            return {
                "ok": False,
                "created": False,
                "message": "No LaTeX source changes to version.",
                "version_id": None,
                "commit": previous_head,
                "head": previous_head,
                "folder_id": folder_id,
                "folder_path": folder_relative,
        }

        if has_changes:
            run_command(["git", "add", "-A", "--", *version_paths], cwd=repo, check=False)
            command = ["git", "commit"]
            if allow_empty:
                command.append("--allow-empty")
            command.extend(["-m", message, "--", *version_paths])
            result = run_command(command, cwd=repo, check=False)
            if result.returncode != 0:
                return {
                    "ok": False,
                    "created": False,
                    "message": (result.stderr or result.stdout or "Failed to create LaTeX version.").strip(),
                    "version_id": version_id,
                    "commit": previous_head,
                    "head": previous_head,
                    "folder_id": folder_id,
                    "folder_path": folder_relative,
                }
            commit = head_commit(repo)
        else:
            ok, commit, error_message = self._create_empty_latex_version_commit(repo, message)
            if not ok or not commit:
                return {
                    "ok": False,
                    "created": False,
                    "message": error_message or "Failed to create LaTeX version.",
                    "version_id": version_id,
                    "commit": previous_head,
                    "head": previous_head,
                    "folder_id": folder_id,
                    "folder_path": folder_relative,
                }

        summary = self._version_summary_from_commit(
            repo,
            project_id=project_id,
            folder_id=folder_id,
            folder_relative=folder_relative,
            commit=commit or "",
        )
        if not summary:
            summary = {
                "version_id": version_id,
                "commit": commit,
                "short_commit": str(commit or "")[:7],
                "folder_id": folder_id,
                "folder_path": folder_relative,
                "main_file_path": main_tex_relative,
                "label": resolved_label,
                "description": resolved_description,
                "source": resolved_source,
                "author": author or "user",
                "created_at": utc_now(),
                "build_id": build_id,
                "reason": reason,
                "hidden": bool(hidden),
                "compare_base": base_commit,
                "changed_paths": [],
                "file_count": 0,
                "added": 0,
                "removed": 0,
            }
        self._remember_latex_version(project_id, folder_relative, summary)
        self._remember_latex_visible_version(project_id, folder_relative, summary)
        return {
            "ok": True,
            "created": True,
            "message": "LaTeX version created.",
            "head": commit,
            "previous_head": previous_head,
            "version": summary,
            **summary,
        }

    def list_versions(self, project_id: str, folder_id: str, limit: int = 30, *, include_hidden: bool = False) -> dict[str, Any]:
        _folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        repo = self._workspace_root(project_id)
        resolved_limit = max(1, min(int(limit or 30), 100))
        scan_limit = max(500, resolved_limit * 50)
        try:
            raw = self._git_stdout(
                repo,
                ["log", f"-n{scan_limit}", "--format=%H%x1e"],
            )
        except Exception as exc:
            return {
                "ok": False,
                "message": str(exc),
                "folder_id": folder_id,
                "folder_path": folder_relative,
                "head": head_commit(repo),
                "versions": [],
            }

        versions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in raw.split("\x1e"):
            commit = record.strip()
            if not commit or commit in seen:
                continue
            seen.add(commit)
            summary = self._version_summary_from_commit(
                repo,
                project_id=project_id,
                folder_id=folder_id,
                folder_relative=folder_relative,
                commit=commit,
            )
            if not summary:
                continue
            if summary.get("hidden") and not include_hidden:
                continue
            versions.append(summary)
            if len(versions) >= resolved_limit:
                break

        return {
            "ok": True,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "head": head_commit(repo),
            "versions": versions,
            "limit": resolved_limit,
            "include_hidden": include_hidden,
        }

    def maybe_create_auto_version(
        self,
        project_id: str,
        folder_id: str,
        *,
        reason: str | None = None,
        active_file: str | None = None,
    ) -> dict[str, Any]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        _main_tex_path, main_tex_relative = self._resolve_main_tex(project_id, folder_path, folder_relative, None)
        repo = self._workspace_root(project_id)
        reason_key = self._clean_version_text(reason or "idle_save", fallback="idle_save", max_length=80)
        reason_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason_key.lower()).strip("_") or "idle_save"

        with advisory_file_lock(self._folder_version_lock_path(project_id, folder_relative)):
            state = self._read_latex_auto_version_state(project_id, folder_relative)
            visible_versions = self.list_versions(project_id, folder_id, limit=1, include_hidden=False).get("versions") or []
            latest_visible = visible_versions[0] if visible_versions and isinstance(visible_versions[0], dict) else None
            if latest_visible:
                state_commit = str(state.get("last_visible_version_commit") or "").strip()
                latest_commit = str(latest_visible.get("commit") or "").strip()
                if latest_commit and state_commit != latest_commit:
                    state.update(
                        {
                            "last_visible_version_commit": latest_commit,
                            "last_visible_version_id": latest_visible.get("version_id"),
                            "last_visible_version_at": latest_visible.get("created_at") or utc_now(),
                            "last_visible_source": latest_visible.get("source"),
                        }
                    )

            base_commit = str(state.get("last_visible_version_commit") or "").strip()
            if base_commit and not self._commit_exists(repo, base_commit):
                base_commit = ""
            if not base_commit and latest_visible:
                base_commit = str(latest_visible.get("commit") or "").strip()
            if base_commit and not self._commit_exists(repo, base_commit):
                base_commit = ""
            if not base_commit:
                base_commit = head_commit(repo) or ""

            metrics = self._latex_range_stats(
                repo,
                folder_relative,
                base_commit or None,
                None,
                main_file_relative=main_tex_relative,
            )
            if not metrics.get("has_changes"):
                self._write_latex_auto_version_state(project_id, folder_relative, state)
                return {
                    "ok": True,
                    "created": False,
                    "skipped_reason": "no_changes",
                    "message": "No LaTeX source changes to checkpoint.",
                    "folder_id": folder_id,
                    "folder_path": folder_relative,
                    "head": head_commit(repo),
                    "base": base_commit or None,
                    "metrics": metrics,
                    "policy": {
                        "version": _LATEX_AUTO_VERSION_POLICY_VERSION,
                        "min_interval_seconds": _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS,
                        "time_interval_seconds": _LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS,
                    },
                }

            now = datetime.now(UTC)
            last_checkpoint_at = self._parse_utc_timestamp(state.get("last_visible_version_at"))
            if last_checkpoint_at is None:
                last_checkpoint_at = self._parse_utc_timestamp(state.get("last_auto_version_at"))
            elapsed_seconds = None
            if last_checkpoint_at is not None:
                elapsed_seconds = max(0, int((now - last_checkpoint_at).total_seconds()))
                if elapsed_seconds < _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS:
                    next_eligible = last_checkpoint_at.timestamp() + _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS
                    return {
                        "ok": True,
                        "created": False,
                        "skipped_reason": "too_soon",
                        "message": "The last LaTeX checkpoint is too recent.",
                        "folder_id": folder_id,
                        "folder_path": folder_relative,
                        "head": head_commit(repo),
                        "base": base_commit or None,
                        "metrics": metrics,
                        "elapsed_seconds": elapsed_seconds,
                        "next_eligible_at": datetime.fromtimestamp(next_eligible, UTC).replace(microsecond=0).isoformat(),
                        "policy": {
                            "version": _LATEX_AUTO_VERSION_POLICY_VERSION,
                            "min_interval_seconds": _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS,
                            "time_interval_seconds": _LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS,
                        },
                    }

            first_visible_checkpoint = latest_visible is None and not state.get("last_visible_version_commit")
            significant = bool(metrics.get("significant"))
            timed = elapsed_seconds is not None and elapsed_seconds >= _LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS
            if not (first_visible_checkpoint or significant or timed):
                self._write_latex_auto_version_state(project_id, folder_relative, state)
                return {
                    "ok": True,
                    "created": False,
                    "skipped_reason": "change_below_threshold",
                    "message": "LaTeX changes are below the automatic checkpoint threshold.",
                    "folder_id": folder_id,
                    "folder_path": folder_relative,
                    "head": head_commit(repo),
                    "base": base_commit or None,
                    "metrics": metrics,
                    "elapsed_seconds": elapsed_seconds,
                    "policy": {
                        "version": _LATEX_AUTO_VERSION_POLICY_VERSION,
                        "min_interval_seconds": _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS,
                        "time_interval_seconds": _LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS,
                        "significant_lines": _LATEX_AUTO_VERSION_SIGNIFICANT_LINES,
                        "significant_chars": _LATEX_AUTO_VERSION_SIGNIFICANT_CHARS,
                        "significant_files": _LATEX_AUTO_VERSION_SIGNIFICANT_FILES,
                    },
                }

            source = "ai" if reason_key == "ai_edit" else "auto"
            label = "AI edit" if source == "ai" else "Auto version"
            if reason_key == "visibility_hidden":
                description = "Automatic checkpoint captured when the editor was hidden."
            elif reason_key == "compile":
                description = "Automatic checkpoint captured before LaTeX compilation."
            elif source == "ai":
                description = "Automatic checkpoint captured after an AI file edit."
            elif timed:
                description = "Automatic checkpoint captured after an editing interval."
            else:
                description = "Automatic checkpoint captured after significant LaTeX edits."

            created = self.create_version(
                project_id,
                folder_id,
                label=label,
                description=description,
                source=source,
                author="ai" if source == "ai" else "system",
                allow_empty=True,
                hidden=False,
                reason=reason_key,
                base_commit=base_commit or None,
            )
            if not created.get("ok"):
                return {
                    **created,
                    "created": False,
                    "skipped_reason": "create_failed",
                    "metrics": metrics,
                    "base": base_commit or None,
                }
            state = self._read_latex_auto_version_state(project_id, folder_relative)
            state.update(
                {
                    "last_auto_metrics": metrics,
                    "last_auto_active_file": self._clean_version_text(active_file or "", max_length=240),
                    "last_auto_reason": reason_key,
                }
            )
            self._write_latex_auto_version_state(project_id, folder_relative, state)
            return {
                **created,
                "created": True,
                "skipped_reason": None,
                "reason": reason_key,
                "base": base_commit or None,
                "metrics": metrics,
                "policy": {
                    "version": _LATEX_AUTO_VERSION_POLICY_VERSION,
                    "min_interval_seconds": _LATEX_AUTO_VERSION_MIN_INTERVAL_SECONDS,
                    "time_interval_seconds": _LATEX_AUTO_VERSION_TIME_INTERVAL_SECONDS,
                    "significant_lines": _LATEX_AUTO_VERSION_SIGNIFICANT_LINES,
                    "significant_chars": _LATEX_AUTO_VERSION_SIGNIFICANT_CHARS,
                    "significant_files": _LATEX_AUTO_VERSION_SIGNIFICANT_FILES,
                },
            }

    def _resolve_version_commit(self, project_id: str, folder_id: str, version_id: str) -> tuple[str, dict[str, Any] | None, str]:
        _folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        repo = self._workspace_root(project_id)
        raw = str(version_id or "").strip()
        if not raw:
            raise ValueError("`version_id` is required.")
        versions = self.list_versions(project_id, folder_id, limit=100, include_hidden=True).get("versions") or []
        for item in versions:
            if not isinstance(item, dict):
                continue
            if raw in {str(item.get("version_id") or ""), str(item.get("commit") or ""), str(item.get("short_commit") or "")}:
                return str(item.get("commit") or ""), item, folder_relative
        result = run_command(["git", "rev-parse", "--verify", raw], cwd=repo, check=False)
        if result.returncode == 0:
            commit = (result.stdout or "").strip()
            summary = self._version_summary_from_commit(
                repo,
                project_id=project_id,
                folder_id=folder_id,
                folder_relative=folder_relative,
                commit=commit,
            )
            return commit, summary, folder_relative
        raise FileNotFoundError(f"Unknown LaTeX version `{version_id}`.")

    def get_version(self, project_id: str, folder_id: str, version_id: str) -> dict[str, Any]:
        commit, summary, folder_relative = self._resolve_version_commit(project_id, folder_id, version_id)
        return {
            "ok": True,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "version": summary,
            **(summary or {"commit": commit}),
        }

    def version_files(self, project_id: str, folder_id: str, version_id: str) -> dict[str, Any]:
        commit, summary, folder_relative = self._resolve_version_commit(project_id, folder_id, version_id)
        repo = self._workspace_root(project_id)
        raw = self._git_stdout(repo, ["ls-tree", "-r", "--name-only", commit, "--", folder_relative])
        files: list[dict[str, Any]] = []
        folder_path, _folder_relative = self._resolve_folder_path(project_id, folder_id)
        main_relative = str((summary or {}).get("main_file_path") or "")
        for relative in [line.strip() for line in raw.splitlines() if line.strip()]:
            path = Path(relative)
            if path.name.startswith("."):
                continue
            if path.suffix.lower() not in _LATEX_MANIFEST_SUFFIXES:
                continue
            suffix = path.suffix.lower()
            if relative == main_relative:
                role = "main"
            elif suffix == ".tex":
                role = "tex"
            elif suffix == ".bib":
                role = "bib"
            elif suffix in {".cls", ".sty", ".bst", ".bbx", ".cbx"}:
                role = "style"
            elif suffix in _LATEX_RESOURCE_SUFFIXES:
                role = "resource"
            else:
                role = "other"
            try:
                rel_to_folder = path.relative_to(Path(folder_relative)).as_posix()
            except Exception:
                rel_to_folder = path.name
            files.append(
                {
                    "id": _encode_quest_file_id(project_id, relative),
                    "name": path.name,
                    "path": relative,
                    "relative_path": rel_to_folder,
                    "role": role,
                    "editable": role in {"main", "tex", "bib", "style"},
                    "document_id": f"git::{commit}::{relative}",
                }
            )
        return {
            "ok": True,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "version": summary,
            "commit": commit,
            "files": files,
            "folder_exists": folder_path.exists(),
        }

    def version_file(self, project_id: str, folder_id: str, version_id: str, path: str) -> dict[str, Any]:
        commit, summary, folder_relative = self._resolve_version_commit(project_id, folder_id, version_id)
        relative = str(path or "").strip().lstrip("/")
        if not relative:
            raise ValueError("`path` is required.")
        if not (relative == folder_relative or relative.startswith(f"{folder_relative.rstrip('/')}/")):
            raise ValueError("`path` must belong to the LaTeX folder.")
        content = self._git_bytes(self._workspace_root(project_id), ["show", f"{commit}:{relative}"])
        try:
            text = content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = ""
            encoding = None
        return {
            "ok": True,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "version": summary,
            "commit": commit,
            "path": relative,
            "content": text,
            "encoding": encoding,
            "size_bytes": len(content),
        }

    def compare_versions(self, project_id: str, folder_id: str, *, base: str, head: str) -> dict[str, Any]:
        base_commit, base_summary, folder_relative = self._resolve_version_commit(project_id, folder_id, base)
        head_commit_value, head_summary, _folder_relative = self._resolve_version_commit(project_id, folder_id, head)
        repo = self._workspace_root(project_id)
        payload = compare_refs(repo, base=base_commit, head=head_commit_value)
        main_file_relative = str(
            (head_summary or {}).get("main_file_path")
            or (base_summary or {}).get("main_file_path")
            or ""
        )
        files = [
            item
            for item in payload.get("files", [])
            if str(item.get("path") or "") == folder_relative
            or (
                str(item.get("path") or "").startswith(f"{folder_relative.rstrip('/')}/")
                and self._is_latex_version_file(str(item.get("path") or ""), main_file_relative or None)
            )
        ]
        return {
            **payload,
            "folder_id": folder_id,
            "folder_path": folder_relative,
            "base": base_commit,
            "head": head_commit_value,
            "base_version": base_summary,
            "head_version": head_summary,
            "files": files,
            "file_count": len(files),
        }

    def _current_manifest_paths(
        self,
        folder_path: Path,
        folder_relative: str = "",
        main_file_relative: str | None = None,
    ) -> set[str]:
        paths: set[str] = set()
        for path in sorted(folder_path.rglob("*")):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(folder_path).as_posix()
            except ValueError:
                continue
            if any(part.startswith(".git") for part in Path(relative).parts):
                continue
            workspace_relative = f"{folder_relative.rstrip('/')}/{relative}" if folder_relative else relative
            if self._is_latex_version_file(workspace_relative, main_file_relative):
                paths.add(relative)
        return paths

    def restore_version(
        self,
        project_id: str,
        folder_id: str,
        version_id: str,
        *,
        mode: str | None = None,
        path: str | None = None,
        expected_head: str | None = None,
        conflict_policy: str | None = None,
    ) -> dict[str, Any]:
        commit, summary, folder_relative = self._resolve_version_commit(project_id, folder_id, version_id)
        repo = self._workspace_root(project_id)
        current_head = head_commit(repo)
        if expected_head and current_head and str(expected_head).strip() != current_head:
            return {
                "ok": False,
                "conflict": True,
                "message": "The quest HEAD changed. Refresh the LaTeX history before restoring.",
                "expected_head": expected_head,
                "current_head": current_head,
            }
        force = str(conflict_policy or "").strip().lower() == "force"
        folder_path, _folder_relative = self._resolve_folder_path(project_id, folder_id)
        main_file_relative = str((summary or {}).get("main_file_path") or "")
        if not main_file_relative:
            try:
                _main_tex_path, main_file_relative = self._resolve_main_tex(project_id, folder_path, folder_relative, None)
            except Exception:
                main_file_relative = ""
        current_version_paths = self._latex_version_paths(repo, folder_path, folder_relative, main_file_relative or None)
        if self._paths_have_git_changes(repo, current_version_paths) and not force:
            return {
                "ok": False,
                "conflict": True,
                "message": "The LaTeX folder has unversioned changes. Create a version or force restore before restoring.",
                "current_head": current_head,
            }

        restore_mode = str(mode or "folder").strip().lower()
        restored_paths: list[str] = []

        if restore_mode == "file":
            relative = str(path or "").strip().lstrip("/")
            if not relative:
                raise ValueError("`path` is required when restoring one file.")
            if not (relative == folder_relative or relative.startswith(f"{folder_relative.rstrip('/')}/")):
                raise ValueError("`path` must belong to the LaTeX folder.")
            target_path = resolve_within(repo, relative)
            blob = self._git_bytes(repo, ["show", f"{commit}:{relative}"])
            ensure_dir(target_path.parent)
            target_path.write_bytes(blob)
            restored_paths.append(relative)
        else:
            raw_paths = self._git_stdout(repo, ["ls-tree", "-r", "--name-only", commit, "--", folder_relative])
            version_paths = [
                line.strip()
                for line in raw_paths.splitlines()
                if line.strip() and self._is_latex_version_file(line.strip(), main_file_relative or None)
            ]
            version_rel_to_folder = {
                Path(relative).relative_to(Path(folder_relative)).as_posix()
                for relative in version_paths
                if relative == folder_relative or relative.startswith(f"{folder_relative.rstrip('/')}/")
            }
            for current_relative in self._current_manifest_paths(folder_path, folder_relative, main_file_relative or None):
                if current_relative not in version_rel_to_folder:
                    try:
                        (folder_path / current_relative).unlink()
                    except FileNotFoundError:
                        pass
            for relative in version_paths:
                if not (relative == folder_relative or relative.startswith(f"{folder_relative.rstrip('/')}/")):
                    continue
                target_path = resolve_within(repo, relative)
                blob = self._git_bytes(repo, ["show", f"{commit}:{relative}"])
                ensure_dir(target_path.parent)
                target_path.write_bytes(blob)
                restored_paths.append(relative)

        label = f"Restore {str((summary or {}).get('label') or version_id)}"
        created = self.create_version(
            project_id,
            folder_id,
            label=label,
            description=f"Restored from LaTeX version {version_id} ({commit[:12]}).",
            source="restore",
            author="user",
            allow_empty=False,
        )
        return {
            "ok": bool(created.get("ok")),
            "message": created.get("message") or "LaTeX version restored.",
            "restored_from": summary or {"commit": commit, "version_id": version_id},
            "restored_paths": restored_paths,
            "restore_version": created.get("version"),
            "head": created.get("head") or head_commit(repo),
            "conflict": False,
        }

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
            "synctex_ready": False,
            "synctex_path": None,
            "bibtex_binary": None,
            "auto": bool(auto),
            "stop_on_first_error": bool(stop_on_first_error),
            "source_commit": None,
            "source_version_id": None,
            "source_version": None,
            "source_version_error": None,
            "auto_version_id": None,
            "auto_version": None,
            "auto_version_skipped_reason": None,
        }

        try:
            auto_version = self.maybe_create_auto_version(project_id, folder_id, reason="compile")
            build["auto_version_skipped_reason"] = auto_version.get("skipped_reason")
            if auto_version.get("created") and isinstance(auto_version.get("version"), dict):
                build["auto_version_id"] = auto_version["version"].get("version_id")
                build["auto_version"] = auto_version["version"]
        except Exception:
            pass

        try:
            source_version = self.create_version(
                project_id,
                folder_id,
                label="Compile source" if not auto else "Auto compile source",
                description="Source snapshot captured before LaTeX compilation.",
                source="compile",
                author="system",
                build_id=build_id,
                hidden=True,
                reason="compile",
                allow_empty=not bool(auto),
            )
            if source_version.get("ok") and isinstance(source_version.get("version"), dict):
                version_payload = dict(source_version["version"])
                build["source_commit"] = version_payload.get("commit")
                build["source_version_id"] = version_payload.get("version_id")
                build["source_version"] = version_payload
            else:
                build["source_commit"] = source_version.get("commit") or head_commit(self._workspace_root(project_id))
                build["source_version_error"] = source_version.get("message")
        except Exception as exc:
            build["source_commit"] = head_commit(self._workspace_root(project_id))
            build["source_version_error"] = str(exc)
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
            "-synctex=1",
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
        generated_synctex = folder_path / f"{main_tex_path.stem}.synctex.gz"
        if not generated_synctex.exists():
            generated_synctex = folder_path / f"{main_tex_path.stem}.synctex"
        synctex_copy_path = build_dir / generated_synctex.name
        synctex_ready = generated_synctex.exists() and generated_synctex.is_file()
        pdf_ready = exit_code == 0 and generated_pdf.exists()
        if pdf_ready:
            shutil.copy2(generated_pdf, pdf_copy_path)
        if synctex_ready:
            shutil.copy2(generated_synctex, synctex_copy_path)

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
                "synctex_ready": synctex_ready,
                "synctex_path": str(synctex_copy_path) if synctex_ready else None,
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

    def synctex_edit(
        self,
        project_id: str,
        folder_id: str,
        build_id: str,
        *,
        page: int | float | str | None,
        x: int | float | str | None,
        y: int | float | str | None,
        pdf_word: str | None = None,
        pdf_context_words: list[str] | None = None,
        pdf_context_index: int | None = None,
        pdf_word_bbox: Any = None,
        pdf_word_center: Any = None,
    ) -> dict[str, Any]:
        folder_path, folder_relative = self._resolve_folder_path(project_id, folder_id)
        build = self.get_build(project_id, folder_id, build_id)

        def _as_positive_number(value: int | float | str | None, name: str) -> float:
            try:
                parsed = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"`{name}` must be a number.") from exc
            if not (parsed >= 0):
                raise ValueError(f"`{name}` must be non-negative.")
            return parsed

        page_number = int(round(_as_positive_number(page, "page")))
        if page_number < 1:
            raise ValueError("`page` must be at least 1.")
        point_x = _as_positive_number(x, "x")
        point_y = _as_positive_number(y, "y")

        output_pdf_path = str(build.get("output_pdf_path") or "").strip()
        synctex_path = str(build.get("synctex_path") or "").strip()
        if not output_pdf_path or not Path(output_pdf_path).is_file():
            return {
                "ok": False,
                "message": "PDF output is not available for this build.",
                "reason": "missing_pdf",
            }
        if not bool(build.get("synctex_ready")) or not synctex_path or not Path(synctex_path).is_file():
            return {
                "ok": False,
                "message": "SyncTeX data is not available. Recompile the LaTeX project to enable PDF-to-source jumps.",
                "reason": "missing_synctex",
            }

        runtime_tools = RuntimeToolService(self.quest_service.home)
        synctex_match = runtime_tools.resolve_binary("synctex", preferred_tools=("tinytex",))
        synctex_bin = synctex_match.get("path")
        if not synctex_bin:
            return {
                "ok": False,
                "message": "`synctex` is not installed on this machine.",
                "reason": "missing_synctex_binary",
            }

        synctex_dir = Path(synctex_path).parent
        output_pdf = Path(output_pdf_path)
        workspace_root = self._workspace_root(project_id).resolve()
        quest_root = self._quest_root(project_id).resolve()

        def _int_or_none(value: str | None) -> int | None:
            try:
                parsed = int(str(value or "").strip())
            except ValueError:
                return None
            return parsed if parsed >= 0 else None

        def _run_synctex_sample(sample: dict[str, Any]) -> tuple[int, dict[str, str], str]:
            result = subprocess.run(
                [
                    str(synctex_bin),
                    "edit",
                    "-o",
                    f"{page_number}:{float(sample['x']):.3f}:{float(sample['y']):.3f}:{output_pdf}",
                    "-d",
                    str(synctex_dir),
                ],
                cwd=str(folder_path),
                capture_output=True,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
            combined = (result.stdout or "") + (result.stderr or "")
            return result.returncode, _parse_synctex_records(combined), combined

        def _candidate_from_records(
            records: dict[str, str],
            sample: dict[str, Any],
            raw_output: str,
        ) -> dict[str, Any] | None:
            raw_input = records.get("input")
            if not raw_input:
                return None
            input_path = Path(raw_input)
            if not input_path.is_absolute():
                input_path = folder_path / input_path
            try:
                input_path = input_path.resolve()
            except OSError:
                return None

            source_root = workspace_root
            try:
                input_relative = input_path.relative_to(workspace_root).as_posix()
            except ValueError:
                try:
                    input_relative = input_path.relative_to(quest_root).as_posix()
                    source_root = quest_root
                except ValueError:
                    return None

            try:
                resolved_input = resolve_within(source_root, input_relative)
            except ValueError:
                resolved_input = resolve_within(quest_root, input_relative)
            if not resolved_input.exists() or not resolved_input.is_file():
                return None
            try:
                resolved_input.resolve().relative_to(folder_path.resolve())
            except ValueError:
                return None

            line = _int_or_none(records.get("line")) or 1
            column = _int_or_none(records.get("column"))
            try:
                source_text = resolved_input.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                source_text = ""
            selection = _source_selection_for_synctex(
                source_text,
                line=line,
                column=column,
                pdf_word=pdf_word,
                pdf_context_words=pdf_context_words,
                pdf_context_index=pdf_context_index,
            )
            return {
                "file_id": _encode_quest_file_id(project_id, input_relative),
                "file_path": input_relative,
                "file_name": Path(input_relative).name,
                "line": max(1, line),
                "column": column if column and column > 0 else None,
                "selection": selection,
                "sample": sample,
                "raw": raw_output[-2000:],
                "records": records,
            }

        samples = _synctex_sample_points(
            point_x,
            point_y,
            pdf_word_bbox=pdf_word_bbox,
            pdf_word_center=pdf_word_center,
        )
        candidates: list[dict[str, Any]] = []
        raw_outputs: list[str] = []
        for sample in samples:
            return_code, records, raw_output = _run_synctex_sample(sample)
            raw_outputs.append(raw_output)
            if return_code != 0:
                continue
            candidate = _candidate_from_records(records, sample, raw_output)
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return {
                "ok": False,
                "message": "No source location was found for this PDF position.",
                "reason": "not_found",
                "raw": "\n".join(raw_outputs)[-4000:],
            }

        counts = Counter((candidate["file_path"], candidate["line"]) for candidate in candidates)

        def _candidate_score(candidate: dict[str, Any]) -> float:
            selection = candidate.get("selection") or {}
            sample = candidate.get("sample") or {}
            score = float(selection.get("score") or 0)
            score += float(sample.get("priority") or 0)
            score += counts[(candidate["file_path"], candidate["line"])] * 25.0
            if selection.get("precision") == "exact_word":
                score += 250.0
            return score

        best = max(candidates, key=_candidate_score)
        selection = dict(best.get("selection") or {})
        selection.pop("score", None)
        precision = selection.get("precision") or ("line_column" if best.get("column") else "line_only")
        if precision == "exact_word":
            line = int(selection.get("start_line") or best["line"])
            column = int(selection.get("start_column") or best.get("column") or 1)
        else:
            line = int(best["line"])
            column = int(best.get("column") or selection.get("start_column") or 1)

        return {
            "ok": True,
            "file_id": best["file_id"],
            "file_path": best["file_path"],
            "file_name": best["file_name"],
            "line": max(1, line),
            "column": column if column and column > 0 else None,
            "selection": selection,
            "precision": precision,
            "confidence": selection.get("confidence"),
            "pdf_word": str(pdf_word or "").strip() or None,
            "pdf_context_words": pdf_context_words or None,
            "pdf_context_index": pdf_context_index,
            "synctex_line": best["line"],
            "synctex_column": best.get("column"),
            "sample_count": len(samples),
            "candidate_count": len(candidates),
            "matched_sample": best.get("sample"),
            "page": page_number,
            "x": point_x,
            "y": point_y,
            "folder_id": folder_id,
            "folder_path": folder_relative,
        }
