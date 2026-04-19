from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..shared import ensure_dir, ensure_utf8_subprocess_env, generate_id, resolve_runner_binary, write_json
from .base import RunRequest, builtin_mcp_server_names_for_custom_profile, resolve_mcp_tool_profile_for_quest
from .simple_cli import SimpleCliRunner


_OPENCODE_MCP_SERVERS = ("bash_exec", "artifact", "memory")


def _normalize_opencode_tool_name(raw_name: str) -> tuple[str, str | None, str | None]:
    normalized = str(raw_name or "").strip() or "tool"
    if normalized.startswith("mcp__"):
        parts = normalized.split("__", 2)
        if len(parts) == 3:
            return normalized, parts[1], parts[2]
        return normalized, None, None
    for server in _OPENCODE_MCP_SERVERS:
        prefix = f"{server}_"
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            tool = normalized[len(prefix):]
            return f"mcp__{server}__{tool}", server, tool
    return normalized, None, None


def _copy_opencode_tree(target_root: Path, *source_roots: Path) -> None:
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


class OpenCodeRunner(SimpleCliRunner):
    runner_name = "opencode"

    def _prepare_runtime(
        self,
        *,
        workspace_root: Path,
        quest_root: Path,
        quest_id: str,
        run_id: str,
        runner_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        runtime_home = ensure_dir(workspace_root / ".ds" / "opencode-home")
        config_home = ensure_dir(runtime_home / ".config" / "opencode")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        source_root = Path(str(resolved_runner_config.get("config_dir") or Path.home() / ".config" / "opencode")).expanduser()
        source_config_path = source_root / "opencode.json"
        target_config_path = config_home / "opencode.json"
        source_config: dict[str, Any] = {}
        if source_config_path.exists():
            try:
                source_config = json.loads(source_config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                source_config = {}
        _copy_opencode_tree(config_home / "skills", source_root / "skills", quest_root / ".opencode" / "skills")
        permission_mode = str(resolved_runner_config.get("permission_mode") or "allow").strip().lower() or "allow"
        shared_env = ensure_utf8_subprocess_env({
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
        })
        custom_profile = resolve_mcp_tool_profile_for_quest(quest_root)
        if custom_profile:
            shared_env["DS_CUSTOM_PROFILE"] = custom_profile
        server_names = builtin_mcp_server_names_for_custom_profile(custom_profile)
        merged_config = {
            **source_config,
            "mcp": {
                **(source_config.get("mcp") if isinstance(source_config.get("mcp"), dict) else {}),
                **{
                    name: {
                        "type": "local",
                        "enabled": True,
                        "command": [
                            "python",
                            "-m",
                            "deepscientist.mcp.server",
                            "--namespace",
                            name,
                        ],
                        "environment": shared_env,
                    }
                    for name in server_names
                },
            },
            "permission": permission_mode if permission_mode in {"allow", "ask", "deny"} else "allow",
        }
        write_json(target_config_path, merged_config)
        return {
            "HOME": str(runtime_home),
            "XDG_CONFIG_HOME": str(runtime_home / ".config"),
        }, {
            "opencode_home": str(runtime_home),
            "opencode_config": str(target_config_path),
        }

    def _build_command(self, request: RunRequest, prompt: str, *, runner_config: dict[str, Any] | None = None) -> list[str]:
        workspace_root = request.worktree_root or request.quest_root
        resolved_binary = resolve_runner_binary(self.binary, runner_name=self.runner_name)
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        normalized_model = str(request.model or "").strip()
        command = [
            resolved_binary or self.binary,
            "run",
            "--format",
            "json",
            "--pure",
            "--dir",
            str(workspace_root),
        ]
        if normalized_model.lower() not in {"", "inherit", "default", "opencode-default"}:
            command.extend(["--model", normalized_model])
        agent_name = str(resolved_runner_config.get("default_agent") or "").strip()
        if agent_name:
            command.extend(["--agent", agent_name])
        variant = str(resolved_runner_config.get("variant") or "").strip()
        if variant:
            command.extend(["--variant", variant])
        command.append(prompt)
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
        part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
        record = part if isinstance(part, dict) and part else payload
        session_id = str(record.get("sessionID") or payload.get("sessionID") or run_id)
        message_id = str(record.get("messageID") or record.get("id") or payload.get("id") or session_id or run_id)

        def emit_message(text: str) -> None:
            normalized = str(text or "").strip()
            if not normalized:
                return
            texts.append(normalized)
            events.append(
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.agent_message",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "source": self.runner_name,
                    "skill_id": skill_id,
                    "text": normalized,
                    "stream_id": session_id,
                    "message_id": message_id,
                    "created_at": created_at,
                }
            )

        if event_type in {"assistant", "message", "text", "result"}:
            message = record.get("message") if isinstance(record.get("message"), dict) else payload.get("message") if isinstance(payload.get("message"), dict) else {}
            content = message.get("content") if message else record.get("content") or payload.get("content")
            if isinstance(content, str):
                emit_message(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        emit_message(str(item.get("text") or item.get("content") or ""))
            elif isinstance(record.get("text"), str):
                emit_message(str(record.get("text") or ""))
            elif isinstance(payload.get("text"), str):
                emit_message(str(payload.get("text") or ""))
            return events, texts

        if event_type in {"tool_use", "tool_call"}:
            raw_tool_name = str(record.get("tool") or record.get("name") or payload.get("tool") or payload.get("name") or "tool").strip() or "tool"
            tool_name, mcp_server, mcp_tool = _normalize_opencode_tool_name(raw_tool_name)
            tool_call_id = str(record.get("callID") or record.get("toolCallID") or payload.get("toolCallID") or record.get("tool_call_id") or payload.get("tool_call_id") or record.get("id") or payload.get("id") or generate_id("tool"))
            state = record.get("state") if isinstance(record.get("state"), dict) else {}
            args = state.get("input") if isinstance(state.get("input"), dict) else record.get("input") if isinstance(record.get("input"), dict) else payload.get("input") if isinstance(payload.get("input"), dict) else payload.get("args")
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
                "args": json.dumps(args or {}, ensure_ascii=False),
                "created_at": created_at,
            }
            if mcp_server:
                event["mcp_server"] = mcp_server
            if mcp_tool:
                event["mcp_tool"] = mcp_tool
            known_tools[tool_call_id] = event.copy()
            events.append(event)

            output = state.get("output") if isinstance(state, dict) else None
            state_status = str(state.get("status") or "").strip().lower()
            has_result = output is not None or bool(state_status) or bool(record.get("error")) or bool(payload.get("error"))
            if has_result:
                rendered_output = output if isinstance(output, str) else json.dumps(output or state or record or payload, ensure_ascii=False)
                result_event = {
                    "event_id": generate_id("evt"),
                    "type": "runner.tool_result",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "source": self.runner_name,
                    "skill_id": skill_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": "failed" if state_status.startswith("fail") or bool(record.get("error")) or bool(payload.get("error")) else "completed",
                    "args": json.dumps(args or {}, ensure_ascii=False),
                    "output": rendered_output,
                    "created_at": created_at,
                }
                if mcp_server:
                    result_event["mcp_server"] = mcp_server
                if mcp_tool:
                    result_event["mcp_tool"] = mcp_tool
                events.append(result_event)
            return events, texts

        if event_type in {"tool_result", "tool_output"}:
            tool_call_id = str(record.get("callID") or record.get("toolCallID") or payload.get("toolCallID") or record.get("tool_call_id") or payload.get("tool_call_id") or record.get("id") or payload.get("id") or generate_id("tool"))
            prior = known_tools.get(tool_call_id) if isinstance(known_tools, dict) else None
            raw_tool_name = str(record.get("tool") or record.get("name") or payload.get("tool") or payload.get("name") or (prior or {}).get("tool_name") or "tool").strip() or "tool"
            tool_name, mcp_server, mcp_tool = _normalize_opencode_tool_name(raw_tool_name)
            output = record.get("output") if record.get("output") is not None else payload.get("output")
            if not isinstance(output, str):
                output = json.dumps(output or record or payload, ensure_ascii=False)
            event = {
                "event_id": generate_id("evt"),
                "type": "runner.tool_result",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": self.runner_name,
                "skill_id": skill_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "failed" if event_type == "tool_output" and payload.get("error") else "completed",
                "output": output,
                "created_at": created_at,
            }
            if isinstance(prior, dict):
                if prior.get("mcp_server"):
                    event["mcp_server"] = prior.get("mcp_server")
                if prior.get("mcp_tool"):
                    event["mcp_tool"] = prior.get("mcp_tool")
            if mcp_server:
                event["mcp_server"] = mcp_server
            if mcp_tool:
                event["mcp_tool"] = mcp_tool
            events.append(event)
            return events, texts

        if event_type in {"thinking", "reasoning"}:
            content = str(record.get("text") or record.get("content") or payload.get("text") or payload.get("content") or "").strip()
            if content:
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.reasoning",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": self.runner_name,
                        "skill_id": skill_id,
                        "text": content,
                        "stream_id": session_id,
                        "message_id": message_id,
                        "kind": event_type,
                        "created_at": created_at,
                    }
                )
            return events, texts

        return events, texts
