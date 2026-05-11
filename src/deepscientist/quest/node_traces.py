from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..shared import ensure_dir, read_json, sha256_text, utc_now, write_json

NODE_TRACE_SCHEMA_VERSION = 2


def _format_state_label(value: str | None) -> str:
    normalized = str(value or "").strip().replace("_", " ").replace("-", " ")
    if not normalized:
        return "Unknown"
    return " ".join(part.capitalize() for part in normalized.split())


def _compact_text(value: object, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            text = str(value)
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize_branch_name(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _infer_stage_from_branch_name(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("analysis/"):
        return "analysis"
    if normalized.startswith("run/"):
        return "experiment"
    if normalized.startswith("idea/"):
        return "idea"
    if normalized.startswith("paper/") or normalized.startswith("write/"):
        return "writing"
    if normalized.startswith("baseline/"):
        return "baseline"
    return None


def _infer_stage_from_skill(skill_id: object) -> str | None:
    normalized = str(skill_id or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"scout", "research", "literature"}:
        return "scout"
    if normalized.startswith("baseline"):
        return "baseline"
    if normalized in {"idea", "scout+idea"}:
        return "idea"
    if normalized == "experiment":
        return "experiment"
    if normalized in {"analysis-campaign", "analysis", "analysis_slice"}:
        return "analysis"
    if normalized in {"write", "finalize"}:
        return "writing"
    if normalized == "decision":
        return "decision"
    return normalized


def _infer_stage_from_event_type(event_type: object) -> str | None:
    normalized = str(event_type or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("research."):
        return "scout"
    if normalized.startswith("baseline."):
        return "baseline"
    if normalized.startswith("idea."):
        return "idea"
    if normalized.startswith("experiment."):
        return "experiment"
    if normalized.startswith("write."):
        return "writing"
    if normalized.startswith("decision.") or normalized.startswith("pi."):
        return "decision"
    return None


def _infer_stage_from_artifact(record: dict[str, Any]) -> str | None:
    explicit = _infer_stage_from_skill(record.get("stage_key"))
    if explicit:
        return explicit
    explicit = _infer_stage_from_skill(record.get("skill_id"))
    if explicit:
        return explicit
    explicit = _infer_stage_from_skill(record.get("run_kind"))
    if explicit:
        return explicit
    kind = str(record.get("kind") or "").strip().lower()
    if kind.startswith("science."):
        return "science"
    if kind == "baseline":
        return "baseline"
    if kind in {"decision", "approval"}:
        return "decision"
    if kind in {"report", "paper", "draft"}:
        return "writing"
    return None


def _load_artifact_record(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".json":
        return None
    payload = read_json(path, {})
    if isinstance(payload, dict) and payload:
        return payload
    return None


def _normalize_paths_map(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str | None] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        if raw_value is None:
            normalized[key] = None
            continue
        text = str(raw_value).strip()
        normalized[key] = text or None
    return normalized


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _run_artifact_context(quest_root: Path, run_id: str | None) -> dict[str, Any] | None:
    normalized = str(run_id or "").strip()
    if not normalized:
        return None
    path = quest_root / ".ds" / "runs" / normalized / "artifact.json"
    payload = read_json(path, {})
    if not isinstance(payload, dict) or not payload:
        return None
    record = dict(payload.get("record") or {}) if isinstance(payload.get("record"), dict) else {}
    checkpoint = dict(payload.get("checkpoint") or {}) if isinstance(payload.get("checkpoint"), dict) else {}
    return {
        "path": str(path),
        "record": record,
        "checkpoint": checkpoint,
        "head_commit": str(checkpoint.get("head") or record.get("head_commit") or "").strip() or None,
        "paths_map": _normalize_paths_map(record.get("paths")),
        "changed_files": _normalize_string_list(record.get("files_changed")),
    }


def _build_run_contexts(quest_root: Path, *, default_branch: str) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    artifact_roots = [quest_root / "artifacts"]
    worktrees_root = quest_root / ".ds" / "worktrees"
    if worktrees_root.exists():
        artifact_roots.extend(path / "artifacts" for path in sorted(worktrees_root.iterdir()) if path.is_dir())
    seen_paths: set[str] = set()
    for artifacts_root in artifact_roots:
        if not artifacts_root.exists():
            continue
        for artifact_path in sorted(path for path in artifacts_root.glob("*/*.json") if path.is_file()):
            resolved = str(artifact_path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            record = _load_artifact_record(artifact_path)
            if not record:
                continue
            run_id = str(record.get("run_id") or "").strip()
            if not run_id:
                continue
            branch_name = _normalize_branch_name(record.get("branch"), fallback=default_branch)
            stage_key = _infer_stage_from_artifact(record)
            current = contexts.get(run_id) or {
                "run_id": run_id,
                "branch_name": branch_name,
                "stage_key": stage_key,
                "worktree_rel_path": record.get("worktree_rel_path"),
                "summary": None,
                "updated_at": None,
            }
            summary = (
                _compact_text(record.get("summary"))
                or _compact_text(record.get("message"))
                or _compact_text(record.get("reason"))
            )
            updated_at = str(record.get("updated_at") or record.get("created_at") or "").strip() or None
            current["branch_name"] = current.get("branch_name") or branch_name
            current["stage_key"] = current.get("stage_key") or stage_key
            current["worktree_rel_path"] = current.get("worktree_rel_path") or record.get("worktree_rel_path")
            current["summary"] = current.get("summary") or summary
            current["updated_at"] = current.get("updated_at") or updated_at
            current["artifact_path"] = current.get("artifact_path") or str(artifact_path)
            contexts[run_id] = current
    return contexts


def _resolve_entry_context(
    quest_root: Path,
    entry: dict[str, Any],
    *,
    default_branch: str,
    run_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    run_id = str(entry.get("run_id") or "").strip() or None
    raw_event_type = str(entry.get("raw_event_type") or entry.get("kind") or "").strip()
    run_context = run_contexts.get(run_id or "")
    artifact_context: dict[str, Any] | None = None
    artifact_path: str | None = None
    for raw_path in entry.get("paths") or []:
        try:
            path = Path(str(raw_path))
        except TypeError:
            continue
        if "artifacts" not in path.parts:
            continue
        artifact_context = _load_artifact_record(path)
        if artifact_context:
            artifact_path = str(path)
            break
    if run_id is None and artifact_context:
        run_id = str(artifact_context.get("run_id") or "").strip() or None
    run_artifact = _run_artifact_context(quest_root, run_id)
    branch_name = _normalize_branch_name(
        (artifact_context or {}).get("branch")
        or (((run_artifact or {}).get("record") or {}) if isinstance((run_artifact or {}).get("record"), dict) else {}).get("branch")
        or (run_context or {}).get("branch_name"),
        fallback=default_branch,
    )
    stage_key = (
        _infer_stage_from_skill(entry.get("skill_id"))
        or _infer_stage_from_artifact(artifact_context or {})
        or _infer_stage_from_artifact((((run_artifact or {}).get("record") or {}) if run_artifact else {}))
        or (run_context or {}).get("stage_key")
        or _infer_stage_from_event_type(raw_event_type)
        or _infer_stage_from_branch_name(branch_name)
        or "general"
    )
    return {
        "run_id": run_id,
        "branch_name": branch_name,
        "stage_key": stage_key,
        "worktree_rel_path": (artifact_context or {}).get("worktree_rel_path")
        or (((run_artifact or {}).get("record") or {}) if run_artifact else {}).get("worktree_rel_path")
        or (run_context or {}).get("worktree_rel_path"),
        "artifact_context": artifact_context,
        "artifact_path": artifact_path or (run_context or {}).get("artifact_path"),
        "run_artifact": run_artifact,
        "trace_confidence": "artifact"
        if artifact_context
        else "run_artifact"
        if run_artifact
        else "run_context"
        if run_context
        else "default_branch",
    }


def _build_action(entry: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    artifact_context = (
        dict(context.get("artifact_context") or {})
        if isinstance(context.get("artifact_context"), dict)
        else {}
    )
    run_artifact = (
        dict(context.get("run_artifact") or {})
        if isinstance(context.get("run_artifact"), dict)
        else {}
    )
    run_record = dict(run_artifact.get("record") or {}) if isinstance(run_artifact.get("record"), dict) else {}
    paths_map = _normalize_paths_map(artifact_context.get("paths")) or _normalize_paths_map(run_record.get("paths"))
    science_paths: dict[str, str] = {}
    if str(artifact_context.get("kind") or "").startswith("science."):
        for key in ("evidence_paths", "input_paths", "output_paths", "log_paths", "validation_paths"):
            for index, path in enumerate(_normalize_string_list(artifact_context.get(key)), start=1):
                science_paths[f"{key.removesuffix('_paths')}_{index}"] = path
        paths_map = {**science_paths, **paths_map}
    changed_files = _normalize_string_list(artifact_context.get("files_changed")) or _normalize_string_list(
        artifact_context.get("changed_files")
    ) or _normalize_string_list(run_record.get("files_changed")) or _normalize_string_list(run_artifact.get("changed_files"))
    if science_paths:
        changed_files = _normalize_string_list([*changed_files, *science_paths.values()])
    details_json = dict(artifact_context.get("details") or {}) if isinstance(artifact_context.get("details"), dict) else {}
    checkpoint_json = dict(run_artifact.get("checkpoint") or {}) if isinstance(run_artifact.get("checkpoint"), dict) else {}
    metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
    payload_json = artifact_context or metadata or None
    return {
        "action_id": entry.get("id"),
        "kind": entry.get("kind"),
        "title": entry.get("title"),
        "summary": entry.get("summary"),
        "status": entry.get("status"),
        "created_at": entry.get("created_at"),
        "run_id": context.get("run_id"),
        "skill_id": entry.get("skill_id"),
        "branch_name": context.get("branch_name"),
        "stage_key": context.get("stage_key"),
        "worktree_rel_path": context.get("worktree_rel_path"),
        "tool_name": entry.get("tool_name"),
        "tool_call_id": entry.get("tool_call_id"),
        "mcp_server": entry.get("mcp_server"),
        "mcp_tool": entry.get("mcp_tool"),
        "args": entry.get("args"),
        "output": entry.get("output"),
        "reason": entry.get("reason"),
        "raw_event_type": entry.get("raw_event_type"),
        "paths": [str(item) for item in (entry.get("paths") or []) if item],
        "paths_map": paths_map or None,
        "artifact_id": artifact_context.get("artifact_id"),
        "artifact_kind": artifact_context.get("kind"),
        "artifact_path": context.get("artifact_path"),
        "head_commit": (
            str(
                artifact_context.get("head_commit")
                or run_artifact.get("head_commit")
                or ""
            ).strip()
            or None
        ),
        "payload_json": payload_json,
        "details_json": details_json or (metadata or None),
        "checkpoint_json": checkpoint_json or None,
        "changed_files": changed_files or None,
        "trace_confidence": context.get("trace_confidence"),
    }


def _summarize_trace(actions: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    for action in reversed(actions):
        summary = _compact_text(
            action.get("summary")
            or action.get("output")
            or action.get("args")
            or action.get("title")
        )
        if summary:
            return summary, str(action.get("status") or "").strip() or None
    return None, None


def _build_counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "actions": len(actions),
        "tool_calls": 0,
        "tool_results": 0,
        "thoughts": 0,
        "artifacts": 0,
        "runs": 0,
    }
    for action in actions:
        kind = str(action.get("kind") or "").strip()
        if kind == "tool_call":
            counts["tool_calls"] += 1
        elif kind == "tool_result":
            counts["tool_results"] += 1
        elif kind == "thought":
            counts["thoughts"] += 1
        elif kind == "artifact":
            counts["artifacts"] += 1
        elif kind == "run":
            counts["runs"] += 1
    return counts


def _build_trace_item(
    *,
    selection_type: str,
    selection_ref: str,
    title: str,
    branch_name: str,
    stage_key: str | None,
    worktree_rel_path: str | None,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_actions = sorted(actions, key=lambda item: str(item.get("created_at") or item.get("action_id") or ""))
    summary, status = _summarize_trace(ordered_actions)
    updated_at = (
        str(ordered_actions[-1].get("created_at") or "").strip()
        if ordered_actions
        else None
    ) or None
    run_ids = sorted({str(item.get("run_id") or "").strip() for item in ordered_actions if item.get("run_id")})
    skill_ids = sorted({str(item.get("skill_id") or "").strip() for item in ordered_actions if item.get("skill_id")})
    primary_action = next(
        (
            action
            for action in reversed(ordered_actions)
            if action.get("artifact_id")
            or action.get("head_commit")
            or action.get("payload_json")
            or action.get("details_json")
        ),
        ordered_actions[-1] if ordered_actions else {},
    )
    merged_paths_map: dict[str, str | None] = {}
    for action in ordered_actions:
        if isinstance(action.get("paths_map"), dict):
            merged_paths_map.update(action.get("paths_map") or {})
    merged_changed_files = _normalize_string_list(
        [item for action in ordered_actions for item in (action.get("changed_files") or [])]
    )
    return {
        "selection_type": selection_type,
        "selection_ref": selection_ref,
        "title": title,
        "summary": summary,
        "status": status,
        "branch_name": branch_name,
        "stage_key": stage_key,
        "stage_title": _format_state_label(stage_key) if stage_key else None,
        "worktree_rel_path": worktree_rel_path,
        "updated_at": updated_at,
        "counts": _build_counts(ordered_actions),
        "run_ids": run_ids,
        "skill_ids": skill_ids,
        "artifact_id": primary_action.get("artifact_id"),
        "artifact_kind": primary_action.get("artifact_kind"),
        "head_commit": primary_action.get("head_commit"),
        "payload_json": primary_action.get("payload_json"),
        "details_json": primary_action.get("details_json"),
        "paths_map": merged_paths_map or None,
        "changed_files": merged_changed_files or None,
        "actions": ordered_actions,
    }


class QuestNodeTraceManager:
    def __init__(self, quest_root: Path) -> None:
        self.quest_root = quest_root

    @property
    def materialized_path(self) -> Path:
        return ensure_dir(self.quest_root / ".ds" / "node_traces") / "index.json"

    def materialize(
        self,
        *,
        quest_id: str,
        workflow: dict[str, Any],
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_signature = sha256_text(
            json.dumps(
                {
                    "schema_version": NODE_TRACE_SCHEMA_VERSION,
                    "entries": workflow.get("entries") or [],
                    "branch": (snapshot or {}).get("branch"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        existing = read_json(self.materialized_path, {})
        if (
            isinstance(existing, dict)
            and existing.get("quest_id") == quest_id
            and existing.get("schema_version") == NODE_TRACE_SCHEMA_VERSION
            and existing.get("source_signature") == source_signature
            and isinstance(existing.get("items"), list)
        ):
            return existing
        default_branch = str((snapshot or {}).get("branch") or "main").strip() or "main"
        run_contexts = _build_run_contexts(self.quest_root, default_branch=default_branch)
        entries = list(workflow.get("entries") or [])

        event_items: list[dict[str, Any]] = []
        stage_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        branch_groups: dict[str, list[dict[str, Any]]] = {}

        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            entry = dict(raw_entry)
            selection_ref = str(entry.get("id") or "").strip()
            if not selection_ref:
                continue
            context = _resolve_entry_context(
                self.quest_root,
                entry,
                default_branch=default_branch,
                run_contexts=run_contexts,
            )
            action = _build_action(entry, context)
            branch_name = str(context.get("branch_name") or default_branch)
            stage_key = str(context.get("stage_key") or "general")
            worktree_rel_path = context.get("worktree_rel_path")
            event_items.append(
                _build_trace_item(
                    selection_type="event_node",
                    selection_ref=selection_ref,
                    title=str(entry.get("title") or selection_ref),
                    branch_name=branch_name,
                    stage_key=stage_key,
                    worktree_rel_path=worktree_rel_path if isinstance(worktree_rel_path, str) else None,
                    actions=[action],
                )
            )
            stage_groups.setdefault((branch_name, stage_key), []).append(action)
            branch_groups.setdefault(branch_name, []).append(action)

        stage_items = [
            _build_trace_item(
                selection_type="stage_node",
                selection_ref=f"stage:{branch_name}:{stage_key}",
                title=f"{branch_name} · {_format_state_label(stage_key)}",
                branch_name=branch_name,
                stage_key=stage_key,
                worktree_rel_path=next(
                    (
                        str(action.get("worktree_rel_path"))
                        for action in actions
                        if action.get("worktree_rel_path")
                    ),
                    None,
                ),
                actions=actions,
            )
            for (branch_name, stage_key), actions in stage_groups.items()
        ]

        branch_items = [
            _build_trace_item(
                selection_type="branch_node",
                selection_ref=branch_name,
                title=branch_name,
                branch_name=branch_name,
                stage_key=None,
                worktree_rel_path=next(
                    (
                        str(action.get("worktree_rel_path"))
                        for action in actions
                        if action.get("worktree_rel_path")
                    ),
                    None,
                ),
                actions=actions,
            )
            for branch_name, actions in branch_groups.items()
        ]

        items = sorted(
            [*branch_items, *stage_items, *event_items],
            key=lambda item: (
                str(item.get("selection_type") or ""),
                str(item.get("updated_at") or ""),
                str(item.get("selection_ref") or ""),
            ),
        )

        payload = {
            "quest_id": quest_id,
            "schema_version": NODE_TRACE_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source_signature": source_signature,
            "items": items,
        }
        write_json(self.materialized_path, payload)
        return payload
