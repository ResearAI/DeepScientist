from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import shlex
import sys
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..artifact import ArtifactService
from ..artifact.metrics import MetricContractValidationError
from ..bash_exec import BashExecService
from ..memory import MemoryService
from ..quest import QuestService
from ..shared import read_json
from .context import McpContext
from .schemas import MetricContractPayload, PrimaryMetricPayload, SupplementaryBaselinePayload

DEFAULT_INLINE_BASH_LOG_LINE_LIMIT = 2000
DEFAULT_INLINE_BASH_LOG_HEAD_LINES = 500
DEFAULT_INLINE_BASH_LOG_TAIL_LINES = 1500
DEFAULT_INLINE_BASH_LOG_WINDOW_LINES = 200
MAX_INLINE_BASH_LOG_WINDOW_LINES = 2000
DEFAULT_BASH_EXEC_AWAIT_WAIT_TIMEOUT_SECONDS = 1800
BASH_EXEC_TERMINAL_STATUSES = {"completed", "failed", "terminated"}
INTERACTION_WATCHDOG_TOOL_CALL_THRESHOLD = 25
INTERACTION_WATCHDOG_SILENCE_THRESHOLD_SECONDS = 30 * 60
LONG_BASH_LOG_HINT = (
    "Use `bash_exec(mode='read', id=..., start=..., tail=...)` to inspect a specific log window, "
    "or `bash_exec(mode='read', id=..., tail=...)` to inspect the latest rendered lines."
)


def _attach_bash_log_truncation_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)

    log_line_count = result.get("log_line_count")
    latest_seq = result.get("latest_seq")
    tail_start_seq = result.get("tail_start_seq")
    line_start = result.get("line_start")
    line_end = result.get("line_end")

    def _as_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    total_lines = _as_int(log_line_count) or 0
    latest_seq_value = _as_int(latest_seq)
    tail_start_seq_value = _as_int(tail_start_seq)
    line_start_value = _as_int(line_start)
    line_end_value = _as_int(line_end)

    if result.get("log_truncated") is True:
        head_lines = _as_int(result.get("log_preview_head_lines")) or 0
        tail_lines = _as_int(result.get("log_preview_tail_lines")) or 0
        omitted_lines = _as_int(result.get("log_preview_omitted_lines")) or max(total_lines - head_lines - tail_lines, 0)
        after_preview_lines = tail_lines
        before_preview_lines = head_lines
        result["log_is_partial"] = True
        result["log_visible_line_start"] = 1 if total_lines else 0
        result["log_visible_line_end"] = total_lines if total_lines and total_lines <= head_lines + tail_lines else head_lines + tail_lines
        result["log_lines_before_window"] = 0
        result["log_lines_after_window"] = max(total_lines - tail_lines, 0) if total_lines else 0
        result["seq_has_more_before"] = False
        result["seq_has_more_after"] = omitted_lines > 0
        result["seqs_before_window"] = 0
        result["seqs_after_window"] = omitted_lines
        result["log_truncation_notice"] = (
            "This log payload is truncated to a preview window rather than the full output. "
            f"It shows the first {head_lines} line(s) and the last {tail_lines} line(s), omitting {omitted_lines} middle line(s). "
            "Do not treat this preview as exhaustive evidence. "
            "Use bash_exec(mode='read', id=..., start=..., tail=...) for a specific line window, "
            "or bash_exec(mode='read', id=..., tail_limit=..., before_seq=..., after_seq=...) for seq-based continuation."
        )
        return result

    if result.get("log_windowed") is True:
        if line_start_value is None:
            line_start_value = 1 if total_lines else 0
        if line_end_value is None:
            line_end_value = line_start_value - 1 if line_start_value else 0
        lines_before = max((line_start_value - 1) if line_start_value else 0, 0)
        lines_after = max(total_lines - max(line_end_value or 0, 0), 0)
        result["log_is_partial"] = bool(result.get("has_more_before")) or bool(result.get("has_more_after"))
        result["log_lines_before_window"] = lines_before
        result["log_lines_after_window"] = lines_after
        result["log_visible_line_start"] = line_start_value
        result["log_visible_line_end"] = line_end_value

        if tail_start_seq_value is not None:
            seq_window_start = tail_start_seq_value
            seq_window_end = (
                tail_start_seq_value + (_as_int(result.get("returned_line_count")) or 0) - 1
                if (_as_int(result.get("returned_line_count")) or 0) > 0
                else tail_start_seq_value - 1
            )
        else:
            seq_window_start = line_start_value
            seq_window_end = line_end_value
        seqs_before = max((seq_window_start or 0) - 1, 0)
        seqs_after = (
            max(latest_seq_value - max(seq_window_end or 0, 0), 0)
            if latest_seq_value is not None
            else lines_after
        )
        result["seq_window_start"] = seq_window_start
        result["seq_window_end"] = seq_window_end
        result["seq_has_more_before"] = seqs_before > 0
        result["seq_has_more_after"] = seqs_after > 0
        result["seqs_before_window"] = seqs_before
        result["seqs_after_window"] = seqs_after

        if result["log_is_partial"]:
            result["log_truncation_notice"] = (
                "This log payload is only a partial window, not the full output. "
                f"It currently covers lines {line_start_value} to {line_end_value} out of {total_lines}, "
                f"with {lines_before} line(s) before and {lines_after} line(s) after this window. "
                "If you need adjacent output, continue with bash_exec(mode='read', id=..., start=..., tail=...) "
                "or use the seq-based before_seq / after_seq parameters."
            )
        return result

    if total_lines > 0:
        result["log_is_partial"] = False
        result["log_lines_before_window"] = 0
        result["log_lines_after_window"] = 0
        if latest_seq_value is not None:
            result["seq_has_more_before"] = False
            result["seq_has_more_after"] = False
            result["seqs_before_window"] = 0
            result["seqs_after_window"] = 0
            result["seq_window_start"] = 1
            result["seq_window_end"] = latest_seq_value
    return result


def _normalize_positive_timeout_seconds(value: Any, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return normalized


def _build_bash_exec_wait_notice(
    *,
    bash_id: str,
    wait_timeout_seconds: int,
    status: str,
) -> dict[str, Any]:
    suggested_poll_interval_seconds = DEFAULT_BASH_EXEC_AWAIT_WAIT_TIMEOUT_SECONDS
    suggested_sleep_timeout = suggested_poll_interval_seconds + 60
    return {
        "wait_timed_out": True,
        "still_running": status in {"running", "terminating"},
        "wait_timeout_seconds": wait_timeout_seconds,
        "suggested_poll_interval_seconds": suggested_poll_interval_seconds,
        "suggested_read_command": f"bash_exec(mode='read', id='{bash_id}')",
        "suggested_await_command": (
            f"bash_exec(mode='await', id='{bash_id}', "
            f"wait_timeout_seconds={suggested_poll_interval_seconds})"
        ),
        "suggested_sleep_command": (
            f"bash_exec(command='sleep {suggested_poll_interval_seconds}', mode='await', "
            f"timeout_seconds={suggested_sleep_timeout})"
        ),
        "long_wait_notice": (
            "This managed bash_exec session is still running, so the bounded await window ended without final completion. "
            f"Read the saved log with bash_exec(mode='read', id='{bash_id}') and check again in about "
            f"{suggested_poll_interval_seconds} seconds. Prefer "
            f"bash_exec(mode='await', id='{bash_id}', wait_timeout_seconds={suggested_poll_interval_seconds}) "
            "for the next bounded wait on this managed session; if you only need wall-clock waiting between checks, "
            f"you may use bash_exec(command='sleep {suggested_poll_interval_seconds}', mode='await', "
            f"timeout_seconds={suggested_sleep_timeout}) before reading the log again."
        ),
    }
ARTIFACT_STATE_CHANGE_WATCHDOG_NOTES = {
    "confirm_baseline": (
        "Baseline confirmation changed durable quest state and this tool does not send a user-visible "
        "summary on its own. Send one concise artifact.interact(...) update now."
    ),
    "waive_baseline": (
        "Baseline waiver changed durable quest state and this tool does not send a user-visible summary "
        "on its own. Send one concise artifact.interact(...) update now."
    ),
    "submit_paper_outline": (
        "Paper outline state changed durably and this tool does not send a user-visible summary on its own. "
        "Send one concise artifact.interact(...) update now."
    ),
    "compile_outline_to_writing_plan": (
        "Paper writing plan state changed durably and this tool does not send a user-visible summary on its own. "
        "Send one concise artifact.interact(...) update now."
    ),
    "publish_baseline": (
        "Baseline publication changed durable state and this tool does not send a user-visible summary "
        "on its own. Send one concise artifact.interact(...) update now."
    ),
    "attach_baseline": (
        "Baseline attachment changed durable quest state and this tool does not send a user-visible summary "
        "on its own. Send one concise artifact.interact(...) update now."
    ),
    "complete_quest": (
        "Quest completion changed durable state and this tool does not send a final user-visible summary "
        "on its own. Send one concise artifact.interact(...) closing update now unless the user already "
        "received an equivalent completion summary."
    ),
}
START_SETUP_FORM_FIELDS: tuple[str, ...] = (
    "title",
    "goal",
    "baseline_id",
    "baseline_variant_id",
    "baseline_source_mode",
    "execution_start_mode",
    "baseline_acceptance_target",
    "baseline_urls",
    "paper_urls",
    "runtime_constraints",
    "objectives",
    "need_research_paper",
    "research_intensity",
    "decision_policy",
    "launch_mode",
    "standard_profile",
    "custom_profile",
    "review_followup_policy",
    "baseline_execution_policy",
    "manuscript_edit_mode",
    "entry_state_summary",
    "review_summary",
    "review_materials",
    "custom_brief",
    "user_language",
)
START_SETUP_SESSION_FIELDS: tuple[str, ...] = (
    "fit_assessment",
    "recommended_workspace_mode",
    "launch_readiness",
    "missing_confirmations",
    "preview_plan",
    "materials_summary",
)


def _split_nested_start_setup_payload(payload: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(payload, dict):
        return None, None
    form_patch = payload.get("form_patch") if isinstance(payload.get("form_patch"), dict) else None
    session_patch = payload.get("session_patch") if isinstance(payload.get("session_patch"), dict) else None
    suggested_form = payload.get("suggested_form") if isinstance(payload.get("suggested_form"), dict) else None
    if isinstance(suggested_form, dict):
        if form_patch is None and isinstance(suggested_form.get("form_patch"), dict):
            form_patch = suggested_form.get("form_patch")
        if session_patch is None and isinstance(suggested_form.get("session_patch"), dict):
            session_patch = suggested_form.get("session_patch")
    return form_patch, session_patch


def _normalize_bash_exec_command_input(raw_command: Any) -> str:
    if isinstance(raw_command, str):
        return raw_command
    if isinstance(raw_command, (list, tuple)):
        items = [str(item).strip() for item in raw_command if str(item).strip()]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return shlex.join(items)
    return str(raw_command or "")


def _normalize_bash_exec_command_input(raw_command: Any) -> str:
    if isinstance(raw_command, str):
        return raw_command
    if isinstance(raw_command, (list, tuple)):
        items = [str(item).strip() for item in raw_command if str(item).strip()]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return shlex.join(items)
    return str(raw_command or "")


def _read_only_tool_annotations(*, title: str | None = None) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _metric_validation_error_payload(exc: MetricContractValidationError) -> dict[str, Any]:
    return exc.as_payload()


def _artifact_call(name: str, why: str) -> dict[str, str]:
    return {"name": name, "why": why}


def _artifact_guided_error_payload(
    service: ArtifactService,
    quest_root: Path,
    *,
    tool_name: str,
    exc: Exception,
) -> dict[str, Any]:
    message = str(exc).strip() or f"`artifact.{tool_name}` failed."
    guidance: list[str] = []
    suggested_artifact_calls: list[dict[str, str]] = []
    extra: dict[str, Any] = {}

    if "selected_outline_ref" in message or "No selected outline is available" in message:
        outlines = service.list_paper_outlines(quest_root)
        outline_items = [dict(item) for item in (outlines.get("outlines") or []) if isinstance(item, dict)]
        candidate_ids = [
            str(item.get("outline_id") or "").strip()
            for item in outline_items
            if str(item.get("status") or "").strip() in {"candidate", "revised"}
            and str(item.get("outline_id") or "").strip()
        ]
        extra["outline_candidates"] = outline_items
        if candidate_ids:
            guidance.append(f"Select a candidate outline first. Available candidates: {', '.join(candidate_ids[:5])}.")
            guidance.append(
                "Use `artifact.submit_paper_outline(mode='select', outline_id='...', selected_reason='...')` "
                "to promote one of those candidates before retrying the writing-facing campaign."
            )
            suggested_artifact_calls.append(
                _artifact_call(
                    "artifact.submit_paper_outline(mode='select', outline_id='...', selected_reason='...')",
                    "Promote one candidate outline into the active paper line.",
                )
            )
        else:
            guidance.append("Create a candidate outline first, then select it before launching a writing-facing analysis campaign.")
            suggested_artifact_calls.append(
                _artifact_call(
                    "artifact.submit_paper_outline(mode='candidate', ...)",
                    "Create the first paper outline candidate for this quest.",
                )
            )
        guidance.append(
            "If the work is only exploratory evidence and not yet bound to the paper contract, downgrade it to a pre-outline analysis-lite / non-writing-facing campaign instead."
        )
        suggested_artifact_calls.append(
            _artifact_call(
                "artifact.create_analysis_campaign(...)",
                "Retry only after the selected outline and paper-facing fields are explicit, or simplify the campaign so it is no longer writing-facing.",
            )
        )
    elif "research_questions" in message:
        guidance.append("Provide non-empty research_questions before launching a writing-facing analysis campaign.")
        guidance.append("The cleanest fix is to revise the selected outline so the paper contract and campaign input agree.")
        suggested_artifact_calls.extend(
            [
                _artifact_call(
                    "artifact.submit_paper_outline(mode='revise', ...)",
                    "Add research_questions to the selected outline.",
                ),
                _artifact_call(
                    "artifact.create_analysis_campaign(..., research_questions=[...], experimental_designs=[...], todo_items=[...])",
                    "Retry the campaign with explicit writing-facing fields.",
                ),
            ]
        )
    elif "experimental_designs" in message:
        guidance.append("Provide non-empty experimental_designs before launching a writing-facing analysis campaign.")
        guidance.append("If the paper contract is still thin, revise the selected outline before retrying.")
        suggested_artifact_calls.extend(
            [
                _artifact_call(
                    "artifact.submit_paper_outline(mode='revise', ...)",
                    "Add experimental_designs to the selected outline.",
                ),
                _artifact_call(
                    "artifact.create_analysis_campaign(..., experimental_designs=[...])",
                    "Retry the campaign with explicit experimental designs.",
                ),
            ]
        )
    elif "todo_items" in message or "outline-bound paper contract fields" in message:
        guidance.append("Every writing-facing analysis slice needs a todo item with section_id, item_id, paper_role, and claim_links.")
        guidance.append("Do not launch a paper-facing campaign until every slice is mapped back into the outline contract.")
        suggested_artifact_calls.append(
            _artifact_call(
                "artifact.create_analysis_campaign(..., todo_items=[...])",
                "Retry with one outline-bound todo item per slice.",
            )
        )
    elif "confirmed or waived baseline gate" in message:
        guidance.append("Open the baseline gate first, or explicitly waive it if skipping is justified.")
        suggested_artifact_calls.extend(
            [
                _artifact_call("artifact.confirm_baseline(...)", "Confirm the active baseline and metric contract."),
                _artifact_call("artifact.waive_baseline(...)", "Record an explicit waiver if baseline work should be skipped."),
            ]
        )
    elif "An active idea is required before starting an analysis campaign." in message:
        guidance.append("Create or activate an idea before launching an analysis campaign.")
        suggested_artifact_calls.extend(
            [
                _artifact_call("artifact.submit_idea(...)", "Create the next durable idea route first."),
                _artifact_call("artifact.activate_branch(...)", "Switch back to the branch that owns the accepted idea line."),
            ]
        )
    elif "baseline_path" in message:
        guidance.append("Use a quest-local baseline path under `baselines/local/...` or `baselines/imported/...`.")
        guidance.append("If the baseline lives outside the quest, materialize or attach it first instead of passing an external path directly.")
        suggested_artifact_calls.extend(
            [
                _artifact_call("artifact.attach_baseline(...)", "Attach a reusable baseline package when one already exists."),
                _artifact_call("artifact.confirm_baseline(...)", "Confirm the quest-local baseline after it is materialized."),
            ]
        )
    elif "imported baseline" in message or "protocol-breaking" in message:
        guidance.append("Do not overwrite the accepted baseline in place when comparability changed materially.")
        guidance.append("Use a new baseline id or a new variant when the path, protocol, or comparator meaning changed.")
        suggested_artifact_calls.extend(
            [
                _artifact_call("artifact.confirm_baseline(...)", "Confirm the new baseline or variant as a separate comparator."),
                _artifact_call("artifact.overwrite_baseline(...)", "Use overwrite only when the baseline is still the same accepted comparator."),
            ]
        )
    elif "submit_paper_bundle requires a selected outline" in message:
        guidance.append("Select an outline before bundling the paper package.")
        suggested_artifact_calls.append(
            _artifact_call(
                "artifact.submit_paper_outline(mode='select', outline_id='...', selected_reason='...')",
                "Select the active outline before generating the final paper bundle.",
            )
        )
    else:
        guidance.append("Inspect the current quest state and the tool-specific required fields before retrying.")
        suggested_artifact_calls.append(
            _artifact_call("artifact.get_quest_state(detail='full')", "Read the current durable quest state before retrying the tool.")
        )

    return {
        "ok": False,
        "tool_name": f"artifact.{tool_name}",
        "message": message,
        "guidance": guidance,
        "suggested_artifact_calls": suggested_artifact_calls,
        **extra,
    }


def _progress_watchdog_note(tool_call_count: int) -> str:
    return (
        "By the way, you have gone "
        f"{tool_call_count} tool calls without notifying the user via artifact.interact(...). "
        "Inspect whether the user-visible state actually changed; only send a progress update if there is a real new checkpoint, blocker, or route change."
    )


def _visibility_watchdog_note(seconds_since_last_update: int) -> str:
    minutes = max(1, seconds_since_last_update // 60)
    return (
        "By the way, it has been "
        f"{minutes} minutes since the last user-visible artifact.interact(...). "
        "Inspect the current run or task state now. Only send a new user-visible update if the frontier materially changed or the user explicitly needs a fresh checkpoint."
    )


def _collect_interaction_watchdog_notes(
    watchdog: dict[str, Any],
    *,
    state_change_note: str | None = None,
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    count = int((watchdog or {}).get("tool_calls_since_last_artifact_interact") or 0)
    if count >= INTERACTION_WATCHDOG_TOOL_CALL_THRESHOLD:
        notes.append(
            {
                "kind": "progress",
                "message": _progress_watchdog_note(count),
            }
        )
    silence_seconds = int((watchdog or {}).get("seconds_since_last_artifact_interact") or 0)
    if count > 0 and silence_seconds >= INTERACTION_WATCHDOG_SILENCE_THRESHOLD_SECONDS:
        notes.append(
            {
                "kind": "visibility",
                "message": _visibility_watchdog_note(silence_seconds),
            }
        )
    if state_change_note:
        notes.append(
            {
                "kind": "state_change",
                "message": state_change_note,
            }
        )
    return notes


def _attach_interaction_watchdog(
    payload: dict[str, Any],
    watchdog: dict[str, Any],
    *,
    state_change_note: str | None = None,
) -> dict[str, Any]:
    enriched = dict(payload)
    interaction_watchdog = dict(watchdog or {})
    notes = _collect_interaction_watchdog_notes(
        watchdog,
        state_change_note=state_change_note,
    )
    interaction_watchdog["user_update_due"] = bool(
        interaction_watchdog.get("user_update_due")
        or any(str(item.get("kind") or "") == "state_change" for item in notes)
    )
    enriched["interaction_watchdog"] = interaction_watchdog
    if not notes:
        return enriched
    enriched["watchdog_notes"] = notes
    for item in notes:
        kind = str(item.get("kind") or "").strip()
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        if kind == "progress":
            enriched["progress_watchdog_note"] = message
        elif kind == "visibility":
            enriched["visibility_watchdog_note"] = message
        elif kind == "state_change":
            enriched["state_change_watchdog_note"] = message
    return enriched


def _local_daemon_api_base_url(home: Path) -> tuple[str | None, dict[str, Any]]:
    state = read_json(home / "runtime" / "daemon.json", {})
    if not isinstance(state, dict):
        return None, {}
    for key in ("url", "bind_url"):
        value = str(state.get(key) or "").strip()
        if value:
            return value.rstrip("/"), state
    return None, state


def _issue_draft_route_effect(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "route:navigate",
        "data": {
            "to": "/settings/issues",
            "issueDraft": {
                "ok": True,
                "title": str(payload.get("title") or "").strip(),
                "body_markdown": str(payload.get("body_markdown") or "").strip(),
                "issue_url_base": str(payload.get("issue_url_base") or "").strip(),
                "repo_url": str(payload.get("repo_url") or "").strip(),
                "generated_at": payload.get("generated_at"),
            },
        },
    }


def _coerce_prepare_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"`{field_name}` must be a boolean.")


def _sanitize_start_setup_form_patch(form_patch: dict[str, Any] | None) -> dict[str, Any]:
    if form_patch is None:
        return {}
    if not isinstance(form_patch, dict):
        raise ValueError("`form_patch` must be an object.")
    patch: dict[str, Any] = {}
    for key in START_SETUP_FORM_FIELDS:
        if key not in form_patch:
            continue
        value = form_patch.get(key)
        if value is None:
            continue
        if key == "need_research_paper":
            patch[key] = _coerce_prepare_bool(value, field_name=key)
            continue
        if isinstance(value, (str, int, float, bool)):
            patch[key] = str(value).strip() if not isinstance(value, bool) else value
            continue
        raise ValueError(f"`form_patch.{key}` must be a string or boolean.")
    return patch


def _sanitize_start_setup_session_patch(session_patch: dict[str, Any] | None) -> dict[str, Any]:
    if session_patch is None:
        return {}
    if not isinstance(session_patch, dict):
        raise ValueError("`session_patch` must be an object.")
    patch: dict[str, Any] = {}
    for key in START_SETUP_SESSION_FIELDS:
        if key not in session_patch:
            continue
        value = session_patch.get(key)
        if value is None:
            continue
        if key in {"recommended_workspace_mode", "launch_readiness"}:
            patch[key] = str(value).strip()
            continue
        if key == "missing_confirmations":
            if not isinstance(value, list):
                raise ValueError("`session_patch.missing_confirmations` must be an array of strings.")
            patch[key] = [str(item).strip() for item in value if str(item).strip()]
            continue
        if key in {"fit_assessment", "preview_plan"}:
            if not isinstance(value, dict):
                raise ValueError(f"`session_patch.{key}` must be an object.")
            patch[key] = json.loads(json.dumps(value, ensure_ascii=False))
            continue
        if key == "materials_summary":
            if not isinstance(value, list):
                raise ValueError("`session_patch.materials_summary` must be an array.")
            patch[key] = [dict(item) for item in value if isinstance(item, dict)]
            continue
    return patch


def _start_setup_patch_effect(
    form_patch: dict[str, Any],
    *,
    session_patch: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    return {
        "name": "start_setup:patch",
        "data": {
            "patch": dict(form_patch),
            "session_patch": dict(session_patch or {}),
            "message": str(message or "").strip() or None,
        },
    }


def _prepare_github_issue_payload_via_daemon(
    home: Path,
    *,
    summary: str | None = None,
    user_notes: str | None = None,
    include_doctor: bool = True,
    include_logs: bool = True,
) -> dict[str, Any]:
    base_url, daemon_state = _local_daemon_api_base_url(home)
    if not base_url:
        raise ValueError("The local daemon URL is unavailable. Start DeepScientist before preparing a GitHub issue draft.")

    token = str((daemon_state or {}).get("auth_token") or "").strip()
    auth_enabled = bool((daemon_state or {}).get("auth_enabled"))
    if auth_enabled and not token:
        raise ValueError("Browser auth is enabled for the local daemon, but no auth token was found in runtime/daemon.json.")

    body = {
        "summary": str(summary or "").strip() or None,
        "user_notes": str(user_notes or "").strip() or None,
        "include_doctor": bool(include_doctor),
        "include_logs": bool(include_logs),
    }
    headers = {
        "Content-Type": "application/json",
    }
    if auth_enabled and token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib_request.Request(
        f"{base_url}/api/system/issues/draft",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:  # pragma: no cover - exercised via unit monkeypatching
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = detail or getattr(exc, "reason", "") or "request failed"
        raise ValueError(f"Local daemon issue draft request failed with HTTP {exc.code}: {message}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to reach the local daemon at `{base_url}`: {exc}") from exc

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("The local daemon returned an invalid issue draft payload.") from exc
    if not isinstance(payload, dict):
        raise ValueError("The local daemon returned a non-object issue draft payload.")
    if payload.get("ok") is False:
        raise ValueError(str(payload.get("message") or "The local daemon rejected the issue draft request."))
    return payload


def _split_bash_log_lines(log_text: str) -> list[str]:
    return log_text.splitlines()


def _join_bash_log_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def _normalize_bash_log_window_size(value: int | None, *, default: int = DEFAULT_INLINE_BASH_LOG_WINDOW_LINES) -> int:
    resolved = default if value is None else int(value)
    return max(1, min(resolved, MAX_INLINE_BASH_LOG_WINDOW_LINES))


def _build_bash_log_window(log_text: str, *, start: int | None = None, tail: int | None = None) -> dict[str, Any]:
    lines = _split_bash_log_lines(log_text)
    total = len(lines)
    line_limit = _normalize_bash_log_window_size(tail)
    if start is not None:
        requested_start = max(1, int(start))
        start_index = min(max(0, requested_start - 1), total)
    else:
        start_index = max(0, total - line_limit)
    selected = lines[start_index : start_index + line_limit]
    returned_count = len(selected)
    line_start = start_index + 1 if total else 1
    line_end = start_index + returned_count
    return {
        "log": _join_bash_log_lines(selected),
        "log_line_count": total,
        "log_windowed": True,
        "line_start": line_start,
        "line_end": line_end,
        "line_limit": line_limit,
        "returned_line_count": returned_count,
        "has_more_before": start_index > 0,
        "has_more_after": line_end < total,
        "log_read_hint": LONG_BASH_LOG_HINT,
    }


def _build_default_bash_log_payload(log_text: str) -> dict[str, Any]:
    lines = _split_bash_log_lines(log_text)
    total = len(lines)
    if total <= DEFAULT_INLINE_BASH_LOG_LINE_LIMIT:
        return {
            "log": log_text,
            "log_line_count": total,
            "log_truncated": False,
        }
    omitted = total - DEFAULT_INLINE_BASH_LOG_HEAD_LINES - DEFAULT_INLINE_BASH_LOG_TAIL_LINES
    marker = (
        f"[... omitted {omitted} lines from the middle of this log. {LONG_BASH_LOG_HINT}]"
    )
    preview_lines = (
        lines[:DEFAULT_INLINE_BASH_LOG_HEAD_LINES]
        + [marker]
        + lines[-DEFAULT_INLINE_BASH_LOG_TAIL_LINES :]
    )
    return {
        "log": _join_bash_log_lines(preview_lines),
        "log_line_count": total,
        "log_truncated": True,
        "log_preview_head_lines": DEFAULT_INLINE_BASH_LOG_HEAD_LINES,
        "log_preview_tail_lines": DEFAULT_INLINE_BASH_LOG_TAIL_LINES,
        "log_preview_omitted_lines": omitted,
        "log_read_hint": LONG_BASH_LOG_HINT,
    }


def _stream_bash_log_summary(path: Path) -> tuple[list[str], int, list[str]]:
    total = 0
    full_lines: list[str] = []
    head_lines: list[str] = []
    tail_lines: deque[str] = deque(maxlen=DEFAULT_INLINE_BASH_LOG_TAIL_LINES)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            total += 1
            if total <= DEFAULT_INLINE_BASH_LOG_LINE_LIMIT:
                full_lines.append(line)
                continue
            if total == DEFAULT_INLINE_BASH_LOG_LINE_LIMIT + 1:
                head_lines = full_lines[:DEFAULT_INLINE_BASH_LOG_HEAD_LINES]
                tail_lines.extend(full_lines[-DEFAULT_INLINE_BASH_LOG_TAIL_LINES :])
                full_lines = []
            tail_lines.append(line)
    return full_lines, total, list(head_lines or tail_lines)


def _build_default_bash_log_payload_from_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "log": "",
            "log_line_count": 0,
            "log_truncated": False,
        }
    full_lines, total, preview_seed = _stream_bash_log_summary(path)
    if total <= DEFAULT_INLINE_BASH_LOG_LINE_LIMIT:
        return {
            "log": _join_bash_log_lines(full_lines),
            "log_line_count": total,
            "log_truncated": False,
        }
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        tail_lines: deque[str] = deque(maxlen=DEFAULT_INLINE_BASH_LOG_TAIL_LINES)
        for raw_line in handle:
            tail_lines.append(raw_line.rstrip("\n"))
    omitted = total - DEFAULT_INLINE_BASH_LOG_HEAD_LINES - DEFAULT_INLINE_BASH_LOG_TAIL_LINES
    marker = (
        f"[... omitted {omitted} lines from the middle of this log. {LONG_BASH_LOG_HINT}]"
    )
    preview_lines = preview_seed[:DEFAULT_INLINE_BASH_LOG_HEAD_LINES] + [marker] + list(tail_lines)
    return {
        "log": _join_bash_log_lines(preview_lines),
        "log_line_count": total,
        "log_truncated": True,
        "log_preview_head_lines": DEFAULT_INLINE_BASH_LOG_HEAD_LINES,
        "log_preview_tail_lines": DEFAULT_INLINE_BASH_LOG_TAIL_LINES,
        "log_preview_omitted_lines": omitted,
        "log_read_hint": LONG_BASH_LOG_HINT,
    }


def _build_bash_log_window_from_path(path: Path, *, start: int | None = None, tail: int | None = None) -> dict[str, Any]:
    if not path.exists():
        return {
            "log": "",
            "log_line_count": 0,
            "log_windowed": True,
            "line_start": 1,
            "line_end": 0,
            "line_limit": _normalize_bash_log_window_size(tail),
            "returned_line_count": 0,
            "has_more_before": False,
            "has_more_after": False,
            "log_read_hint": LONG_BASH_LOG_HINT,
        }
    line_limit = _normalize_bash_log_window_size(tail)
    if start is not None:
        requested_start = max(1, int(start))
        selected: list[str] = []
        total = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                total += 1
                if total < requested_start:
                    continue
                if len(selected) < line_limit:
                    selected.append(raw_line.rstrip("\n"))
        returned_count = len(selected)
        line_start = requested_start if total else 1
        line_end = requested_start + returned_count - 1 if returned_count else requested_start - 1
        return {
            "log": _join_bash_log_lines(selected),
            "log_line_count": total,
            "log_windowed": True,
            "line_start": line_start,
            "line_end": line_end,
            "line_limit": line_limit,
            "returned_line_count": returned_count,
            "has_more_before": line_start > 1,
            "has_more_after": line_end < total,
            "log_read_hint": LONG_BASH_LOG_HINT,
        }

    tail_lines: deque[str] = deque(maxlen=line_limit)
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            total += 1
            tail_lines.append(raw_line.rstrip("\n"))
    returned_count = len(tail_lines)
    line_start = max(1, total - returned_count + 1) if total else 1
    line_end = total
    return {
        "log": _join_bash_log_lines(list(tail_lines)),
        "log_line_count": total,
        "log_windowed": True,
        "line_start": line_start,
        "line_end": line_end,
        "line_limit": line_limit,
        "returned_line_count": returned_count,
        "has_more_before": line_start > 1,
        "has_more_after": False,
        "log_read_hint": LONG_BASH_LOG_HINT,
    }


def build_memory_server(context: McpContext) -> FastMCP:
    service = MemoryService(context.home)
    server = FastMCP(
        "memory",
        instructions=(
            "Quest-aware DeepScientist memory namespace. "
            "Use list_recent to recover context at turn start or resume, "
            "search before repeating literature/debug work, "
            "read only the few selected cards that matter now, "
            "write durable findings instead of chat transcripts, "
            "and promote_to_global only for stable cross-quest lessons. "
            "Prefer quest-local scope when quest context exists."
        ),
        log_level="ERROR",
    )

    @server.tool(
        name="write",
        description=(
            "Write a Markdown memory card with YAML frontmatter. "
            "Use after a non-trivial paper finding, reusable lesson, failure pattern, or idea rationale that should survive beyond chat."
        ),
    )
    def write(
        kind: str,
        title: str,
        body: str = "",
        markdown: str | None = None,
        scope: str = "quest",
        tags: list[str] | str | None = None,
        metadata: dict[str, Any] | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_scope = _resolve_scope(context, scope)
        quest_root = context.require_quest_root() if resolved_scope == "quest" else None
        return service.write_card(
            scope=resolved_scope,
            kind=kind,
            title=title,
            body=body,
            markdown=markdown,
            quest_root=quest_root,
            quest_id=context.quest_id,
            tags=tags,
            metadata=metadata,
        )

    @server.tool(
        name="read",
        description=(
            "Read a memory card by id or path. "
            "Use after list_recent or search surfaced a specific card worth reusing now."
        ),
        annotations=_read_only_tool_annotations(title="Read memory card"),
    )
    def read(
        card_id: str | None = None,
        path: str | None = None,
        scope: str = "quest",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_scope = _resolve_scope(context, scope)
        quest_root = context.require_quest_root() if resolved_scope == "quest" else None
        return service.read_card(card_id=card_id, path=path, scope=resolved_scope, quest_root=quest_root)

    @server.tool(
        name="search",
        description=(
            "Search memory cards by metadata or body text. "
            "Use before broad literature search, retries, route decisions, or repeated debugging."
        ),
        annotations=_read_only_tool_annotations(title="Search memory cards"),
    )
    def search(
        query: str,
        scope: str = "quest",
        limit: int = 10,
        kind: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_scope = _resolve_search_scope(context, scope)
        if resolved_scope == "quest" and context.quest_root is not None and service.shared_read_enabled():
            items = service.search_visible_quest_cards(
                query,
                active_quest_root=context.quest_root,
                active_quest_id=context.quest_id,
                limit=limit,
                kind=kind,
                include_shared=True,
            )
        elif resolved_scope == "both" and context.quest_root is not None:
            quest_items = service.search_visible_quest_cards(
                query,
                active_quest_root=context.quest_root,
                active_quest_id=context.quest_id,
                limit=limit,
                kind=kind,
                include_shared=service.shared_read_enabled(),
            )
            global_items = service.search(query, scope="global", limit=limit, kind=kind)
            items = quest_items + global_items
            items.sort(key=lambda item: service._visible_card_sort_key(item, active_quest_id=context.quest_id))
            items = items[:limit]
        else:
            quest_root = context.quest_root if resolved_scope in {"quest", "both"} else None
            items = service.search(query, scope=resolved_scope, quest_root=quest_root, limit=limit, kind=kind)
        return {"ok": True, "count": len(items), "items": items}

    @server.tool(
        name="list_recent",
        description=(
            "List the most recently updated memory cards. "
            "Use to recover quest context at turn start, after resume, or after a long pause."
        ),
        annotations=_read_only_tool_annotations(title="List recent memory cards"),
    )
    def list_recent(
        scope: str = "quest",
        limit: int = 10,
        kind: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_scope = _resolve_search_scope(context, scope)
        if resolved_scope == "quest" and context.quest_root is not None and service.shared_read_enabled():
            items = service.list_visible_quest_cards(
                active_quest_root=context.quest_root,
                active_quest_id=context.quest_id,
                limit=limit,
                kind=kind,
                include_shared=True,
            )
        elif resolved_scope == "both":
            quest_items = (
                service.list_visible_quest_cards(
                    active_quest_root=context.require_quest_root(),
                    active_quest_id=context.quest_id,
                    limit=limit,
                    kind=kind,
                    include_shared=service.shared_read_enabled(),
                )
                if context.quest_root is not None
                else []
            )
            global_items = service.list_recent(scope="global", limit=limit, kind=kind)
            items = quest_items + global_items
            items.sort(key=lambda item: service._visible_card_sort_key(item, active_quest_id=context.quest_id))
            items = items[:limit]
        else:
            quest_root = context.quest_root if resolved_scope == "quest" else None
            items = service.list_recent(scope=resolved_scope, quest_root=quest_root, limit=limit, kind=kind)
        return {"ok": True, "count": len(items), "items": items}

    @server.tool(
        name="promote_to_global",
        description=(
            "Promote a quest memory card into global memory. "
            "Use only for stable, cross-quest reusable lessons."
        ),
    )
    def promote_to_global(
        card_id: str | None = None,
        path: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.promote_to_global(card_id=card_id, path=path, quest_root=context.require_quest_root())

    return server


def build_artifact_server(context: McpContext) -> FastMCP:
    service = ArtifactService(context.home)
    quest_service = service.quest_service
    custom_profile = str(context.custom_profile or "").strip().lower()
    issue_only_profile = custom_profile == "settings_issue"
    start_setup_prepare_profile = custom_profile == "start_setup_prepare"
    server = FastMCP(
        "artifact",
        instructions=(
            "Quest-aware DeepScientist artifact namespace. "
            "Use artifact as the quest control plane for ideas, branches, worktrees, decisions, progress, run records, reports, approvals, and user interaction state. "
            "Git behavior is exposed through artifact only."
        ),
        log_level="ERROR",
    )

    def finalize_artifact_tool(
        payload: dict[str, Any],
        *,
        tool_name: str,
        state_change_note: str | None = None,
    ) -> dict[str, Any]:
        quest_root = context.require_quest_root().resolve()
        quest_service.record_tool_activity(
            quest_root,
            tool_name=f"artifact.{tool_name}",
        )
        watchdog = quest_service.artifact_interaction_watchdog_status(quest_root)
        return _attach_interaction_watchdog(
            payload,
            watchdog,
            state_change_note=state_change_note,
        )

    def finalize_state_changing_artifact_tool(payload: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
        return finalize_artifact_tool(
            payload,
            tool_name=tool_name,
            state_change_note=ARTIFACT_STATE_CHANGE_WATCHDOG_NOTES.get(tool_name),
        )

    def _quest_relative_path(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        path = Path(text)
        if not path.is_absolute():
            return text
        quest_root = context.require_quest_root().resolve()
        try:
            active_workspace_root = quest_service.active_workspace_root(quest_root)
        except Exception:
            active_workspace_root = None
        roots = [context.worktree_root, active_workspace_root, context.quest_root]
        seen: set[str] = set()
        for raw_root in roots:
            if raw_root is None:
                continue
            root = raw_root.resolve()
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            try:
                return path.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
        try:
            return path.resolve().relative_to(quest_root).as_posix()
        except ValueError:
            return text

    def _compact_artifact_delta(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            key: value.get(key)
            for key in (
                "schema_version",
                "delta_id",
                "delta_kind",
                "sidecar_rel_path",
                "path_count",
                "changed_paths",
            )
            if value.get(key) is not None
        }

    def _compact_paths(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, str]:
        paths: dict[str, str] = {}
        for key in keys:
            relative = _quest_relative_path(payload.get(key))
            if relative:
                paths[key] = relative
        return paths

    def compact_paper_write_result(payload: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
        compact: dict[str, Any] = {
            "ok": bool(payload.get("ok")),
            "tool_name": tool_name,
            "artifact_delta": _compact_artifact_delta(payload.get("artifact_delta")),
            "hint": "Full paper artifact content was written to files; read the listed paths or artifact_delta sidecar only when needed.",
        }
        if tool_name == "submit_paper_outline":
            compact.update(
                {
                    "mode": payload.get("mode"),
                    "outline_id": payload.get("outline_id"),
                    "paths": _compact_paths(
                        payload,
                        (
                            "outline_path",
                            "selected_outline_path",
                            "outline_manifest_path",
                            "paper_line_state_path",
                            "outline_selection_path",
                            "revised_outline_path",
                        ),
                    ),
                }
            )
            return compact

        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
        paper_line_state = payload.get("paper_line_state") if isinstance(payload.get("paper_line_state"), dict) else {}
        continuation = payload.get("continuation") if isinstance(payload.get("continuation"), dict) else {}
        compact.update(
            {
                "package_type": manifest.get("package_type"),
                "title": manifest.get("title"),
                "selected_outline_ref": manifest.get("selected_outline_ref"),
                "paper_branch": manifest.get("paper_branch") or paper_line_state.get("paper_branch"),
                "next_anchor": continuation.get("anchor") or "decision",
                "paths": _compact_paths(
                    payload,
                    (
                        "manifest_path",
                        "baseline_inventory_path",
                        "evidence_ledger_path",
                        "paper_line_state_path",
                        "manuscript_coverage_path",
                        "open_source_manifest_path",
                    ),
                ),
            }
        )
        return compact

    if issue_only_profile:
        @server.tool(
            name="prepare_github_issue",
            description=(
                "Generate a prefilled GitHub issue draft from the live local daemon's settings diagnostics. "
                "By default this also asks the browser UI to navigate to `/settings/issues` and preload the generated draft."
            ),
        )
        def prepare_github_issue(
            summary: str = "",
            user_notes: str = "",
            include_doctor: bool = True,
            include_logs: bool = True,
            open_settings_page: bool = True,
            comment: str | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            result = _prepare_github_issue_payload_via_daemon(
                context.home,
                summary=summary,
                user_notes=user_notes,
                include_doctor=include_doctor,
                include_logs=include_logs,
            )
            if open_settings_page:
                result["ui_effects"] = [_issue_draft_route_effect(result)]
            return finalize_artifact_tool(result, tool_name="prepare_github_issue")

        return server

    if start_setup_prepare_profile:
        @server.tool(
            name="prepare_start_setup_form",
            description=(
                "Prepare and apply a structured patch for the autonomous start form. "
                "Use this when the setup agent has enough information to fill or refine the form automatically."
            ),
        )
        def prepare_start_setup_form(
            form_patch: dict[str, Any] | None = None,
            session_patch: dict[str, Any] | None = None,
            message: str = "",
            comment: str | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nested_form_patch, nested_session_patch = _split_nested_start_setup_payload(form_patch)
            if nested_form_patch is not None:
                form_patch = nested_form_patch
            if session_patch is None and nested_session_patch is not None:
                session_patch = nested_session_patch
            sanitized_patch = _sanitize_start_setup_form_patch(form_patch)
            sanitized_session_patch = _sanitize_start_setup_session_patch(session_patch)
            if not sanitized_patch and not sanitized_session_patch:
                raise ValueError("At least one of `form_patch` or `session_patch` must include supported fields.")
            result = service.apply_start_setup_form_patch(
                context.require_quest_root(),
                form_patch=sanitized_patch,
                session_patch=sanitized_session_patch,
                message=message,
            )
            result["ui_effects"] = [_start_setup_patch_effect(sanitized_patch, session_patch=sanitized_session_patch, message=message)]
            return finalize_artifact_tool(result, tool_name="prepare_start_setup_form")

        return server

    @server.tool(name="record", description="Write a structured artifact record under the current quest.")
    def record(payload: dict[str, Any], comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        enriched = dict(payload)
        if comment is not None and "comment" not in enriched:
            enriched["comment"] = comment
        if context.run_id and "run_id" not in enriched:
            enriched["run_id"] = context.run_id
        if context.active_anchor and "anchor" not in enriched:
            enriched["anchor"] = context.active_anchor
        if context.agent_role:
            source = dict(enriched.get("source") or {})
            source.setdefault("kind", "agent")
            source.setdefault("role", context.agent_role)
            if context.run_id:
                source.setdefault("run_id", context.run_id)
            enriched["source"] = source
        return service.record(
            context.require_quest_root(),
            enriched,
            workspace_root=context.worktree_root,
        )

    @server.tool(name="checkpoint", description="Create a Git checkpoint in the current quest repository.")
    def checkpoint(
        message: str,
        allow_empty: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.checkpoint(
            context.worktree_root or context.require_quest_root(),
            message,
            allow_empty=allow_empty,
        )

    @server.tool(
        name="git",
        description=(
            "Run git-oriented workspace operations for Copilot mode and general quest maintenance. "
            "Use action=status|commit|branch|checkout|log|show|diff|graph."
        ),
    )
    def git(
        action: str,
        message: str | None = None,
        ref: str | None = None,
        base: str | None = None,
        head: str | None = None,
        sha: str | None = None,
        path: str | None = None,
        branch: str | None = None,
        create_from: str | None = None,
        limit: int = 30,
        allow_empty: bool = False,
        checkout_new_branch: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.git_action(
            context.require_quest_root(),
            action=action,
            workspace_root=context.worktree_root,
            message=message,
            ref=ref,
            base=base,
            head=head,
            sha=sha,
            path=path,
            branch=branch,
            create_from=create_from,
            limit=limit,
            allow_empty=allow_empty,
            checkout_new_branch=checkout_new_branch,
        )

    @server.tool(name="prepare_branch", description="Prepare an idea or run branch and optional worktree.")
    def prepare_branch(
        run_id: str | None = None,
        idea_id: str | None = None,
        branch: str | None = None,
        branch_kind: str = "run",
        create_worktree_flag: bool = True,
        start_point: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.prepare_branch(
            context.require_quest_root(),
            run_id=run_id or context.run_id,
            idea_id=idea_id,
            branch=branch,
            branch_kind=branch_kind,
            create_worktree_flag=create_worktree_flag,
            start_point=start_point,
        )

    @server.tool(
        name="activate_branch",
        description=(
            "Activate one existing durable research branch as the current workspace without creating a new lineage node. "
            "Use this when you need to revisit an older idea/main-result branch for more experiments or a fresh decision."
        ),
    )
    def activate_branch(
        branch: str | None = None,
        idea_id: str | None = None,
        run_id: str | None = None,
        anchor: str | None = "auto",
        promote_to_head: bool = False,
        create_worktree_if_missing: bool = True,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return service.activate_branch(
                context.require_quest_root(),
                branch=branch,
                idea_id=idea_id,
                run_id=run_id,
                anchor=anchor,
                promote_to_head=promote_to_head,
                create_worktree_if_missing=create_worktree_if_missing,
            )
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="activate_branch",
                    exc=exc,
                ),
                tool_name="activate_branch",
            )

    @server.tool(
        name="submit_idea",
        description=(
            "Create or revise the active research idea. "
            "Normal research flow should use mode=create together with submission_mode='line' and lineage_intent=continue_line or branch_alternative, so each durable idea submission becomes a new branch/worktree and a new user-visible research node. "
            "submission_mode='candidate' records a candidate idea brief without opening a new branch yet. "
            "mode=revise is maintenance-only for refining the current active idea.md in place. "
            "When foundation_ref is omitted, lineage_intent infers the parent and default foundation from the active research line."
        ),
    )
    def submit_idea(
        mode: str = "create",
        submission_mode: str = "line",
        idea_id: str | None = None,
        lineage_intent: str | None = None,
        title: str = "",
        problem: str = "",
        hypothesis: str = "",
        mechanism: str = "",
        method_brief: str = "",
        selection_scores: dict[str, Any] | None = None,
        mechanism_family: str = "",
        change_layer: str = "",
        source_lens: str = "",
        expected_gain: str = "",
        evidence_paths: list[str] | None = None,
        risks: list[str] | None = None,
        decision_reason: str = "",
        foundation_ref: dict[str, Any] | str | None = None,
        foundation_reason: str = "",
        next_target: str = "experiment",
        draft_markdown: str = "",
        source_candidate_id: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return service.submit_idea(
                context.require_quest_root(),
                mode=mode,
                submission_mode=submission_mode,
                idea_id=idea_id,
                lineage_intent=lineage_intent,
                title=title,
                problem=problem,
                hypothesis=hypothesis,
                mechanism=mechanism,
                method_brief=method_brief,
                selection_scores=selection_scores,
                mechanism_family=mechanism_family,
                change_layer=change_layer,
                source_lens=source_lens,
                expected_gain=expected_gain,
                evidence_paths=evidence_paths,
                risks=risks,
                decision_reason=decision_reason,
                foundation_ref=foundation_ref,
                foundation_reason=foundation_reason,
                next_target=next_target,
                draft_markdown=draft_markdown,
                source_candidate_id=source_candidate_id,
            )
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="submit_idea",
                    exc=exc,
                ),
                tool_name="submit_idea",
            )

    @server.tool(
        name="list_research_branches",
        description=(
            "List research branches with branch number, active idea, foundation info, and corresponding main-experiment results. "
            "Use before creating the next idea when you need to compare possible foundations."
        ),
        annotations=_read_only_tool_annotations(title="List research branches"),
    )
    def list_research_branches(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.list_research_branches(context.require_quest_root())

    @server.tool(
        name="resolve_runtime_refs",
        description=(
            "Resolve the current canonical research ids and refs. "
            "Use this before supplementary work when you need the active idea, latest main run, active campaign, outline, or reply-thread ids without guessing."
        ),
        annotations=_read_only_tool_annotations(title="Resolve runtime refs"),
    )
    def resolve_runtime_refs(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.resolve_runtime_refs(context.require_quest_root())

    @server.tool(
        name="get_paper_contract",
        description=(
            "Read the active paper contract, including selected outline, section result tables, evidence ledger items, "
            "analysis inventory, and experiment matrix rows. Use detail='full' by default when writing or finalizing from paper evidence."
        ),
        annotations=_read_only_tool_annotations(title="Get paper contract"),
    )
    def get_paper_contract(
        detail: str = "full",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_paper_contract(
            context.require_quest_root(),
            detail=detail,
        )

    @server.tool(
        name="get_paper_contract_health",
        description=(
            "Inspect whether the active paper line is actually unblocked for writing or finalize work. "
            "Use detail='summary' for a compact decision surface or detail='full' for exact blocking items."
        ),
        annotations=_read_only_tool_annotations(title="Get paper contract health"),
    )
    def get_paper_contract_health(
        detail: str = "summary",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_paper_contract_health(
            context.require_quest_root(),
            detail=detail,
        )

    @server.tool(
        name="validate_manuscript_coverage",
        description=(
            "Validate whether the current paper is only a draft checkpoint or a full manuscript/submission package. "
            "Checks section coverage, figures/tables, ready analysis groups, PDF, and submission checklist state."
        ),
        annotations=_read_only_tool_annotations(title="Validate manuscript coverage"),
    )
    def validate_manuscript_coverage(
        detail: str = "summary",
        minimum_sections: int = 5,
        minimum_analysis_groups: int = 5,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.validate_manuscript_coverage(
            context.require_quest_root(),
            detail=detail,
            minimum_sections=minimum_sections,
            minimum_analysis_groups=minimum_analysis_groups,
        )

    @server.tool(
        name="validate_academic_outline",
        description=(
            "Validate that the selected outline is a real paper plan before drafting. "
            "Checks the one-sentence paper idea, story spine, evidence boundaries, core claims, method, evaluation plan, "
            "4-8 planned analyses or an explicit waiver, and implementation wording leakage."
        ),
        annotations=_read_only_tool_annotations(title="Validate academic outline"),
    )
    def validate_academic_outline(
        detail: str = "summary",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.validate_academic_outline(
            context.require_quest_root(),
            detail=detail,
        )

    @server.tool(
        name="validate_manuscript_language",
        description=(
            "Scan paper draft/LaTeX for main-text implementation or route terms that should stay in artifact records "
            "or appendix reproducibility details."
        ),
        annotations=_read_only_tool_annotations(title="Validate manuscript language"),
    )
    def validate_manuscript_language(
        detail: str = "summary",
        scope: str = "main_text",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.validate_manuscript_language(
            context.require_quest_root(),
            detail=detail,
            scope=scope,
        )

    @server.tool(
        name="compile_outline_to_writing_plan",
        description=(
            "Turn the selected outline into concrete writing jobs for introduction, method, setup, results, analyses, "
            "limitations, and abstract. Use after validate_academic_outline and before drafting."
        ),
    )
    def compile_outline_to_writing_plan(
        detail: str = "summary",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.compile_outline_to_writing_plan(
                context.require_quest_root(),
                detail=detail,
            )
            return finalize_state_changing_artifact_tool(result, tool_name="compile_outline_to_writing_plan")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="compile_outline_to_writing_plan",
                    exc=exc,
                ),
                tool_name="compile_outline_to_writing_plan",
            )

    @server.tool(
        name="get_quest_state",
        description=(
            "Read the current quest runtime state without mutating anything. "
            "Use detail='summary' for a compact operational view or detail='full' for recent artifacts, runs, and active interactions."
        ),
        annotations=_read_only_tool_annotations(title="Get quest state"),
    )
    def get_quest_state(
        detail: str = "summary",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_quest_state(
            context.require_quest_root(),
            detail=detail,
        )

    @server.tool(
        name="get_global_status",
        description=(
            "Read a concise quest-global status summary for direct user questions such as overall progress, paper readiness, or the latest measured result. "
            "Use detail='brief' for a compact answer surface or detail='full' for more structured context."
        ),
        annotations=_read_only_tool_annotations(title="Get global status"),
    )
    def get_global_status(
        detail: str = "brief",
        locale: str = "zh",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_global_status(
            context.require_quest_root(),
            detail=detail,
            locale=locale,
        )

    @server.tool(
        name="get_research_map_status",
        description=(
            "Read the current research-node progress state that corresponds to the quest canvas. "
            "Returns the active workspace node, research head node, node history, runtime refs, canvas freshness, recommended activation ref, and Git identifiers so agents can recover progress or switch branches without guessing."
        ),
        annotations=_read_only_tool_annotations(title="Get research map status"),
    )
    def get_research_map_status(
        detail: str = "summary",
        locale: str = "zh",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_research_map_status(
            context.require_quest_root(),
            detail=detail,
            locale=locale,
        )

    @server.tool(
        name="get_benchstore_catalog",
        description=(
            "Read the BenchStore catalog with current-device recommendation hints. "
            "Use detail='summary' for compact recommendations or detail='full' for the full structured catalog."
        ),
        annotations=_read_only_tool_annotations(title="Get BenchStore catalog"),
    )
    def get_benchstore_catalog(
        detail: str = "summary",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_benchstore_catalog(
            context.require_quest_root(),
            detail=detail,
        )

    @server.tool(
        name="get_start_setup_context",
        description=(
            "Read the current autonomous start-setup context, including the suggested form and selected benchmark context when present."
        ),
        annotations=_read_only_tool_annotations(title="Get start setup context"),
    )
    def get_start_setup_context(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.get_start_setup_context(context.require_quest_root())

    @server.tool(
        name="get_method_scoreboard",
        description=(
            "Read or refresh the quest-level method scoreboard so overall experiment history and the current incumbent line are explicit."
        ),
    )
    def get_method_scoreboard(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.refresh_method_scoreboard(context.require_quest_root())

    @server.tool(
        name="get_optimization_frontier",
        description=(
            "Read a compact optimization-frontier summary for algorithm-first quests. "
            "It summarizes candidate briefs, promoted lines, recent implementation candidates, stagnant branches, fusion opportunities, and the recommended next mode."
        ),
        annotations=_read_only_tool_annotations(title="Get optimization frontier"),
    )
    def get_optimization_frontier(
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_optimization_frontier(
            context.require_quest_root(),
        )

    @server.tool(
        name="read_quest_documents",
        description=(
            "Read durable quest documents such as brief, plan, status, summary, and active user requirements. "
            "Use mode='excerpt' for compact recovery or mode='full' when exact document wording matters."
        ),
        annotations=_read_only_tool_annotations(title="Read quest documents"),
    )
    def read_quest_documents(
        names: list[str] | None = None,
        mode: str = "excerpt",
        max_lines: int = 12,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.read_quest_documents(
            context.require_quest_root(),
            names=names,
            mode=mode,
            max_lines=max_lines,
        )

    @server.tool(
        name="get_conversation_context",
        description=(
            "Read a recent window of quest conversation history. "
            "Use this when earlier user/assistant continuity matters and the current prompt intentionally keeps only a compact turn launcher."
        ),
        annotations=_read_only_tool_annotations(title="Get conversation context"),
    )
    def get_conversation_context(
        limit: int = 12,
        include_attachments: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_conversation_context(
            context.require_quest_root(),
            limit=limit,
            include_attachments=include_attachments,
        )

    @server.tool(
        name="get_analysis_campaign",
        description=(
            "Get one analysis campaign manifest with todo items, slice status, and next pending slice. "
            "Pass campaign_id='active' or omit it to recover the active campaign."
        ),
        annotations=_read_only_tool_annotations(title="Get analysis campaign"),
    )
    def get_analysis_campaign(
        campaign_id: str | None = "active",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.get_analysis_campaign(context.require_quest_root(), campaign_id=campaign_id)

    @server.tool(
        name="record_main_experiment",
        description=(
            "Record the completed main experiment on the active idea workspace. "
            "This writes RUN.md and RESULT.json, compares metrics to the attached baseline, "
            "derives breakthrough status, and notifies bound conversations."
        ),
    )
    def record_main_experiment(
        run_id: str,
        title: str = "",
        hypothesis: str = "",
        setup: str = "",
        execution: str = "",
        results: str = "",
        conclusion: str = "",
        metric_rows: list[dict[str, Any]] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        metric_contract: dict[str, Any] | None = None,
        evidence_paths: list[str] | None = None,
        changed_files: list[str] | None = None,
        config_paths: list[str] | None = None,
        notes: list[str] | None = None,
        dataset_scope: str = "full",
        verdict: str = "",
        status: str = "completed",
        baseline_id: str | None = None,
        baseline_variant_id: str | None = None,
        evaluation_summary: dict[str, Any] | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return service.record_main_experiment(
                context.require_quest_root(),
                run_id=run_id,
                title=title,
                hypothesis=hypothesis,
                setup=setup,
                execution=execution,
                results=results,
                conclusion=conclusion,
                metric_rows=metric_rows,
                metrics_summary=metrics_summary,
                metric_contract=metric_contract,
                evidence_paths=evidence_paths,
                changed_files=changed_files,
                config_paths=config_paths,
                notes=notes,
                dataset_scope=dataset_scope,
                verdict=verdict,
                status=status,
                baseline_id=baseline_id,
                baseline_variant_id=baseline_variant_id,
                evaluation_summary=evaluation_summary,
                strict_metric_contract=True,
            )
        except MetricContractValidationError as exc:
            return _metric_validation_error_payload(exc)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="record_main_experiment",
                    exc=exc,
                ),
                tool_name="record_main_experiment",
            )

    @server.tool(
        name="create_analysis_campaign",
        description=(
            "Create a structured analysis campaign from the current workspace/result node. "
            "Use this for one or more extra experiments; each slice receives its own child branch/worktree and explicit requirements."
        ),
    )
    def create_analysis_campaign(
        campaign_title: str,
        campaign_goal: str,
        slices: list[dict[str, Any]],
        parent_run_id: str | None = None,
        campaign_origin: dict[str, Any] | None = None,
        selected_outline_ref: str | None = None,
        research_questions: list[str] | None = None,
        experimental_designs: list[str] | None = None,
        todo_items: list[dict[str, Any]] | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return service.create_analysis_campaign(
                context.require_quest_root(),
                campaign_title=campaign_title,
                campaign_goal=campaign_goal,
                parent_run_id=parent_run_id,
                slices=slices,
                campaign_origin=campaign_origin,
                selected_outline_ref=selected_outline_ref,
                research_questions=research_questions,
                experimental_designs=experimental_designs,
                todo_items=todo_items,
            )
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="create_analysis_campaign",
                    exc=exc,
                ),
                tool_name="create_analysis_campaign",
            )

    @server.tool(
        name="submit_paper_outline",
        description=(
            "Persist a paper outline candidate, select an approved outline, or revise the selected outline. "
            "Use this before analysis campaigns that should support final writing claims. "
            "For paper-facing work, put the paper idea and section plan in detailed_outline.paper_view, "
            "and keep result rows, paths, run ids, and reproducibility details in detailed_outline.evidence_view. "
            "Good paper_view records a one-sentence thesis, what the reader should learn, evidence boundaries, "
            "and a 4-8 item analysis plan when the paper is mature."
        ),
    )
    def submit_paper_outline(
        mode: str = "candidate",
        outline_id: str | None = None,
        title: str = "",
        note: str = "",
        story: str = "",
        ten_questions: list[str] | None = None,
        detailed_outline: dict[str, Any] | None = None,
        review_result: str | None = None,
        selected_reason: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.submit_paper_outline(
                context.require_quest_root(),
                mode=mode,
                outline_id=outline_id,
                title=title,
                note=note,
                story=story,
                ten_questions=ten_questions,
                detailed_outline=detailed_outline,
                review_result=review_result,
                selected_reason=selected_reason,
            )
            return finalize_state_changing_artifact_tool(
                compact_paper_write_result(result, tool_name="submit_paper_outline"),
                tool_name="submit_paper_outline",
            )
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="submit_paper_outline",
                    exc=exc,
                ),
                tool_name="submit_paper_outline",
            )

    @server.tool(
        name="list_paper_outlines",
        description=(
            "List candidate/revised paper outlines and the selected outline reference. "
            "Use this before writing-facing analysis campaigns or when you need a valid outline_id."
        ),
        annotations=_read_only_tool_annotations(title="List paper outlines"),
    )
    def list_paper_outlines(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.list_paper_outlines(context.require_quest_root())

    @server.tool(
        name="submit_paper_bundle",
        description=(
            "Persist a paper bundle manifest. Defaults to a draft checkpoint; use package_type='submission_package' only for submission-ready manuscripts."
        ),
    )
    def submit_paper_bundle(
        title: str | None = None,
        summary: str = "",
        outline_path: str | None = None,
        draft_path: str | None = None,
        writing_plan_path: str | None = None,
        references_path: str | None = None,
        claim_evidence_map_path: str | None = None,
        compile_report_path: str | None = None,
        pdf_path: str | None = None,
        latex_root_path: str | None = None,
        package_type: str = "draft_checkpoint",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.submit_paper_bundle(
                context.require_quest_root(),
                title=title,
                summary=summary,
                outline_path=outline_path,
                draft_path=draft_path,
                writing_plan_path=writing_plan_path,
                references_path=references_path,
                claim_evidence_map_path=claim_evidence_map_path,
                compile_report_path=compile_report_path,
                pdf_path=pdf_path,
                latex_root_path=latex_root_path,
                package_type=package_type,
            )
            return finalize_state_changing_artifact_tool(
                compact_paper_write_result(result, tool_name="submit_paper_bundle"),
                tool_name="submit_paper_bundle",
            )
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="submit_paper_bundle",
                    exc=exc,
                ),
                tool_name="submit_paper_bundle",
            )

    @server.tool(
        name="record_analysis_slice",
        description=(
            "Record the full setup, execution, and result for one analysis slice. "
            "This also mirrors the result back to the parent experiment branch and moves to the next slice automatically."
        ),
    )
    def record_analysis_slice(
        campaign_id: str,
        slice_id: str,
        status: str = "completed",
        setup: str = "",
        execution: str = "",
        results: str = "",
        evidence_paths: list[str] | None = None,
        metric_rows: list[dict[str, Any]] | None = None,
        deviations: list[str] | None = None,
        claim_impact: str | None = None,
        reviewer_resolution: str | None = None,
        manuscript_update_hint: str | None = None,
        next_recommendation: str | None = None,
        dataset_scope: str = "full",
        subset_approval_ref: str | None = None,
        comparison_baselines: list[dict[str, Any]] | None = None,
        evaluation_summary: dict[str, Any] | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.record_analysis_slice(
            context.require_quest_root(),
            campaign_id=campaign_id,
            slice_id=slice_id,
            status=status,
            setup=setup,
            execution=execution,
            results=results,
            evidence_paths=evidence_paths,
            metric_rows=metric_rows,
            deviations=deviations,
            claim_impact=claim_impact,
            reviewer_resolution=reviewer_resolution,
            manuscript_update_hint=manuscript_update_hint,
            next_recommendation=next_recommendation,
            dataset_scope=dataset_scope,
            subset_approval_ref=subset_approval_ref,
            comparison_baselines=comparison_baselines,
            evaluation_summary=evaluation_summary,
        )

    @server.tool(name="publish_baseline", description="Publish a quest baseline to the global baseline registry.")
    def publish_baseline(
        payload: dict[str, Any],
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        enriched = dict(payload)
        if comment is not None and "comment" not in enriched:
            enriched["comment"] = comment
        enriched.setdefault("source", {"kind": "artifact_publish", "quest_id": context.quest_id, "quest_root": str(context.require_quest_root())})
        try:
            result = service.publish_baseline(context.require_quest_root(), enriched)
            return finalize_state_changing_artifact_tool(result, tool_name="publish_baseline")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="publish_baseline",
                    exc=exc,
                ),
                tool_name="publish_baseline",
            )

    @server.tool(name="attach_baseline", description="Attach a published baseline to the current quest.")
    def attach_baseline(
        baseline_id: str,
        variant_id: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.attach_baseline(context.require_quest_root(), baseline_id, variant_id)
            return finalize_state_changing_artifact_tool(result, tool_name="attach_baseline")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="attach_baseline",
                    exc=exc,
                ),
                tool_name="attach_baseline",
            )

    @server.tool(
        name="confirm_baseline",
        description=(
            "Confirm the active quest baseline and open the stage gate into idea work. "
            "The baseline path must point at a quest-local baseline under baselines/local or baselines/imported. "
            "Descriptions, derivations, and source refs must live on entries inside "
            "`metric_contract.metrics`."
        ),
    )
    def confirm_baseline(
        baseline_path: str,
        baseline_id: str | None = None,
        variant_id: str | None = None,
        summary: str | None = None,
        baseline_kind: str | None = None,
        metric_contract: MetricContractPayload | None = None,
        metric_directions: dict[str, str] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: PrimaryMetricPayload | None = None,
        auto_advance: bool = True,
        comment: str | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
        try:
            result = service.confirm_baseline(
                context.require_quest_root(),
                baseline_path=baseline_path,
                comment=comment,
                baseline_id=baseline_id,
                variant_id=variant_id,
                summary=summary,
                baseline_kind=baseline_kind,
                metric_contract=metric_contract.model_dump(exclude_none=True) if metric_contract is not None else None,
                metric_directions=metric_directions,
                metrics_summary=metrics_summary,
                primary_metric=primary_metric.model_dump(exclude_none=True) if primary_metric is not None else None,
                auto_advance=auto_advance,
                strict_metric_contract=True,
            )
            return finalize_state_changing_artifact_tool(result, tool_name="confirm_baseline")
        except MetricContractValidationError as exc:
            return _metric_validation_error_payload(exc)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="confirm_baseline",
                    exc=exc,
                ),
                tool_name="confirm_baseline",
            )

    @server.tool(
        name="overwrite_baseline",
        description=(
            "Refresh an already accepted baseline after verified code, variant, or canonical metric changes. "
            "This rewrites the active baseline reference and downstream inventories, so comparator-breaking changes "
            "should usually become a new baseline id or variant instead of an in-place overwrite."
        ),
    )
    def overwrite_baseline(
        change_summary: str,
        baseline_id: str | None = None,
        baseline_path: str | None = None,
        variant_id: str | None = None,
        summary: str | None = None,
        baseline_kind: str | None = None,
        metric_contract: MetricContractPayload | None = None,
        metric_directions: dict[str, str] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: PrimaryMetricPayload | None = None,
        supplementary_baselines: list[SupplementaryBaselinePayload] | None = None,
        overwrite_scope: str = "full_refresh",
        allow_path_change: bool = False,
        allow_protocol_breaking_change: bool = False,
        sync_requested_baseline_ref: bool = True,
        refresh_analysis_inventory: bool = True,
        refresh_paper_inventory: bool = True,
        auto_advance: bool = True,
        comment: str | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
        try:
            result = service.overwrite_baseline(
                context.require_quest_root(),
                baseline_id=baseline_id,
                baseline_path=baseline_path,
                variant_id=variant_id,
                summary=summary,
                change_summary=change_summary,
                baseline_kind=baseline_kind,
                metric_contract=metric_contract.model_dump(exclude_none=True) if metric_contract is not None else None,
                metric_directions=metric_directions,
                metrics_summary=metrics_summary,
                primary_metric=primary_metric.model_dump(exclude_none=True) if primary_metric is not None else None,
                supplementary_baselines=[
                    item.model_dump(exclude_none=True) for item in (supplementary_baselines or [])
                ]
                or None,
                overwrite_scope=overwrite_scope,
                allow_path_change=allow_path_change,
                allow_protocol_breaking_change=allow_protocol_breaking_change,
                sync_requested_baseline_ref=sync_requested_baseline_ref,
                refresh_analysis_inventory=refresh_analysis_inventory,
                refresh_paper_inventory=refresh_paper_inventory,
                auto_advance=auto_advance,
                strict_metric_contract=True,
                comment=comment,
            )
            return finalize_state_changing_artifact_tool(result, tool_name="overwrite_baseline")
        except MetricContractValidationError as exc:
            return _metric_validation_error_payload(exc)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="overwrite_baseline",
                    exc=exc,
                ),
                tool_name="overwrite_baseline",
            )

    @server.tool(
        name="overwrite_baseline",
        description=(
            "Refresh an already accepted baseline after verified code, variant, or canonical metric changes. "
            "This rewrites the active baseline reference and downstream inventories, so comparator-breaking changes "
            "should usually become a new baseline id or variant instead of an in-place overwrite."
        ),
    )
    def overwrite_baseline(
        change_summary: str,
        baseline_id: str | None = None,
        baseline_path: str | None = None,
        variant_id: str | None = None,
        summary: str | None = None,
        baseline_kind: str | None = None,
        metric_contract: MetricContractPayload | None = None,
        metric_directions: dict[str, str] | None = None,
        metrics_summary: dict[str, Any] | None = None,
        primary_metric: PrimaryMetricPayload | None = None,
        supplementary_baselines: list[SupplementaryBaselinePayload] | None = None,
        overwrite_scope: str = "full_refresh",
        allow_path_change: bool = False,
        allow_protocol_breaking_change: bool = False,
        sync_requested_baseline_ref: bool = True,
        refresh_analysis_inventory: bool = True,
        refresh_paper_inventory: bool = True,
        auto_advance: bool = True,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.overwrite_baseline(
                context.require_quest_root(),
                baseline_id=baseline_id,
                baseline_path=baseline_path,
                variant_id=variant_id,
                summary=summary,
                change_summary=change_summary,
                baseline_kind=baseline_kind,
                metric_contract=metric_contract.model_dump(exclude_none=True) if metric_contract is not None else None,
                metric_directions=metric_directions,
                metrics_summary=metrics_summary,
                primary_metric=primary_metric.model_dump(exclude_none=True) if primary_metric is not None else None,
                supplementary_baselines=[
                    item.model_dump(exclude_none=True) for item in (supplementary_baselines or [])
                ]
                or None,
                overwrite_scope=overwrite_scope,
                allow_path_change=allow_path_change,
                allow_protocol_breaking_change=allow_protocol_breaking_change,
                sync_requested_baseline_ref=sync_requested_baseline_ref,
                refresh_analysis_inventory=refresh_analysis_inventory,
                refresh_paper_inventory=refresh_paper_inventory,
                auto_advance=auto_advance,
                strict_metric_contract=True,
                comment=comment,
            )
            return finalize_state_changing_artifact_tool(result, tool_name="overwrite_baseline")
        except MetricContractValidationError as exc:
            return _metric_validation_error_payload(exc)

    @server.tool(
        name="waive_baseline",
        description="Explicitly waive the baseline gate and advance with a durable written reason.",
    )
    def waive_baseline(
        reason: str,
        auto_advance: bool = True,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            result = service.waive_baseline(
                context.require_quest_root(),
                reason=reason,
                comment=comment,
                auto_advance=auto_advance,
            )
            return finalize_state_changing_artifact_tool(result, tool_name="waive_baseline")
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            return finalize_artifact_tool(
                _artifact_guided_error_payload(
                    service,
                    context.require_quest_root(),
                    tool_name="waive_baseline",
                    exc=exc,
                ),
                tool_name="waive_baseline",
            )

    @server.tool(
        name="arxiv",
        description=(
            "Interact with the quest-local arXiv library. "
            "Use mode='read' to read one paper by id with local-first automatic persistence, "
            "or mode='list' to list the saved arXiv items for the current quest."
        ),
    )
    def arxiv(
        paper_id: str | None = None,
        mode: str = "read",
        full_text: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.arxiv(
            paper_id,
            mode=mode,
            full_text=full_text,
            quest_root=context.require_quest_root(),
        )

    @server.tool(name="refresh_summary", description="Refresh SUMMARY.md from recent artifact state.")
    def refresh_summary(
        reason: str | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return service.refresh_summary(context.require_quest_root(), reason=reason)

    @server.tool(name="render_git_graph", description="Render the quest Git graph to JSON, SVG, and PNG.")
    def render_git_graph(comment: str | dict[str, Any] | None = None) -> dict[str, Any]:
        return service.render_git_graph(context.require_quest_root())

    @server.tool(
        name="interact",
        description=(
            "Send a structured user-facing interaction and optionally fetch new inbound messages. "
            "Use kind='answer' for direct user questions, kind='progress' for long-running checkpoint updates, "
            "kind='milestone' for material state changes, and kind='decision_request' only for true blocking decisions."
        ),
    )
    def interact(
        kind: str = "progress",
        message: str = "",
        response_phase: str = "ack",
        importance: str = "info",
        deliver_to_bound_conversations: bool = True,
        include_recent_inbound_messages: bool = True,
        recent_message_limit: int = 8,
        attachments: list[dict[str, Any]] | None = None,
        interaction_id: str | None = None,
        expects_reply: bool | None = None,
        reply_mode: str | None = None,
        options: list[dict[str, Any]] | None = None,
        surface_actions: list[dict[str, Any]] | None = None,
        connector_hints: dict[str, Any] | None = None,
        allow_free_text: bool = True,
        reply_schema: dict[str, Any] | None = None,
        reply_to_interaction_id: str | None = None,
        supersede_open_requests: bool = True,
        dedupe_key: str | None = None,
        suppress_if_unchanged: bool | None = None,
        min_interval_seconds: int | None = None,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = service.interact(
            context.require_quest_root(),
            kind=kind,
            message=message,
            response_phase=response_phase,
            importance=importance,
            deliver_to_bound_conversations=deliver_to_bound_conversations,
            include_recent_inbound_messages=include_recent_inbound_messages,
            recent_message_limit=recent_message_limit,
            attachments=attachments,
            interaction_id=interaction_id,
            expects_reply=expects_reply,
            reply_mode=reply_mode,
            options=options,
            surface_actions=surface_actions,
            connector_hints=connector_hints,
            allow_free_text=allow_free_text,
            reply_schema=reply_schema,
            reply_to_interaction_id=reply_to_interaction_id,
            supersede_open_requests=supersede_open_requests,
            dedupe_key=dedupe_key,
            suppress_if_unchanged=suppress_if_unchanged,
            min_interval_seconds=min_interval_seconds,
        )
        result["interaction_watchdog"] = quest_service.artifact_interaction_watchdog_status(context.require_quest_root())
        return result

    @server.tool(
        name="complete_quest",
        description=(
            "Mark the quest as completed after the user explicitly approved completion via a blocking "
            "artifact.interact(...) request whose reply_schema.decision_type is `quest_completion_approval`."
        ),
    )
    def complete_quest(
        summary: str = "",
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = service.complete_quest(
            context.require_quest_root(),
            summary=summary,
        )
        if result.get("ok") is True and str(result.get("status") or "").strip() == "completed":
            return finalize_state_changing_artifact_tool(result, tool_name="complete_quest")
        return result

    return server


def build_bash_exec_server(context: McpContext) -> FastMCP:
    service = BashExecService(context.home)
    quest_service = QuestService(context.home)
    server = FastMCP(
        "bash_exec",
        instructions=(
            "Quest-aware DeepScientist bash execution namespace with detached execution, durable logs, and progress tracking. "
            "Use bash_exec when commands should be monitored, revisited from logs, stopped later, or resumed after interruption."
        ),
        log_level="ERROR",
    )

    @server.tool(
        name="bash_exec",
        description=(
            "Execute a bash command inside the current quest. "
            "mode=detach returns immediately. mode=await/create waits for completion up to a bounded wait window, "
            "then returns a running-session notice if the command is still active. "
            "mode=read returns the saved log. It returns the full saved log up to 2000 lines, "
            "or a 500-line head plus 1500-line tail preview for longer logs. "
            "Use start/tail for rendered line windows and tail_limit/after_seq for seq-based monitoring. "
            "mode=kill requests termination. "
            "mode=list shows known quest-local bash sessions. mode=history shows a compact reverse-chronological bash id list."
        ),
    )
    def bash_exec(
        command: Any = "",
        mode: str = "detach",
        id: str | None = None,
        reason: str | None = None,
        workdir: str | None = None,
        env: dict[str, Any] | None = None,
        export_log: bool = False,
        export_log_to: str | None = None,
        timeout_seconds: int | None = None,
        wait_timeout_seconds: int | None = None,
        status: str | None = None,
        kind: str | None = None,
        agent_ids: list[str] | None = None,
        agent_instance_ids: list[str] | None = None,
        chat_session_id: str | None = None,
        limit: int = 20,
        start: int | None = None,
        tail: int | None = None,
        tail_limit: int | None = None,
        before_seq: int | None = None,
        after_seq: int | None = None,
        order: str = "asc",
        include_log: bool = False,
        wait: bool = False,
        force: bool = False,
        comment: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        quest_root = context.require_quest_root().resolve()

        def finalize(payload: dict[str, Any]) -> dict[str, Any]:
            quest_service.record_tool_activity(
                quest_root,
                tool_name=f"bash_exec.{normalized_mode}",
            )
            watchdog = quest_service.artifact_interaction_watchdog_status(quest_root)
            return _attach_interaction_watchdog(payload, watchdog)

        normalized_mode = (mode or "detach").strip().lower()
        if normalized_mode == "create":
            normalized_mode = "await"
        if normalized_mode not in {"detach", "await", "read", "kill", "list", "history"}:
            raise ValueError("Mode must be one of `detach`, `await`, `create`, `read`, `kill`, `list`, or `history`.")
        normalized_command = _normalize_bash_exec_command_input(command)
        normalized_timeout_seconds = _normalize_positive_timeout_seconds(
            timeout_seconds,
            field_name="timeout_seconds",
        )
        normalized_wait_timeout_seconds = _normalize_positive_timeout_seconds(
            wait_timeout_seconds,
            field_name="wait_timeout_seconds",
        )

        def build_await_payload(session: dict[str, Any], *, wait_timeout: int | None) -> dict[str, Any]:
            payload = service.build_tool_result(
                context,
                session=session,
                include_log=False,
                export_log=export_log,
                export_log_to=export_log_to,
            )
            session_status = str(session.get("status") or "").strip().lower()
            if wait_timeout is not None and session_status not in BASH_EXEC_TERMINAL_STATUSES:
                payload.update(
                    _build_bash_exec_wait_notice(
                        bash_id=str(session["bash_id"]),
                        wait_timeout_seconds=wait_timeout,
                        status=session_status,
                    )
                )
            return payload

        if normalized_mode in {"list", "history"}:
            resolved_limit = 500 if normalized_mode == "history" and limit == 20 else max(1, min(limit, 500))
            items = service.list_sessions(
                quest_root,
                status=status,
                kind=kind,
                agent_ids=agent_ids,
                agent_instance_ids=agent_instance_ids,
                chat_session_id=chat_session_id,
                limit=resolved_limit,
            )
            history_lines = [service.format_history_line(item) for item in items]
            counts: dict[str, int] = {}
            for item in items:
                item_status = str(item.get("status") or "unknown")
                counts[item_status] = counts.get(item_status, 0) + 1
            payload = {
                "count": len(items),
                "items": items,
                "status_counts": counts,
                "summary": service.summary(quest_root),
                "history_lines": history_lines,
            }
            if normalized_mode == "history":
                return finalize({
                    "count": len(items),
                    "lines": history_lines,
                    "items": items,
                })
            return finalize(payload)
        if normalized_mode == "read":
            bash_id = service.resolve_session_id(quest_root, id)
            session = service.get_session(quest_root, bash_id)
            normalized_order = (order or "asc").strip().lower()
            if normalized_order not in {"asc", "desc"}:
                normalized_order = "asc"
            if tail is not None and tail_limit is not None:
                raise ValueError("Use either `tail` or `tail_limit`, not both.")
            use_line_window = start is not None or tail is not None or (start is not None and tail_limit is not None)
            if use_line_window and (before_seq is not None or after_seq is not None):
                raise ValueError("`start`/`tail` cannot be combined with `before_seq` or `after_seq`.")
            if use_line_window and normalized_order != "asc":
                raise ValueError("`start`/`tail` windows only support `order='asc'`.")
            if use_line_window:
                payload = service.build_tool_result(
                    context,
                    session=session,
                    include_log=False,
                    export_log=export_log,
                    export_log_to=export_log_to,
                )
                payload.update(
                    _build_bash_log_window_from_path(
                        service.terminal_log_path(quest_root, bash_id),
                        start=start,
                        tail=tail if tail is not None else tail_limit,
                    )
                )
                return finalize(_attach_bash_log_truncation_metadata(payload))
            use_tail = tail_limit is not None or before_seq is not None or after_seq is not None or normalized_order != "asc"
            if use_tail:
                resolved_tail_limit = max(1, min(int(tail_limit or 200), 1000))
                entries, tail_meta = service.read_log_entries(
                    quest_root,
                    bash_id,
                    limit=resolved_tail_limit,
                    before_seq=before_seq,
                    after_seq=after_seq,
                    order=normalized_order,
                    prefer_visible=True,
                )
                payload = service.build_tool_result(
                    context,
                    session=session,
                    include_log=include_log,
                    export_log=export_log,
                    export_log_to=export_log_to,
                )
                payload["tail"] = entries
                payload["tail_limit"] = tail_meta.get("tail_limit")
                payload["tail_start_seq"] = tail_meta.get("tail_start_seq")
                payload["latest_seq"] = tail_meta.get("latest_seq")
                payload["after_seq"] = tail_meta.get("after_seq")
                payload["before_seq"] = tail_meta.get("before_seq")
                payload["order"] = normalized_order
                visible_seqs = [int(entry.get("seq") or 0) for entry in entries if int(entry.get("seq") or 0) > 0]
                seq_window_start = min(visible_seqs) if visible_seqs else None
                seq_window_end = max(visible_seqs) if visible_seqs else None
                latest_seq_value = tail_meta.get("latest_seq")
                seqs_before_window = max(int(seq_window_start or 0) - 1, 0) if seq_window_start is not None else None
                seqs_after_window = (
                    max(int(latest_seq_value or 0) - int(seq_window_end or 0), 0)
                    if seq_window_end is not None and latest_seq_value is not None
                    else None
                )
                payload["seq_window_start"] = seq_window_start
                payload["seq_window_end"] = seq_window_end
                payload["seq_has_more_before"] = bool(seqs_before_window and seqs_before_window > 0)
                payload["seq_has_more_after"] = bool(seqs_after_window and seqs_after_window > 0)
                payload["seqs_before_window"] = seqs_before_window
                payload["seqs_after_window"] = seqs_after_window
                payload["tail_is_partial"] = payload["seq_has_more_before"] or payload["seq_has_more_after"]
                if payload["tail_is_partial"]:
                    before_text = (
                        f"{seqs_before_window} seq(s) before"
                        if seqs_before_window is not None
                        else "some earlier seqs outside this filtered window"
                    )
                    after_text = (
                        f"{seqs_after_window} seq(s) after"
                        if seqs_after_window is not None
                        else "some later seqs outside this filtered window"
                    )
                    payload["log_truncation_notice"] = (
                        "This seq-based bash_exec read is only a partial window, not the full log. "
                        f"It currently covers seq {seq_window_start} to {seq_window_end}; there are {before_text} and {after_text}. "
                        "Continue with before_seq / after_seq or adjust tail_limit if you need more surrounding output."
                    )
                return finalize(payload)
            payload = service.build_tool_result(
                context,
                session=session,
                include_log=False,
                export_log=export_log,
                export_log_to=export_log_to,
            )
            payload.update(_build_default_bash_log_payload_from_path(service.terminal_log_path(quest_root, bash_id)))
            return finalize(_attach_bash_log_truncation_metadata(payload))
        if normalized_mode == "kill":
            bash_id = service.resolve_session_id(quest_root, id)
            session = service.request_stop(
                quest_root,
                bash_id,
                reason=reason,
                user_id=f"agent:{context.agent_role or 'pi'}",
                force=force,
            )
            if wait:
                resolved_wait_timeout = normalized_wait_timeout_seconds or normalized_timeout_seconds
                session = service.wait_for_session(quest_root, bash_id, timeout_seconds=resolved_wait_timeout)
            return finalize(service.build_tool_result(context, session=session, include_log=False))
        if normalized_mode == "await" and not normalized_command:
            bash_id = service.resolve_session_id(quest_root, id)
            resolved_wait_timeout = (
                normalized_wait_timeout_seconds
                or normalized_timeout_seconds
                or DEFAULT_BASH_EXEC_AWAIT_WAIT_TIMEOUT_SECONDS
            )
            session = service.wait_for_session(quest_root, bash_id, timeout_seconds=resolved_wait_timeout)
            return finalize(build_await_payload(session, wait_timeout=resolved_wait_timeout))
        if not normalized_command.strip():
            raise ValueError("command is required for `detach` and `await`.")
        session = service.start_session(
            context,
            command=normalized_command,
            mode=normalized_mode,
            workdir=workdir,
            env=env,
            timeout_seconds=normalized_timeout_seconds,
            comment=comment,
        )
        if normalized_mode == "detach":
            return finalize(service.build_tool_result(context, session=session, include_log=False))
        resolved_wait_timeout = (
            normalized_wait_timeout_seconds
            or DEFAULT_BASH_EXEC_AWAIT_WAIT_TIMEOUT_SECONDS
        )
        session = service.wait_for_session(
            quest_root,
            str(session["bash_id"]),
            timeout_seconds=resolved_wait_timeout,
        )
        return finalize(build_await_payload(session, wait_timeout=resolved_wait_timeout))

    return server


def _resolve_scope(context: McpContext, scope: str) -> str:
    normalized = (scope or "quest").strip().lower()
    if normalized == "quest" and context.quest_root is None:
        raise ValueError("Quest-local memory call requires quest context.")
    if normalized not in {"quest", "global"}:
        raise ValueError("Scope must be `quest` or `global`.")
    return normalized


def _resolve_search_scope(context: McpContext, scope: str) -> str:
    normalized = (scope or "quest").strip().lower()
    if normalized in {"quest", "both"} and context.quest_root is None:
        return "global"
    if normalized not in {"quest", "global", "both"}:
        raise ValueError("Scope must be `quest`, `global`, or `both`.")
    return normalized


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def main() -> int:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="DeepScientist built-in MCP server")
    parser.add_argument("--namespace", choices=("memory", "artifact", "bash_exec"), required=True)
    args = parser.parse_args()
    context = McpContext.from_env()
    if args.namespace == "memory":
        build_memory_server(context).run("stdio")
    elif args.namespace == "artifact":
        build_artifact_server(context).run("stdio")
    else:
        build_bash_exec_server(context).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
