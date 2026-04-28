from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .shared import ensure_dir, read_json, utc_now, write_json

DEFAULT_EVIDENCE_PACKET_THRESHOLD_BYTES = 48_000
DEFAULT_RUNNER_TOOL_RESULT_THRESHOLD_BYTES = 8_000
_MAX_SUMMARY_CHARS = 900
_MAX_BLOCKERS = 12


def payload_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        return str(payload).encode("utf-8", errors="replace")


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(payload_json_bytes(payload)).hexdigest()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return normalized.strip("-")[:80] or "payload"


def _sidecar_path(
    *,
    quest_root: Path,
    run_id: str | None,
    tool_name: str,
    payload_hash: str,
    item_id: str | None = None,
) -> Path:
    run_segment = _slug(run_id or "manual")
    item_segment = _slug(item_id or payload_hash[:12])
    tool_segment = _slug(tool_name)
    return quest_root / ".ds" / "evidence_packets" / run_segment / f"{tool_segment}-{item_segment}.json"


def _collect_blockers(value: Any, blockers: list[str]) -> None:
    if len(blockers) >= _MAX_BLOCKERS:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key or "").lower()
            if any(marker in lowered for marker in ("block", "gap", "missing", "error", "invalid", "unresolved")):
                if isinstance(item, str) and item.strip():
                    blockers.append(item.strip())
                elif isinstance(item, list):
                    for child in item:
                        if len(blockers) >= _MAX_BLOCKERS:
                            break
                        if isinstance(child, str) and child.strip():
                            blockers.append(child.strip())
                        elif isinstance(child, dict):
                            title = str(child.get("title") or child.get("summary") or child.get("reason") or "").strip()
                            status = str(child.get("status") or "").strip()
                            if title:
                                blockers.append(f"{status}: {title}".strip(": "))
                elif isinstance(item, dict):
                    title = str(item.get("title") or item.get("summary") or item.get("reason") or "").strip()
                    if title:
                        blockers.append(title)
            if isinstance(item, (dict, list)):
                _collect_blockers(item, blockers)
            if len(blockers) >= _MAX_BLOCKERS:
                break
    elif isinstance(value, list):
        for item in value:
            _collect_blockers(item, blockers)
            if len(blockers) >= _MAX_BLOCKERS:
                break


def extract_key_blockers(payload: Any) -> list[str]:
    blockers: list[str] = []
    _collect_blockers(payload, blockers)
    seen: set[str] = set()
    ordered: list[str] = []
    for blocker in blockers:
        text = " ".join(str(blocker).split())
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text[:240])
        if len(ordered) >= _MAX_BLOCKERS:
            break
    return ordered


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return None


def summarize_payload(payload: Any, *, tool_name: str) -> str:
    if not isinstance(payload, dict):
        text = str(payload).strip()
        return (text[: _MAX_SUMMARY_CHARS - 1].rstrip() + "...") if len(text) > _MAX_SUMMARY_CHARS else text

    parts: list[str] = []
    ok_value = payload.get("ok")
    if isinstance(ok_value, bool):
        parts.append(f"ok={ok_value}")
    status = _first_text(payload, ("status", "state", "detail", "summary", "message"))
    if status:
        parts.append(f"status={status}")
    for key in ("count", "total", "item_count", "log_line_count"):
        if key in payload and isinstance(payload.get(key), int | float | str):
            parts.append(f"{key}={payload.get(key)}")
    for key in ("items", "results", "entries", "files"):
        value = payload.get(key)
        if isinstance(value, list):
            parts.append(f"{key}={len(value)}")
            break

    blockers = extract_key_blockers(payload)
    if blockers:
        parts.append(f"key_blockers={len(blockers)}")
        parts.append(f"first_blocker={blockers[0]}")

    summary = f"{tool_name}: " + "; ".join(str(part) for part in parts if str(part).strip())
    if summary.strip() == f"{tool_name}:":
        summary = f"{tool_name}: compact evidence packet available in sidecar."
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[: _MAX_SUMMARY_CHARS - 3].rstrip() + "..."
    return summary


def compact_evidence_payload(
    payload: Any,
    *,
    quest_root: Path,
    run_id: str | None,
    tool_name: str,
    detail: str | None = None,
    item_id: str | None = None,
    force: bool = False,
    threshold_bytes: int = DEFAULT_EVIDENCE_PACKET_THRESHOLD_BYTES,
    reason: str | None = None,
    full_detail_requested: bool | None = None,
) -> tuple[Any, dict[str, Any]]:
    payload_bytes = len(payload_json_bytes(payload))
    threshold = max(1, int(threshold_bytes))
    if not force and payload_bytes <= threshold:
        return payload, {
            "compacted": False,
            "payload_bytes": payload_bytes,
            "threshold_bytes": threshold,
        }

    digest = payload_sha256(payload)
    sidecar_path = _sidecar_path(
        quest_root=quest_root,
        run_id=run_id,
        tool_name=tool_name,
        payload_hash=digest,
        item_id=item_id,
    )
    ensure_dir(sidecar_path.parent)
    key_blockers = extract_key_blockers(payload)
    summary = summarize_payload(payload, tool_name=tool_name)
    write_json(
        sidecar_path,
        {
            "version": 1,
            "created_at": utc_now(),
            "tool_name": tool_name,
            "detail": detail,
            "summary": summary,
            "key_blockers": key_blockers,
            "payload_sha256": digest,
            "payload_bytes": payload_bytes,
            "payload": payload,
        },
    )
    index_path = sidecar_path.parent / "index.json"
    existing_index = read_json(index_path, {})
    existing_items = (
        [dict(item) for item in (existing_index.get("items") or []) if isinstance(item, dict)]
        if isinstance(existing_index, dict)
        else []
    )
    entry = {
        "tool_name": tool_name,
        "detail": detail,
        "summary": summary,
        "sidecar_path": str(sidecar_path),
        "payload_sha256": digest,
        "payload_bytes": payload_bytes,
        "key_blockers": key_blockers,
        "created_at": utc_now(),
    }
    write_json(
        index_path,
        {
            "version": 1,
            "updated_at": utc_now(),
            "run_id": run_id,
            "items": [*existing_items, entry][-200:],
        },
    )
    evidence_packet = {
        "version": 1,
        "tool_name": tool_name,
        "detail": detail,
        "summary": summary,
        "sidecar_path": str(sidecar_path),
        "index_path": str(index_path),
        "payload_sha256": digest,
        "payload_bytes": payload_bytes,
        "key_blockers": key_blockers,
        "full_detail_requested": bool(full_detail_requested),
        "compaction_reason": reason or "context_budget",
        "drill_down_rule": "Read sidecar_path only when the compact facts are insufficient for the next decision.",
    }
    compacted = {
        "ok": bool(payload.get("ok")) if isinstance(payload, dict) and isinstance(payload.get("ok"), bool) else True,
        "compacted": True,
        "evidence_packet": evidence_packet,
    }
    return compacted, {
        "compacted": True,
        "sidecar_path": str(sidecar_path),
        "payload_sha256": digest,
        "payload_bytes": payload_bytes,
        "summary": summary,
        "key_blocker_count": len(key_blockers),
    }


def compact_runner_tool_event(
    event: dict[str, Any],
    *,
    quest_root: Path,
    run_id: str,
    threshold_bytes: int = DEFAULT_RUNNER_TOOL_RESULT_THRESHOLD_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if str(event.get("type") or "") != "runner.tool_result":
        return event, {"compacted": False}
    output = str(event.get("output") or "")
    tool_name = str(event.get("tool_name") or event.get("mcp_tool") or "tool").strip() or "tool"
    args = str(event.get("args") or "")
    full_detail_requested = "detail" in args and "full" in args.lower()
    output_bytes = len(output.encode("utf-8", errors="replace"))
    if output_bytes <= max(1, int(threshold_bytes)):
        return event, {
            "compacted": False,
            "output_bytes": output_bytes,
            "threshold_bytes": int(threshold_bytes),
        }

    parsed_payload: Any
    try:
        parsed_payload = json.loads(output)
    except json.JSONDecodeError:
        parsed_payload = {"text": output}
    compacted_payload, meta = compact_evidence_payload(
        parsed_payload,
        quest_root=quest_root,
        run_id=run_id,
        tool_name=tool_name,
        item_id=str(event.get("event_id") or event.get("tool_call_id") or ""),
        force=True,
        threshold_bytes=threshold_bytes,
        reason="runner_tool_result_context_budget",
        full_detail_requested=full_detail_requested,
    )
    compacted_event = dict(event)
    compacted_event["output"] = json.dumps(compacted_payload, ensure_ascii=False, indent=2)
    compacted_event["output_bytes"] = output_bytes
    compacted_event["output_sha256"] = hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()
    compacted_event["output_compacted"] = True
    compacted_event["evidence_packet"] = (
        compacted_payload.get("evidence_packet") if isinstance(compacted_payload, dict) else None
    )
    return compacted_event, {
        **meta,
        "output_bytes": output_bytes,
    }
