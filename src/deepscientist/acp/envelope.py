from __future__ import annotations

from typing import Any

from ..shared import generate_id, utc_now


def build_slash_commands(quest_id: str | None = None) -> list[dict[str, Any]]:
    quest_arg = quest_id or "<quest_id>"
    return [
        {
            "name": "/projects",
            "description": "Open the quest browser or jump to a quest by id.",
        },
        {
            "name": "/new",
            "description": "Create a new quest explicitly, for example `/new reproduce the baseline`.",
        },
        {
            "name": "/delete",
            "description": f"Delete a quest (destructive; requires confirmation), for example `/delete {quest_arg} --yes`.",
        },
        {
            "name": "/resume",
            "description": f"Resume a stopped quest, for example `/resume {quest_arg}`.",
        },
        {
            "name": "/stop",
            "description": f"Stop a running quest, for example `/stop {quest_arg}`.",
        },
        {
            "name": "/status",
            "description": "Show the current quest snapshot and latest milestone.",
        },
        {
            "name": "/summary",
            "description": "Show the compact quest summary written from artifacts.",
        },
        {
            "name": "/metrics",
            "description": "Show the latest recorded run metrics or selected run metrics.",
        },
        {
            "name": "/graph",
            "description": "Refresh and show the Git branch graph for the quest repository.",
        },
        {
            "name": "/terminal",
            "description": "Send a command to the quest terminal, or use `/terminal -R` to restore the current shell state.",
        },
        {
            "name": "/approve",
            "description": "Approve a pending decision with a reason, for example `/approve decision-001 Proceed`.",
        },
        {
            "name": "/note",
            "description": "Store a user note, for example `/note revisit the baseline choice`.",
        },
        {
            "name": "/use",
            "description": f"Bind a connector conversation to a quest, for example `/use {quest_arg}`.",
        },
    ]


def build_session_descriptor(
    snapshot: dict[str, Any],
    *,
    session_id: str | None = None,
    transport: str = "sse",
) -> dict[str, Any]:
    quest_id = str(snapshot.get("quest_id") or "")
    return {
        "profile": "deepscientist-acp-compat/v1",
        "protocol": "agent-client-protocol",
        "transport": transport,
        "session_id": session_id or f"quest:{quest_id}",
        "quest_id": quest_id,
        "cwd": snapshot.get("current_workspace_root") or snapshot.get("quest_root"),
        "title": snapshot.get("title") or quest_id,
        "runner": snapshot.get("runner"),
        "status": snapshot.get("status"),
        "active_anchor": snapshot.get("active_anchor"),
        "bound_conversations": snapshot.get("bound_conversations") or [],
        "mcp_servers": [
            {"name": "memory", "transport": "stdio", "scope": "quest-local"},
            {"name": "artifact", "transport": "stdio", "scope": "quest-local"},
            {"name": "bash_exec", "transport": "stdio", "scope": "quest-local"},
        ],
        "slash_commands": build_slash_commands(quest_id),
        "meta": {
            "quest_root": snapshot.get("quest_root"),
            "current_workspace_root": snapshot.get("current_workspace_root"),
            "current_workspace_branch": snapshot.get("current_workspace_branch"),
            "research_head_branch": snapshot.get("research_head_branch"),
            "latest_metric": (snapshot.get("summary") or {}).get("latest_metric"),
            "pending_decisions": snapshot.get("pending_decisions") or [],
            "runtime_status": snapshot.get("runtime_status") or snapshot.get("status"),
            "stop_reason": snapshot.get("stop_reason"),
            "pending_user_message_count": snapshot.get("pending_user_message_count") or 0,
            "default_reply_interaction_id": snapshot.get("default_reply_interaction_id"),
            "waiting_interaction_id": snapshot.get("waiting_interaction_id"),
            "latest_thread_interaction_id": snapshot.get("latest_thread_interaction_id"),
            "last_artifact_interact_at": snapshot.get("last_artifact_interact_at"),
            "last_delivered_batch_id": snapshot.get("last_delivered_batch_id"),
            "updated_at": snapshot.get("updated_at") or utc_now(),
        },
    }


def build_session_update(
    event: dict[str, Any],
    *,
    quest_id: str,
    cursor: int,
    session_id: str | None = None,
) -> dict[str, Any]:
    event_type = str(event.get("type") or event.get("event_type") or "event")
    created_at = (
        event.get("created_at")
        or event.get("recorded_at")
        or event.get("timestamp")
        or utc_now()
    )
    event_id = str(event.get("event_id") or generate_id("evt"))
    update_kind = "event"
    update_payload: dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "quest_id": quest_id,
        "created_at": created_at,
        "cursor": cursor,
    }
    if event_type == "conversation.message":
        update_kind = "message"
        update_payload["message"] = {
            "role": event.get("role"),
            "source": event.get("source"),
            "content": event.get("content"),
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "reply_to_interaction_id": event.get("reply_to_interaction_id"),
            "client_message_id": event.get("client_message_id"),
            "delivery_state": event.get("delivery_state"),
        }
    elif event_type == "artifact.recorded":
        update_kind = "artifact"
        update_payload["artifact"] = {
            "artifact_path": event.get("artifact_path"),
            "artifact_id": event.get("artifact_id"),
            "kind": event.get("kind"),
            "status": event.get("status"),
            "summary": event.get("summary"),
            "reason": event.get("reason"),
            "guidance": event.get("guidance"),
            "guidance_vm": event.get("guidance_vm"),
            "paths": event.get("paths") or {},
            "workspace_root": event.get("workspace_root"),
            "branch": event.get("branch"),
            "head_commit": event.get("head_commit"),
            "flow_type": event.get("flow_type"),
            "protocol_step": event.get("protocol_step"),
            "idea_id": event.get("idea_id"),
            "campaign_id": event.get("campaign_id"),
            "slice_id": event.get("slice_id"),
            "details": event.get("details") or {},
            "checkpoint": event.get("checkpoint"),
            "attachments": event.get("attachments") or [],
            "interaction_id": event.get("interaction_id"),
            "expects_reply": event.get("expects_reply"),
            "reply_mode": event.get("reply_mode"),
            "options": event.get("options") or [],
            "allow_free_text": event.get("allow_free_text"),
            "reply_schema": event.get("reply_schema") or {},
            "reply_to_interaction_id": event.get("reply_to_interaction_id"),
        }
    elif event_type == "runner.delta":
        update_kind = "message"
        update_payload["message"] = {
            "role": "assistant",
            "source": event.get("source") or "runner",
            "content": event.get("text"),
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "stream_id": event.get("stream_id"),
            "message_id": event.get("message_id"),
            "stream": True,
        }
    elif event_type == "runner.agent_message":
        update_kind = "message"
        update_payload["message"] = {
            "role": "assistant",
            "source": event.get("source") or "runner",
            "content": event.get("text"),
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "stream_id": event.get("stream_id"),
            "message_id": event.get("message_id"),
            "stream": False,
        }
    elif event_type == "runner.reasoning":
        update_kind = "message"
        update_payload["message"] = {
            "role": "assistant",
            "source": event.get("source") or "runner",
            "content": event.get("text"),
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "stream_id": event.get("stream_id"),
            "message_id": event.get("message_id"),
            "stream": False,
        }
    elif event_type == "runner.turn_start":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_started",
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
        }
    elif event_type == "runner.turn_finish":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_finished",
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "exit_code": event.get("exit_code"),
            "summary": event.get("summary"),
        }
    elif event_type == "runner.tool_call":
        update_kind = "event"
        update_payload["data"] = {
            "label": "tool_call",
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "tool_name": event.get("tool_name"),
            "tool_call_id": event.get("tool_call_id"),
            "status": event.get("status"),
            "args": event.get("args"),
            "mcp_server": event.get("mcp_server"),
            "mcp_tool": event.get("mcp_tool"),
            "metadata": event.get("metadata"),
            "summary": f"{event.get('tool_name') or 'tool'} started",
        }
    elif event_type == "runner.tool_result":
        update_kind = "event"
        update_payload["data"] = {
            "label": "tool_result",
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "tool_name": event.get("tool_name"),
            "tool_call_id": event.get("tool_call_id"),
            "status": event.get("status"),
            "args": event.get("args"),
            "output": event.get("output"),
            "mcp_server": event.get("mcp_server"),
            "mcp_tool": event.get("mcp_tool"),
            "metadata": event.get("metadata"),
            "summary": f"{event.get('tool_name') or 'tool'} finished",
        }
    elif event_type == "runner.turn_error":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_failed",
            "run_id": event.get("run_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "summary": event.get("summary"),
        }
    elif event_type == "runner.turn_retry_started":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_retry_started",
            "run_id": event.get("run_id"),
            "turn_id": event.get("turn_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "attempt_index": event.get("attempt_index"),
            "max_attempts": event.get("max_attempts"),
            "summary": event.get("summary"),
            "previous_run_id": event.get("previous_run_id"),
        }
    elif event_type == "runner.turn_retry_scheduled":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_retry_scheduled",
            "run_id": event.get("run_id"),
            "turn_id": event.get("turn_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "attempt_index": event.get("attempt_index"),
            "max_attempts": event.get("max_attempts"),
            "next_attempt_index": event.get("next_attempt_index"),
            "backoff_seconds": event.get("backoff_seconds"),
            "summary": event.get("summary"),
            "failure_summary": event.get("failure_summary"),
        }
    elif event_type == "runner.turn_retry_aborted":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_retry_aborted",
            "run_id": event.get("run_id"),
            "turn_id": event.get("turn_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "attempt_index": event.get("attempt_index"),
            "max_attempts": event.get("max_attempts"),
            "summary": event.get("summary"),
            "failure_summary": event.get("failure_summary"),
        }
    elif event_type == "runner.turn_retry_exhausted":
        update_kind = "event"
        update_payload["data"] = {
            "label": "run_retry_exhausted",
            "run_id": event.get("run_id"),
            "turn_id": event.get("turn_id"),
            "skill_id": event.get("skill_id"),
            "model": event.get("model"),
            "attempt_index": event.get("attempt_index"),
            "max_attempts": event.get("max_attempts"),
            "summary": event.get("summary"),
            "failure_summary": event.get("failure_summary"),
        }
    elif event_type == "quest.control":
        update_kind = "event"
        update_payload["data"] = {
            "label": f"quest_{event.get('action') or 'control'}",
            "action": event.get("action"),
            "source": event.get("source"),
            "status": event.get("status"),
            "summary": event.get("summary"),
            "interrupted": event.get("interrupted"),
        }
    else:
        update_payload["data"] = event

    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session_id or f"quest:{quest_id}",
            "update": {
                "kind": update_kind,
                **update_payload,
            },
        },
    }
