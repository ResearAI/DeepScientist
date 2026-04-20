from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ..shared import ensure_dir, ensure_utf8_subprocess_env, generate_id, resolve_runner_binary, write_json
from .base import RunRequest, builtin_mcp_server_names_for_custom_profile, resolve_mcp_tool_profile_for_quest
from .simple_cli import SimpleCliRunner


_CLAUDE_DISALLOWED_TOOLS = "Bash,WebFetch,WebSearch,Task"
_CLAUDE_TOOL_OUTPUT_LIMIT = 16_000
_CLAUDE_EVENT_JSON_LIMIT = 2_000_000
_CLAUDE_OVERSIZED_PREVIEW_LIMIT = 12_000


def _claude_auth_env(env: dict[str, str]) -> dict[str, str]:
    resolved = dict(env)
    auth_token = str(resolved.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    api_key = str(resolved.get("ANTHROPIC_API_KEY") or "").strip()
    if auth_token and not api_key:
        resolved["ANTHROPIC_API_KEY"] = auth_token
    return resolved


def _copy_file_if_exists(source: Path, target: Path) -> None:
    if not source.exists() or not source.is_file():
        return
    ensure_dir(target.parent)
    shutil.copy2(source, target)


def _sync_overlay_tree(target_root: Path, *source_roots: Path) -> None:
    ensure_dir(target_root)
    expected: set[Path] = set()
    for source_root in source_roots:
        if not source_root.exists() or not source_root.is_dir():
            continue
        for source_path in sorted(source_root.rglob("*")):
            relative = source_path.relative_to(source_root)
            expected.add(relative)
            target_path = target_root / relative
            if source_path.is_dir():
                ensure_dir(target_path)
                continue
            ensure_dir(target_path.parent)
            shutil.copy2(source_path, target_path)
    for existing in sorted(target_root.rglob("*"), reverse=True):
        relative = existing.relative_to(target_root)
        if relative in expected:
            continue
        if existing.is_dir():
            shutil.rmtree(existing, ignore_errors=True)
        else:
            existing.unlink(missing_ok=True)


def _truncate_leaf_text(text: str, *, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(int(limit * 0.7), 256)
    tail = max(limit - head - 64, 128)
    omitted = max(len(text) - head - tail, 0)
    return f"{text[:head].rstrip()}\n...[truncated {omitted} chars]...\n{text[-tail:].lstrip()}"


def _encoded_json_size(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8", errors="ignore"))


def _compact_tool_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(payload)
    output_text = str(compacted.get("output") or "")
    if output_text and len(output_text) > _CLAUDE_TOOL_OUTPUT_LIMIT:
        compacted["output_bytes"] = len(output_text.encode("utf-8", errors="ignore"))
        compacted["output"] = _truncate_leaf_text(output_text, limit=min(_CLAUDE_TOOL_OUTPUT_LIMIT, _CLAUDE_OVERSIZED_PREVIEW_LIMIT))
        compacted["output_truncated"] = True
    if _encoded_json_size(compacted) <= _CLAUDE_EVENT_JSON_LIMIT:
        return compacted
    args_text = str(compacted.get("args") or "")
    if args_text and _encoded_json_size(compacted) > _CLAUDE_EVENT_JSON_LIMIT:
        compacted["args"] = _truncate_leaf_text(args_text, limit=4_000)
        compacted["args_truncated"] = True
    if _encoded_json_size(compacted) > _CLAUDE_EVENT_JSON_LIMIT:
        compacted["output"] = str(compacted.get("output") or "")[:2_000]
        compacted["output_truncated"] = True
    return compacted


class ClaudeRunner(SimpleCliRunner):
    runner_name = "claude"

    def _command_uses_stdin_prompt(self) -> bool:
        return True

    def _prepare_runtime(
        self,
        *,
        workspace_root: Path,
        quest_root: Path,
        quest_id: str,
        run_id: str,
        runner_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        target = ensure_dir(workspace_root / ".ds" / "claude-home")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        runner_env = resolved_runner_config.get("env") if isinstance(resolved_runner_config.get("env"), dict) else {}
        cli_auth_env = _claude_auth_env(
            {
                str(key): str(value)
                for key, value in runner_env.items()
                if str(key or "").strip() and value is not None and str(value).strip()
            }
        )
        source_home = Path(str(resolved_runner_config.get("config_dir") or Path.home() / ".claude")).expanduser()
        for filename in (".credentials.json", "settings.json", "settings.local.json"):
            _copy_file_if_exists(source_home / filename, target / filename)
        _sync_overlay_tree(target / "agents", source_home / "agents", quest_root / ".claude" / "agents")
        shared_env = _claude_auth_env(ensure_utf8_subprocess_env({
            "DEEPSCIENTIST_HOME": str(self.home),
            "DEEPSCIENTIST_REPO_ROOT": str(self.repo_root),
            "DS_HOME": str(self.home),
            "DS_QUEST_ID": quest_id,
            "DS_QUEST_ROOT": str(quest_root),
            "DS_WORKTREE_ROOT": str(workspace_root),
            "DS_RUN_ID": run_id,
            "DS_WORKER_ID": run_id,
            "DS_CONVERSATION_ID": f"quest:{quest_id}",
            "DS_AGENT_ROLE": "pi",
            "DS_TEAM_MODE": "single",
        }))
        custom_profile = resolve_mcp_tool_profile_for_quest(quest_root)
        if custom_profile:
            shared_env["DS_CUSTOM_PROFILE"] = custom_profile
        server_names = builtin_mcp_server_names_for_custom_profile(custom_profile)
        project_state = {
            str(workspace_root): {
                "allowedTools": [],
                "mcpContextUris": [],
                "mcpServers": {
                    name: {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": ["-m", "deepscientist.mcp.server", "--namespace", name],
                        "env": shared_env,
                    }
                    for name in server_names
                },
                "enabledMcpjsonServers": [],
                "disabledMcpjsonServers": [],
                "hasTrustDialogAccepted": True,
                "projectOnboardingSeenCount": 0,
                "hasClaudeMdExternalIncludesApproved": False,
                "hasClaudeMdExternalIncludesWarningShown": False,
            }
        }
        claude_state_path = target / ".claude.json"
        existing_state: dict[str, Any] = {}
        if claude_state_path.exists():
            try:
                existing_state = json.loads(claude_state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_state = {}
        merged_state = {
            **existing_state,
            "projects": {
                **(existing_state.get("projects") if isinstance(existing_state.get("projects"), dict) else {}),
                **project_state,
            },
        }
        write_json(claude_state_path, merged_state)
        return {
            "CLAUDE_CONFIG_DIR": str(target),
            **cli_auth_env,
        }, {
            "claude_home": str(target),
        }

    def _build_command(self, request: RunRequest, prompt: str, *, runner_config: dict[str, Any] | None = None) -> list[str]:
        workspace_root = request.worktree_root or request.quest_root
        resolved_binary = resolve_runner_binary(self.binary, runner_name=self.runner_name)
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        permission_mode = str(resolved_runner_config.get("permission_mode") or "bypassPermissions").strip() or "bypassPermissions"
        normalized_model = str(request.model or "").strip()
        command = [
            resolved_binary or self.binary,
            "-p",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--verbose",
            "--add-dir",
            str(workspace_root),
            "--no-session-persistence",
            "--permission-mode",
            permission_mode,
            "--disallowedTools",
            _CLAUDE_DISALLOWED_TOOLS,
        ]
        if normalized_model.lower() not in {"", "inherit", "default", "claude-default"}:
            command.extend(["--model", normalized_model])
        return command

    def _translate_event(
        self,
        payload: dict[str, Any],
        *,
        raw_line: str,
        quest_id: str,
        run_id: str,
        skill_id: str,
        created_at: str,
        translation_state: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        event_type = str(payload.get("type") or "").strip().lower()
        events: list[dict[str, Any]] = []
        texts: list[str] = []
        known_tools = translation_state.setdefault("known_tools", {})
        seen_final_messages = translation_state.setdefault("seen_final_messages", set())

        if event_type == "assistant":
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type") or "").strip().lower()
                if block_type == "text":
                    text = str(block.get("text") or "").strip()
                    if not text:
                        continue
                    texts.append(text)
                    seen_final_messages.add(text)
                    events.append(
                        {
                            "event_id": generate_id("evt"),
                            "type": "runner.agent_message",
                            "quest_id": quest_id,
                            "run_id": run_id,
                            "source": self.runner_name,
                            "skill_id": skill_id,
                            "text": text,
                            "stream_id": str(message.get("id") or run_id),
                            "message_id": str(message.get("id") or run_id),
                            "created_at": created_at,
                        }
                    )
                elif block_type == "thinking":
                    text = str(block.get("thinking") or block.get("text") or "").strip()
                    if not text:
                        continue
                    events.append(
                        {
                            "event_id": generate_id("evt"),
                            "type": "runner.reasoning",
                            "quest_id": quest_id,
                            "run_id": run_id,
                            "source": self.runner_name,
                            "skill_id": skill_id,
                            "text": text,
                            "stream_id": str(message.get("id") or run_id),
                            "message_id": str(message.get("id") or run_id),
                            "kind": "thinking",
                            "created_at": created_at,
                        }
                    )
                elif block_type == "tool_use":
                    tool_name = str(block.get("name") or "tool").strip() or "tool"
                    tool_call_id = str(block.get("id") or generate_id("tool"))
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    event = {
                        "event_id": generate_id("evt"),
                        "type": "runner.tool_call",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": self.runner_name,
                        "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "status": "calling",
                        "args": json.dumps(tool_input, ensure_ascii=False),
                        "created_at": created_at,
                    }
                    if tool_name.startswith("mcp__"):
                        parts = tool_name.split("__", 2)
                        if len(parts) == 3:
                            event["mcp_server"] = parts[1]
                            event["mcp_tool"] = parts[2]
                    known_tools[tool_call_id] = event.copy()
                    events.append(event)
            return events, texts

        if event_type == "user":
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            for block in message.get("content") or []:
                if not isinstance(block, dict) or str(block.get("type") or "").strip().lower() != "tool_result":
                    continue
                tool_call_id = str(block.get("tool_use_id") or generate_id("tool"))
                content = block.get("content")
                if isinstance(content, list):
                    rendered_output = "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
                else:
                    rendered_output = str(content or "")
                prior = known_tools.get(tool_call_id) if isinstance(known_tools, dict) else None
                result_event = _compact_tool_event_payload(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.tool_result",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": self.runner_name,
                    "skill_id": skill_id,
                        "tool_call_id": tool_call_id,
                        "tool_name": str(block.get("name") or (prior or {}).get("tool_name") or "tool").strip() or "tool",
                        "status": "failed" if bool(block.get("is_error")) else "completed",
                        "output": rendered_output,
                        "created_at": created_at,
                    }
                )
                if isinstance(prior, dict):
                    if prior.get("mcp_server"):
                        result_event["mcp_server"] = prior.get("mcp_server")
                    if prior.get("mcp_tool"):
                        result_event["mcp_tool"] = prior.get("mcp_tool")
                if not result_event.get("mcp_server") and not result_event.get("mcp_tool"):
                    tool_name = str(result_event.get("tool_name") or "").strip()
                    if tool_name.startswith("mcp__"):
                        parts = tool_name.split("__", 2)
                        if len(parts) == 3:
                            result_event["mcp_server"] = parts[1]
                            result_event["mcp_tool"] = parts[2]
                events.append(result_event)
            return events, texts

        if event_type == "result":
            text = str(payload.get("result") or payload.get("content") or "").strip()
            if text and text not in seen_final_messages:
                seen_final_messages.add(text)
                texts.append(text)
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.agent_message",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": self.runner_name,
                        "skill_id": skill_id,
                        "text": text,
                        "stream_id": run_id,
                        "message_id": run_id,
                        "created_at": created_at,
                    }
                )
        return events, texts
