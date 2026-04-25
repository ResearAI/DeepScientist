from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from ..artifact import ArtifactService
from ..codex_cli_compat import (
    active_provider_metadata_from_home,
    materialize_codex_runtime_home,
    normalize_codex_reasoning_effort,
    provider_profile_metadata_from_home,
)
from ..config import ConfigManager
from ..gitops import export_git_graph
from ..process_control import process_session_popen_kwargs
from ..prompts import PromptBuilder
from ..runtime_logs import JsonlLogger
from ..shared import append_jsonl, ensure_dir, ensure_utf8_subprocess_env, generate_id, read_yaml, resolve_runner_binary, utc_now, write_json, write_text
from ..web_search import extract_web_search_payload
from .base import (
    SETTINGS_ISSUE_CUSTOM_PROFILE,
    START_SETUP_PREPARE_PROFILE,
    RunRequest,
    RunResult,
    builtin_mcp_server_names_for_custom_profile,
    extract_start_setup_patch_from_text,
    extract_start_setup_session_patch_from_text,
    resolve_mcp_tool_profile_for_quest,
)

_TOOL_EVENT_ARGS_TEXT_LIMIT = 8_000
_TOOL_EVENT_OUTPUT_TEXT_LIMIT = 16_000
_MAX_QUEST_EVENT_JSON_BYTES = 2_000_000
_OVERSIZED_EVENT_PREVIEW_TEXT_LIMIT = 12_000
_BUILTIN_MCP_TOOL_APPROVALS: dict[str, tuple[str, ...]] = {
    "memory": (
        "write",
        "read",
        "search",
        "list_recent",
        "promote_to_global",
    ),
    "artifact": (
        "record",
        "checkpoint",
        "prepare_branch",
        "activate_branch",
        "submit_idea",
        "list_research_branches",
        "resolve_runtime_refs",
        "get_paper_contract_health",
        "validate_manuscript_coverage",
        "get_quest_state",
        "get_global_status",
        "get_method_scoreboard",
        "get_optimization_frontier",
        "read_quest_documents",
        "get_conversation_context",
        "get_analysis_campaign",
        "list_distill_candidates",
        "record_main_experiment",
        "create_analysis_campaign",
        "submit_paper_outline",
        "list_paper_outlines",
        "submit_paper_bundle",
        "record_analysis_slice",
        "publish_baseline",
        "attach_baseline",
        "confirm_baseline",
        "overwrite_baseline",
        "waive_baseline",
        "arxiv",
        "refresh_summary",
        "render_git_graph",
        "interact",
        "complete_quest",
    ),
    "bash_exec": (
        "bash_exec",
    ),
}


def _builtin_mcp_tool_approvals_for_profile(custom_profile: str | None) -> dict[str, tuple[str, ...]]:
    normalized = str(custom_profile or "").strip().lower()
    if normalized == SETTINGS_ISSUE_CUSTOM_PROFILE:
        return {
            "artifact": ("prepare_github_issue",),
            "bash_exec": _BUILTIN_MCP_TOOL_APPROVALS.get("bash_exec", ()),
        }
    if normalized == START_SETUP_PREPARE_PROFILE:
        return {
            "artifact": ("prepare_start_setup_form",),
            "bash_exec": _BUILTIN_MCP_TOOL_APPROVALS.get("bash_exec", ()),
        }
    return _BUILTIN_MCP_TOOL_APPROVALS

_PROVIDER_ENV_CONFLICT_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)
_CHAT_WIRE_TOOL_CALL_GUARD_MARKER = "## Codex Chat-Wire Tool Call Compatibility"
_WINDOWS_GBK_SAFE_REPLACEMENTS: dict[str, str] = {
    "•": "-",
    "…": "...",
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "≤": "<=",
    "≥": ">=",
    "—": "-",
    "–": "-",
    "✓": "[ok]",
    "✗": "[x]",
    "✨": "*",
    "🚀": "[launch]",
    "📄": "[file]",
    "📊": "[chart]",
    "📌": "[pin]",
    "💡": "[idea]",
    "📎": "[attachment]",
    "̀": "",
    "́": "",
}


def _compact_text(value: object, *, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _sanitize_text_for_windows_gbk(text: str) -> tuple[str, dict[str, str]]:
    source = str(text or "")
    if not source:
        return source, {}
    try:
        source.encode("gbk")
        return source, {}
    except UnicodeEncodeError:
        pass

    replacements: dict[str, str] = {}
    rendered: list[str] = []
    for char in source:
        try:
            char.encode("gbk")
            rendered.append(char)
        except UnicodeEncodeError:
            replacement = _WINDOWS_GBK_SAFE_REPLACEMENTS.get(char, "?")
            replacements.setdefault(char, replacement)
            rendered.append(replacement)
    return "".join(rendered), replacements


def _truncate_leaf_text(text: str, *, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(int(limit * 0.7), 256)
    tail = max(limit - head - 64, 128)
    omitted = max(len(text) - head - tail, 0)
    return f"{text[:head].rstrip()}\n...[truncated {omitted} chars]...\n{text[-tail:].lstrip()}"


def _truncate_structured_value(value: object, *, string_limit: int) -> object:
    if isinstance(value, str):
        return _truncate_leaf_text(value.strip(), limit=string_limit)
    if isinstance(value, list):
        return [_truncate_structured_value(item, string_limit=string_limit) for item in value[:200]]
    if isinstance(value, dict):
        truncated: dict[object, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 200:
                truncated["__truncated__"] = f"truncated remaining {len(value) - 200} item(s)"
                break
            truncated[key] = _truncate_structured_value(item, string_limit=string_limit)
        return truncated
    return value


def _structured_text(value: object, *, limit: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _truncate_leaf_text(value.strip(), limit=limit or len(value))
    normalized_value = _truncate_structured_value(value, string_limit=max(limit or _TOOL_EVENT_OUTPUT_TEXT_LIMIT, 512))
    try:
        return json.dumps(normalized_value, ensure_ascii=False, indent=2)
    except TypeError:
        return _truncate_leaf_text(str(value), limit=limit or _TOOL_EVENT_OUTPUT_TEXT_LIMIT)


def _encoded_json_size(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8", errors="ignore"))


def _compact_tool_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _encoded_json_size(payload) <= _MAX_QUEST_EVENT_JSON_BYTES:
        return payload

    compacted = dict(payload)
    output_text = str(compacted.get("output") or "")
    if output_text:
        compacted["output_bytes"] = len(output_text.encode("utf-8", errors="ignore"))
        compacted["output"] = _truncate_leaf_text(
            output_text,
            limit=_OVERSIZED_EVENT_PREVIEW_TEXT_LIMIT,
        )
        compacted["output_truncated"] = True
    args_text = str(compacted.get("args") or "")
    if args_text and _encoded_json_size(compacted) > _MAX_QUEST_EVENT_JSON_BYTES:
        compacted["args"] = _truncate_leaf_text(args_text, limit=4_000)
        compacted["args_truncated"] = True
    if _encoded_json_size(compacted) > _MAX_QUEST_EVENT_JSON_BYTES:
        metadata = compacted.get("metadata")
        if isinstance(metadata, dict):
            allowed_keys = {
                "mcp_server",
                "mcp_tool",
                "bash_id",
                "status",
                "command",
                "workdir",
                "cwd",
                "started_at",
                "finished_at",
                "exit_code",
                "stop_reason",
                "log_path",
            }
            compacted["metadata"] = {
                key: metadata.get(key)
                for key in allowed_keys
                if key in metadata
            }
            compacted["metadata_truncated"] = True
    if _encoded_json_size(compacted) > _MAX_QUEST_EVENT_JSON_BYTES:
        compacted["output"] = _compact_text(compacted.get("output"), limit=2_000)
        compacted["output_truncated"] = True
    return compacted


def _iter_event_texts(event: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in ("text", "content", "message"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value)
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("text", "content", "message"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value)
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    value = block.get("text") or block.get("content")
                    if isinstance(value, str) and value.strip():
                        texts.append(value)
    delta = event.get("delta")
    if isinstance(delta, str) and delta.strip():
        texts.append(delta)
    elif isinstance(delta, dict):
        for key in ("text", "content"):
            value = delta.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value)
    return texts


def _dedupe_texts(values: list[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _web_search_text_payload(item: dict[str, Any]) -> str:
    payload = extract_web_search_payload(item)
    return _compact_text(payload, limit=2400)


def _message_stream_id(event: dict[str, Any], item: dict[str, Any], *, run_id: str, kind: str) -> str:
    for value in (
        event.get("stream_id"),
        item.get("stream_id"),
        event.get("message_id"),
        item.get("message_id"),
        event.get("item_id"),
        item.get("id"),
        event.get("output_item_id"),
        event.get("response_id"),
    ):
        if value:
            return str(value)
    normalized_kind = str(kind or "message").strip().lower() or "message"
    return f"{run_id}:{normalized_kind}"


def _message_id(event: dict[str, Any], item: dict[str, Any], *, stream_id: str) -> str:
    for value in (
        event.get("message_id"),
        item.get("message_id"),
        event.get("item_id"),
        item.get("id"),
        event.get("output_item_id"),
    ):
        if value:
            return str(value)
    return stream_id


def _message_events(
    event: dict[str, Any],
    *,
    quest_id: str,
    run_id: str,
    skill_id: str,
    created_at: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    event_type = str(event.get("type") or "")
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    item_type = str(item.get("type") or event.get("item_type") or "")
    quest_events: list[dict[str, Any]] = []
    output_texts: list[str] = []

    if item_type == "agent_message":
        texts = _dedupe_texts(_iter_event_texts(event))
        stream_id = _message_stream_id(event, item, run_id=run_id, kind="assistant")
        message_id = _message_id(event, item, stream_id=stream_id)
        for text in texts:
            quest_events.append(
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.agent_message",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "source": "codex",
                    "skill_id": skill_id,
                    "text": text,
                    "stream_id": stream_id,
                    "message_id": message_id,
                    "created_at": created_at,
                }
            )
        return quest_events, texts

    if item_type in {"reasoning", "reasoning_summary"} or "reasoning" in event_type:
        texts = _dedupe_texts(_iter_event_texts(event))
        stream_id = _message_stream_id(event, item, run_id=run_id, kind=item_type or "reasoning")
        message_id = _message_id(event, item, stream_id=stream_id)
        for text in texts:
            quest_events.append(
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.reasoning",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "source": "codex",
                    "skill_id": skill_id,
                    "text": text,
                    "stream_id": stream_id,
                    "message_id": message_id,
                    "kind": item_type or "reasoning",
                    "created_at": created_at,
                }
            )
        return quest_events, []

    if item_type:
        return [], []

    if event_type in {"thread.started", "turn.started", "turn.completed"}:
        return [], []

    texts = _dedupe_texts(_iter_event_texts(event))
    stream_id = _message_stream_id(event, item, run_id=run_id, kind="assistant")
    message_id = _message_id(event, item, stream_id=stream_id)
    for text in texts:
        quest_events.append(
            {
                "event_id": generate_id("evt"),
                "type": "runner.delta",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": "codex",
                "skill_id": skill_id,
                "text": text,
                "stream_id": stream_id,
                "message_id": message_id,
                "created_at": created_at,
            }
        )
    return quest_events, texts


def _tool_call_id(event: dict[str, Any], item: dict[str, Any]) -> str:
    for value in (
        item.get("call_id"),
        item.get("tool_call_id"),
        item.get("id"),
        event.get("call_id"),
        event.get("tool_call_id"),
        event.get("id"),
    ):
        if value:
            return str(value)
    return generate_id("tool")


def _tool_name(event: dict[str, Any], item: dict[str, Any]) -> str:
    for value in (
        item.get("name"),
        item.get("function"),
        event.get("name"),
        event.get("function"),
    ):
        if isinstance(value, dict):
            nested = value.get("name")
            if nested:
                return str(nested)
        elif value:
            return str(value)
    return "tool"


def _is_bash_exec_item(event: dict[str, Any], item: dict[str, Any]) -> bool:
    server = str(item.get("server") or event.get("server") or "").strip()
    tool = str(item.get("tool") or event.get("tool") or "").strip()
    return server == "bash_exec" and tool == "bash_exec"


def _tool_args(event: dict[str, Any], item: dict[str, Any]) -> str:
    if _is_bash_exec_item(event, item):
        for value in (
            item.get("arguments"),
            event.get("arguments"),
            item.get("input"),
            event.get("input"),
        ):
            text = _structured_text(value, limit=_TOOL_EVENT_ARGS_TEXT_LIMIT)
            if text:
                return text
        return ""
    for value in (
        item.get("command"),
        item.get("query"),
        item.get("action"),
        item.get("arguments"),
        item.get("input"),
        event.get("arguments"),
        event.get("input"),
        event.get("query"),
        event.get("action"),
        event.get("delta"),
    ):
        text = _compact_text(value, limit=1200)
        if text:
            return text
    return ""


def _tool_output(event: dict[str, Any], item: dict[str, Any]) -> str:
    if _is_bash_exec_item(event, item):
        for value in (
            item.get("result"),
            item.get("output"),
            item.get("content"),
            item.get("error"),
            event.get("result"),
            event.get("output"),
            event.get("content"),
            event.get("error"),
            item.get("aggregated_output"),
            event.get("aggregated_output"),
        ):
            text = _structured_text(value, limit=_TOOL_EVENT_OUTPUT_TEXT_LIMIT)
            if text:
                return text
        return ""
    for value in (
        item.get("aggregated_output"),
        item.get("changes"),
        item.get("output"),
        item.get("result"),
        item.get("content"),
        item.get("error"),
        event.get("aggregated_output"),
        event.get("changes"),
        event.get("output"),
        event.get("result"),
        event.get("content"),
        event.get("error"),
    ):
        text = _compact_text(value, limit=1200)
        if text:
            return text
    return ""


def _mcp_result_payload(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result")
    if isinstance(result, dict):
        structured = result.get("structured_content") or result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        if isinstance(result, dict):
            return result
    return {}


def _mcp_tool_metadata(
    *,
    quest_id: str,
    run_id: str,
    server: str,
    tool: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "mcp_server": server,
        "mcp_tool": tool,
    }
    arguments = item.get("arguments")
    if isinstance(arguments, dict):
        if isinstance(arguments.get("command"), str):
            metadata["command"] = arguments.get("command")
        if isinstance(arguments.get("workdir"), str):
            metadata["workdir"] = arguments.get("workdir")
        if isinstance(arguments.get("mode"), str):
            metadata["mode"] = arguments.get("mode")
        if arguments.get("timeout_seconds") is not None:
            metadata["timeout_seconds"] = arguments.get("timeout_seconds")
        if "comment" in arguments:
            metadata["comment"] = arguments.get("comment")
        if server == "bash_exec" and tool == "bash_exec" and isinstance(arguments.get("id"), str):
            metadata["bash_id"] = arguments.get("id")
    metadata["session_id"] = f"quest:{quest_id}"
    metadata["agent_id"] = "pi"
    metadata["agent_instance_id"] = run_id
    metadata["quest_id"] = quest_id
    result_payload = _mcp_result_payload(item)
    if server == "bash_exec" and tool == "bash_exec" and result_payload:
        for key in (
            "bash_id",
            "status",
            "command",
            "workdir",
            "cwd",
            "kind",
            "comment",
            "started_at",
            "finished_at",
            "exit_code",
            "stop_reason",
            "last_progress",
            "log_path",
            "watchdog_after_seconds",
        ):
            if key in result_payload:
                metadata[key] = result_payload.get(key)
    return metadata


def _tool_event(
    event: dict[str, Any],
    *,
    quest_id: str,
    run_id: str,
    skill_id: str,
    known_tool_names: dict[str, str],
    created_at: str,
) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "")
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    item_type = str(item.get("type") or event.get("item_type") or "")

    if item_type == "command_execution":
        tool_call_id = _tool_call_id(event, item)
        tool_name = "shell_command"
        known_tool_names[tool_call_id] = tool_name
        if event_type == "item.started" or str(item.get("status") or "") == "in_progress":
            return {
                "event_id": generate_id("evt"),
                "type": "runner.tool_call",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": "codex",
                "skill_id": skill_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "calling",
                "args": _tool_args(event, item),
                "raw_event_type": event_type,
                "created_at": created_at,
            }
        return _compact_tool_event_payload({
            "event_id": generate_id("evt"),
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": str(item.get("status") or "completed"),
            "args": _tool_args(event, item),
            "output": _tool_output(event, item),
            "raw_event_type": event_type,
            "created_at": created_at,
        })

    if item_type == "web_search":
        tool_call_id = _tool_call_id(event, item)
        tool_name = "web_search"
        search_payload = extract_web_search_payload(item)
        metadata = {"search": search_payload}
        known_tool_names[tool_call_id] = tool_name
        if event_type == "item.started":
            return {
                "event_id": generate_id("evt"),
                "type": "runner.tool_call",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": "codex",
                "skill_id": skill_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "calling",
                "args": _web_search_text_payload(item),
                "metadata": metadata,
                "raw_event_type": event_type,
                "created_at": created_at,
            }
        return _compact_tool_event_payload({
            "event_id": generate_id("evt"),
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": "completed",
            "args": _web_search_text_payload(item),
            "output": _web_search_text_payload(item),
            "metadata": metadata,
            "raw_event_type": event_type,
            "created_at": created_at,
        })

    if item_type == "file_change":
        tool_call_id = _tool_call_id(event, item)
        tool_name = "file_change"
        known_tool_names[tool_call_id] = tool_name
        return _compact_tool_event_payload({
            "event_id": generate_id("evt"),
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": str(item.get("status") or "completed"),
            "output": _tool_output(event, item),
            "raw_event_type": event_type,
            "created_at": created_at,
        })

    if item_type == "mcp_tool_call":
        tool_call_id = _tool_call_id(event, item)
        server = str(item.get("server") or "").strip()
        tool = str(item.get("tool") or "").strip()
        tool_name = f"{server}.{tool}" if server and tool else tool or server or "mcp_tool"
        metadata = _mcp_tool_metadata(
            quest_id=quest_id,
            run_id=run_id,
            server=server,
            tool=tool,
            item=item,
        )
        known_tool_names[tool_call_id] = tool_name
        if event_type == "item.started" or str(item.get("status") or "") == "in_progress":
            return {
                "event_id": generate_id("evt"),
                "type": "runner.tool_call",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": "codex",
                "skill_id": skill_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "calling",
                "args": _tool_args(event, item),
                "mcp_server": server,
                "mcp_tool": tool,
                "metadata": metadata,
                "raw_event_type": event_type,
                "created_at": created_at,
            }
        return _compact_tool_event_payload({
            "event_id": generate_id("evt"),
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": str(item.get("status") or "completed"),
            "args": _tool_args(event, item),
            "output": _tool_output(event, item),
            "mcp_server": server,
            "mcp_tool": tool,
            "metadata": metadata,
            "raw_event_type": event_type,
            "created_at": created_at,
        })

    if item_type in {"function_call", "custom_tool_call", "tool_call"} or "function_call" in event_type or "tool_call" in event_type:
        tool_call_id = _tool_call_id(event, item)
        tool_name = _tool_name(event, item)
        known_tool_names[tool_call_id] = tool_name
        return {
            "event_id": generate_id("evt"),
            "type": "runner.tool_call",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": "calling" if "delta" in event_type or "added" in event_type else "completed",
            "args": _tool_args(event, item),
            "raw_event_type": event_type,
            "created_at": created_at,
        }

    if item_type in {"function_call_output", "custom_tool_call_output", "tool_result", "tool_call_output"} or "function_call_output" in event_type or "tool_result" in event_type:
        tool_call_id = _tool_call_id(event, item)
        tool_name = known_tool_names.get(tool_call_id) or _tool_name(event, item)
        return _compact_tool_event_payload({
            "event_id": generate_id("evt"),
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": run_id,
            "source": "codex",
            "skill_id": skill_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": "completed",
            "args": _tool_args(event, item),
            "output": _tool_output(event, item),
            "raw_event_type": event_type,
            "created_at": created_at,
        })

    return None


class CodexRunner:
    def __init__(
        self,
        *,
        home: Path,
        repo_root: Path,
        binary: str,
        logger: JsonlLogger,
        prompt_builder: PromptBuilder,
        artifact_service: ArtifactService,
    ) -> None:
        self.home = home
        self.repo_root = repo_root
        self.binary = binary
        self.logger = logger
        self.prompt_builder = prompt_builder
        self.artifact_service = artifact_service
        self._process_lock = threading.Lock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}

    @staticmethod
    def _subprocess_popen_kwargs(*, workspace_root: Path, env: dict[str, str]) -> dict[str, Any]:
        return {
            "cwd": str(workspace_root),
            "env": env,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            **process_session_popen_kwargs(hide_window=True),
        }

    def run(self, request: RunRequest) -> RunResult:
        workspace_root = request.worktree_root or request.quest_root
        run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
        history_root = ensure_dir(request.quest_root / ".ds" / "codex_history" / request.run_id)
        runner_config = self._load_runner_config()
        prompt = self.prompt_builder.build(
            quest_id=request.quest_id,
            skill_id=request.skill_id,
            user_message=request.message,
            model=request.model,
            turn_reason=request.turn_reason,
            turn_intent=request.turn_intent,
            turn_mode=request.turn_mode,
            retry_context=request.retry_context,
        )
        prompt = self._apply_chat_wire_tool_call_guard(prompt, runner_config=runner_config)
        prompt_to_send = prompt
        prompt_sanitization: dict[str, str] = {}
        sanitized_prompt_path: str | None = None
        if os.name == "nt":
            prompt_to_send, prompt_sanitization = _sanitize_text_for_windows_gbk(prompt)
        write_text(run_root / "prompt.md", prompt)
        if prompt_sanitization:
            sanitized_path = run_root / "prompt.windows-gbk-sanitized.md"
            write_text(sanitized_path, prompt_to_send)
            sanitized_prompt_path = str(sanitized_path)

        codex_home = self._prepare_project_codex_home(
            workspace_root,
            quest_root=request.quest_root,
            quest_id=request.quest_id,
            run_id=request.run_id,
            runner_config=runner_config,
        )
        command = self._build_command(request, prompt_to_send, runner_config=runner_config)
        write_json(
            run_root / "command.json",
            {
                "command": command,
                "codex_home": str(codex_home),
                "quest_root": str(request.quest_root),
                "workspace_root": str(workspace_root),
                "cwd": str(workspace_root),
                "turn_reason": request.turn_reason,
                "turn_intent": request.turn_intent,
                "turn_mode": request.turn_mode,
                "windows_gbk_prompt_sanitized": bool(prompt_sanitization),
                "windows_gbk_sanitized_prompt_path": sanitized_prompt_path,
                "windows_gbk_replacements": prompt_sanitization,
            },
        )

        env = dict(**os.environ)
        runner_env = runner_config.get("env") if isinstance(runner_config.get("env"), dict) else {}
        for key, value in runner_env.items():
            env_key = str(key or "").strip()
            if not env_key or value is None:
                continue
            env_value = str(value)
            if env_value == "":
                continue
            env[env_key] = env_value
        env["CODEX_HOME"] = str(codex_home)
        env = self._sanitize_provider_env(env, runner_config=runner_config)
        env["DEEPSCIENTIST_HOME"] = str(self.home)
        env["DEEPSCIENTIST_REPO_ROOT"] = str(self.repo_root)
        env["DS_HOME"] = str(self.home)
        env["DS_QUEST_ID"] = request.quest_id
        env["DS_QUEST_ROOT"] = str(request.quest_root)
        env["DS_WORKTREE_ROOT"] = str(workspace_root)
        env["DS_RUN_ID"] = request.run_id
        env["DS_TURN_REASON"] = request.turn_reason
        env["DS_TURN_INTENT"] = request.turn_intent
        env["DS_TURN_MODE"] = request.turn_mode
        quest_yaml = read_yaml(request.quest_root / "quest.yaml", {})
        env["DS_ACTIVE_ANCHOR"] = str(quest_yaml.get("active_anchor", "baseline"))
        env["DS_CONVERSATION_ID"] = f"quest:{request.quest_id}"
        env["DS_AGENT_ROLE"] = request.skill_id
        env["DS_TEAM_MODE"] = "single"
        env = ensure_utf8_subprocess_env(env)
        popen_kwargs = self._subprocess_popen_kwargs(workspace_root=workspace_root, env=env)
        process = subprocess.Popen(command, **popen_kwargs)
        with self._process_lock:
            self._active_processes[request.quest_id] = process
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        try:
            history_events = history_root / "events.jsonl"
            stdout_events = run_root / "stdout.jsonl"
            quest_events = request.quest_root / ".ds" / "events.jsonl"
            known_tool_names: dict[str, str] = {}

            append_jsonl(
                quest_events,
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_start",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "created_at": utc_now(),
                },
            )
            if prompt_sanitization:
                append_jsonl(
                    quest_events,
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.prompt_sanitized",
                        "quest_id": request.quest_id,
                        "run_id": request.run_id,
                        "source": "codex",
                        "skill_id": request.skill_id,
                        "summary": (
                            "Windows GBK-compatible prompt sanitization replaced non-encodable characters "
                            "before sending the prompt to Codex."
                        ),
                        "replacements": prompt_sanitization,
                        "created_at": utc_now(),
                    },
                )

            try:
                process.stdin.write(prompt_to_send)
            except UnicodeEncodeError as exc:
                if os.name == "nt" and not prompt_sanitization:
                    prompt_to_send, prompt_sanitization = _sanitize_text_for_windows_gbk(prompt)
                    if not prompt_sanitization:
                        raise exc
                    sanitized_path = run_root / "prompt.windows-gbk-sanitized.md"
                    write_text(sanitized_path, prompt_to_send)
                    append_jsonl(
                        quest_events,
                        {
                            "event_id": generate_id("evt"),
                            "type": "runner.prompt_sanitized",
                            "quest_id": request.quest_id,
                            "run_id": request.run_id,
                            "source": "codex",
                            "skill_id": request.skill_id,
                            "summary": (
                                "Windows GBK-compatible prompt sanitization retried after a UnicodeEncodeError "
                                "while writing the prompt to Codex."
                            ),
                            "replacements": prompt_sanitization,
                            "created_at": utc_now(),
                        },
                    )
                    process.stdin.write(prompt_to_send)
                else:
                    raise exc
            process.stdin.close()

            output_parts: list[str] = []
            final_output_parts: list[str] = []

            for raw_line in process.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = {"raw": line}
                timestamp = utc_now()
                append_jsonl(history_events, {"timestamp": timestamp, "event": payload})
                append_jsonl(stdout_events, {"timestamp": timestamp, "line": line})
                try:
                    self.artifact_service.quest_service.schedule_projection_refresh(
                        request.quest_root,
                        kinds=("details",),
                    )
                except Exception:
                    pass
                tool_event = _tool_event(
                    payload,
                    quest_id=request.quest_id,
                    run_id=request.run_id,
                    skill_id=request.skill_id,
                    known_tool_names=known_tool_names,
                    created_at=timestamp,
                )
                if tool_event is not None:
                    append_jsonl(quest_events, tool_event)
                message_events, message_output_parts = _message_events(
                    payload,
                    quest_id=request.quest_id,
                    run_id=request.run_id,
                    skill_id=request.skill_id,
                    created_at=timestamp,
                )
                for message_event in message_events:
                    append_jsonl(quest_events, message_event)
                    if message_event.get("type") == "runner.agent_message":
                        text = message_event.get("text")
                        if isinstance(text, str) and text.strip():
                            final_output_parts.append(text.strip())
                output_parts.extend(message_output_parts)

            stderr_text = process.stderr.read()
            exit_code = process.wait()
            summary_text = "\n".join(part.strip() for part in output_parts if part.strip()).strip()
            output_text = (
                next(
                    (
                        part.strip()
                        for part in reversed(final_output_parts)
                        if isinstance(part, str) and part.strip()
                    ),
                    "",
                )
                or summary_text
            )
            self._apply_start_setup_patch_fallback_if_present(
                request=request,
                output_text=output_text,
                quest_events=quest_events,
            )
            append_jsonl(
                quest_events,
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_finish",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "codex",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "exit_code": exit_code,
                    "stderr_text": stderr_text[:2000],
                    "summary": (summary_text or output_text)[:1000],
                    "created_at": utc_now(),
                },
            )
            write_text(history_root / "assistant.md", (output_text or "") + ("\n" if output_text else ""))
            write_text(run_root / "stderr.txt", stderr_text)
            result_payload = {
                "ok": exit_code == 0,
                "run_id": request.run_id,
                "model": request.model,
                "exit_code": exit_code,
                "history_root": str(history_root),
                "run_root": str(run_root),
                "output_text": output_text,
                "stderr_text": stderr_text,
                "completed_at": utc_now(),
            }
            write_json(run_root / "result.json", result_payload)
            write_json(history_root / "meta.json", result_payload)
            try:
                self.artifact_service.quest_service.schedule_projection_refresh(
                    request.quest_root,
                    kinds=("details",),
                    throttle_seconds=0.0,
                )
            except Exception:
                pass
            self.logger.log(
                "info",
                "runner.codex.completed",
                quest_id=request.quest_id,
                run_id=request.run_id,
                model=request.model,
                exit_code=exit_code,
            )
            artifact_result = self.artifact_service.record(
                request.quest_root,
                {
                    "kind": "run",
                    "status": "completed" if exit_code == 0 else "failed",
                    "run_id": request.run_id,
                    "run_kind": request.skill_id,
                    "model": request.model,
                    "summary": (summary_text or output_text)[:1000],
                    "history_root": str(history_root),
                    "run_root": str(run_root),
                    "exit_code": exit_code,
                },
                workspace_root=workspace_root,
                commit_message=f"run: {request.skill_id} {request.run_id}",
            )
            export_git_graph(request.quest_root, request.quest_root / "artifacts" / "graphs")
            write_json(run_root / "artifact.json", artifact_result)
            return RunResult(
                ok=exit_code == 0,
                run_id=request.run_id,
                model=request.model,
                output_text=output_text,
                exit_code=exit_code,
                history_root=history_root,
                run_root=run_root,
                stderr_text=stderr_text,
            )
        finally:
            with self._process_lock:
                if self._active_processes.get(request.quest_id) is process:
                    self._active_processes.pop(request.quest_id, None)

    def interrupt(self, quest_id: str) -> bool:
        with self._process_lock:
            process = self._active_processes.get(quest_id)
        if process is None or process.poll() is not None:
            return False

        interrupted = False
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                interrupted = True
            except (AttributeError, OSError, ValueError):
                interrupted = False
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                interrupted = True
            except (OSError, ProcessLookupError):
                interrupted = False

        if not interrupted:
            try:
                process.terminate()
                interrupted = True
            except OSError:
                return False

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                try:
                    process.kill()
                except OSError:
                    return interrupted
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    try:
                        process.kill()
                    except OSError:
                        return interrupted
            process.wait(timeout=3)
        return interrupted

    def _apply_start_setup_patch_fallback_if_present(
        self,
        *,
        request: RunRequest,
        output_text: str,
        quest_events: Path,
    ) -> None:
        quest_yaml = read_yaml(request.quest_root / "quest.yaml", {})
        startup_contract = quest_yaml.get("startup_contract") if isinstance(quest_yaml.get("startup_contract"), dict) else {}
        if not isinstance(startup_contract.get("start_setup_session"), dict):
            return
        patch = extract_start_setup_patch_from_text(output_text)
        session_patch = extract_start_setup_session_patch_from_text(output_text)
        if not patch and not session_patch:
            return
        result = self.artifact_service.apply_start_setup_form_patch(
            request.quest_root,
            form_patch=patch,
            session_patch=session_patch,
            message="Applied from runner fallback `start_setup_patch` block.",
        )
        patch_keys = sorted(result.get("form_patch", {}).keys()) if isinstance(result.get("form_patch"), dict) else sorted((patch or {}).keys())
        append_jsonl(
            quest_events,
            {
                "event_id": generate_id("evt"),
                "type": "runner.turn_postprocess_info",
                "quest_id": request.quest_id,
                "run_id": request.run_id,
                "source": "codex",
                "skill_id": request.skill_id,
                "summary": (
                    "Applied the fenced `start_setup_patch` fallback block to the quest startup form "
                    "so the suggested form stays synchronized even when Codex answered with a patch block "
                    "instead of a direct MCP tool call."
                ),
                "details": {
                    "warning_code": "start_setup_patch_fallback_applied",
                    "patch_keys": patch_keys,
                },
                "created_at": utc_now(),
            },
        )

    def _build_command(self, request: RunRequest, prompt: str, *, runner_config: dict[str, Any] | None = None) -> list[str]:
        workspace_root = request.worktree_root or request.quest_root
        resolved_binary = resolve_runner_binary(self.binary, runner_name="codex")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        profile = str(resolved_runner_config.get("profile") or "").strip()
        normalized_model = str(request.model or "").strip()
        if profile and normalized_model.lower() not in {"", "inherit", "default", "codex-default"}:
            normalized_model = "inherit"
        command = [
            resolved_binary or self.binary,
            "--search",
        ]
        if profile:
            command.extend(["--profile", profile])
        command.extend(
            [
                "exec",
                "--json",
                "--cd",
                str(workspace_root),
                "--skip-git-repo-check",
            ]
        )
        if normalized_model.lower() not in {"", "inherit", "default", "codex-default"}:
            command.extend(["--model", normalized_model])
        if request.approval_policy:
            command.extend(["-c", f'approval_policy="{request.approval_policy}"'])
        reasoning_effort, _ = normalize_codex_reasoning_effort(
            request.reasoning_effort,
            resolved_binary=resolved_binary or self.binary,
        )
        if reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
        tool_timeout_sec = self._positive_timeout_seconds(resolved_runner_config.get("mcp_tool_timeout_sec"))
        if tool_timeout_sec is not None:
            timeout_value = int(tool_timeout_sec) if float(tool_timeout_sec).is_integer() else float(tool_timeout_sec)
            custom_profile = resolve_mcp_tool_profile_for_quest(request.quest_root)
            server_names = builtin_mcp_server_names_for_custom_profile(custom_profile)
            for server_name in server_names:
                command.extend(["-c", f"mcp_servers.{server_name}.tool_timeout_sec={timeout_value}"])
        if request.sandbox_mode:
            command.extend(["--sandbox", request.sandbox_mode])
        command.append("-")
        return command

    def _apply_chat_wire_tool_call_guard(
        self,
        prompt: str,
        *,
        runner_config: dict[str, Any] | None = None,
    ) -> str:
        prompt_text = str(prompt or "")
        if not prompt_text or _CHAT_WIRE_TOOL_CALL_GUARD_MARKER in prompt_text:
            return prompt_text

        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        profile = str(resolved_runner_config.get("profile") or "").strip()
        if not profile:
            return prompt_text
        config_home = str(resolved_runner_config.get("config_dir") or os.environ.get("CODEX_HOME") or "").strip()
        if not config_home:
            return prompt_text

        metadata = active_provider_metadata_from_home(config_home, profile=profile or None)
        wire_api = str(metadata.get("wire_api") or "").strip().lower()
        if wire_api != "chat":
            return prompt_text

        provider = str(metadata.get("provider") or "").strip() or "unknown"
        guard_lines = [
            _CHAT_WIRE_TOOL_CALL_GUARD_MARKER,
            f"active_provider_profile: {profile}",
            f"active_provider_name: {provider}",
            "active_provider_wire_api: chat",
            "single_tool_call_per_turn_rule: emit at most one tool call in each assistant message.",
            "tool_call_serialization_rule: after each tool result, decide whether to make the next tool call or produce the answer.",
            "no_batched_mcp_rule: never bundle multiple `artifact.*`, `memory.*`, or `bash_exec.*` calls into the same response, even when the reads look independent.",
            "no_immediate_repeat_rule: if a tool already returned the information needed for the current subtask, do not immediately call that same tool again; move to the next tool or answer.",
            "state_recovery_preference_rule: on a fresh quest turn, prefer `artifact.get_quest_state`, `artifact.read_quest_documents`, and `memory.list_recent` to recover context before reaching for `bash_exec`.",
            "bash_exec_after_context_rule: use `bash_exec` only after you know the exact command you need and why the `artifact` / `memory` path is insufficient.",
            "tool_call_json_rule: every tool call must contain exactly one complete JSON object argument with no trailing characters.",
        ]
        guard_block = "\n".join(guard_lines)
        return f"{prompt_text.rstrip()}\n\n{guard_block}\n"

    def _prepare_project_codex_home(
        self,
        workspace_root: Path,
        *,
        quest_root: Path,
        quest_id: str,
        run_id: str,
        runner_config: dict[str, Any] | None = None,
    ) -> Path:
        target = ensure_dir(workspace_root / ".ds" / "codex-home")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        configured_home = str(resolved_runner_config.get("config_dir") or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
        profile = str(resolved_runner_config.get("profile") or "").strip()
        materialize_codex_runtime_home(
            source_home=configured_home,
            target_home=target,
            profile=profile,
            quest_codex_root=quest_root / ".codex",
        )
        self._inject_built_in_mcp(
            target,
            quest_root=quest_root,
            workspace_root=workspace_root,
            quest_id=quest_id,
            run_id=run_id,
            runner_config=runner_config,
        )
        return target

    def _inject_built_in_mcp(
        self,
        codex_home: Path,
        *,
        quest_root: Path,
        workspace_root: Path,
        quest_id: str,
        run_id: str,
        runner_config: dict[str, Any] | None = None,
    ) -> None:
        config_path = codex_home / "config.toml"
        existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        marker_start = "# BEGIN DEEPSCIENTIST BUILTINS"
        marker_end = "# END DEEPSCIENTIST BUILTINS"
        if marker_start in existing and marker_end in existing:
            prefix = existing.split(marker_start, 1)[0].rstrip()
        else:
            prefix = existing.rstrip()

        pythonpath = os.environ.get("PYTHONPATH", "")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        tool_timeout_sec = self._positive_timeout_seconds(resolved_runner_config.get("mcp_tool_timeout_sec"))

        shared_env = ensure_utf8_subprocess_env({
            "DEEPSCIENTIST_HOME": str(self.home),
            "DEEPSCIENTIST_REPO_ROOT": str(self.repo_root),
            "DS_HOME": str(self.home),
            "DS_QUEST_ID": quest_id,
            "DS_QUEST_ROOT": str(quest_root),
            "DS_WORKTREE_ROOT": str(workspace_root),
            "DS_RUN_ID": run_id,
            "DS_WORKER_ID": run_id,
            "DS_ACTIVE_ANCHOR": str(read_yaml(quest_root / "quest.yaml", {}).get("active_anchor", "baseline")),
            "DS_CONVERSATION_ID": f"quest:{quest_id}",
            "DS_AGENT_ROLE": "pi",
            "DS_TEAM_MODE": "single",
        })
        custom_profile = resolve_mcp_tool_profile_for_quest(quest_root)
        if custom_profile:
            shared_env["DS_CUSTOM_PROFILE"] = custom_profile
        if pythonpath:
            shared_env["PYTHONPATH"] = pythonpath

        server_names = builtin_mcp_server_names_for_custom_profile(custom_profile)
        tool_approvals = _builtin_mcp_tool_approvals_for_profile(custom_profile)
        block = "\n".join(
            [marker_start]
            + [
                item
                for index, name in enumerate(server_names)
                for item in (
                    [self._mcp_block(name, shared_env, tool_timeout_sec=tool_timeout_sec, approvals=tool_approvals.get(name, ()))]
                    + ([""] if index < len(server_names) - 1 else [])
                )
            ]
            + [marker_end]
        ).strip()
        new_text = f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"
        write_text(config_path, new_text)

    @staticmethod
    def _mcp_block(
        name: str,
        env: dict[str, str],
        *,
        tool_timeout_sec: float | None = None,
        approvals: tuple[str, ...] = (),
    ) -> str:
        args = ["-m", "deepscientist.mcp.server", "--namespace", name]
        lines = [
            f"[mcp_servers.{name}]",
            'transport = "stdio"',
            f'command = "{sys.executable}"',
            f"args = [{', '.join(json.dumps(item) for item in args)}]",
        ]
        if tool_timeout_sec is not None:
            value = int(tool_timeout_sec) if float(tool_timeout_sec).is_integer() else float(tool_timeout_sec)
            lines.append(f"tool_timeout_sec = {value}")
        lines.extend(
            [
                "",
                f"[mcp_servers.{name}.env]",
            ]
        )
        for key, value in env.items():
            lines.append(f"{key} = {json.dumps(value)}")
        for tool_name in approvals:
            lines.extend(
                [
                    "",
                    f"[mcp_servers.{name}.tools.{tool_name}]",
                    'approval_mode = "approve"',
                ]
            )
        return "\n".join(lines)

    def _load_runner_config(self) -> dict[str, Any]:
        try:
            runners_cfg = ConfigManager(self.home).load_runners_config()
        except OSError:
            return {}
        codex_cfg = runners_cfg.get("codex")
        return codex_cfg if isinstance(codex_cfg, dict) else {}

    @staticmethod
    def _positive_timeout_seconds(value: object) -> float | None:
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return None
        return timeout if timeout > 0 else None

    @staticmethod
    def _sanitize_provider_env(
        env: dict[str, str],
        *,
        runner_config: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else {}
        profile = str(resolved_runner_config.get("profile") or "").strip()
        config_home = str(resolved_runner_config.get("config_dir") or env.get("CODEX_HOME") or "").strip()
        if not config_home:
            return env
        metadata = active_provider_metadata_from_home(config_home, profile=profile or None)
        requires_openai_auth = metadata.get("requires_openai_auth")
        if requires_openai_auth is not False:
            return env
        sanitized = dict(env)
        for key in _PROVIDER_ENV_CONFLICT_KEYS:
            sanitized.pop(key, None)
        return sanitized
