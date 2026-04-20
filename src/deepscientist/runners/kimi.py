from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ..kimi_cli_compat import materialize_kimi_runtime_home
from ..shared import ensure_dir, ensure_utf8_subprocess_env, generate_id, resolve_runner_binary, write_json
from .base import RunRequest, builtin_mcp_server_names_for_custom_profile, resolve_mcp_tool_profile_for_quest
from .simple_cli import SimpleCliRunner


def _sync_kimi_tree(target_root: Path, *source_roots: Path) -> None:
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


def _decode_kimi_tool_name(raw_name: str) -> tuple[str, str | None, str | None]:
    normalized = str(raw_name or "").strip() or "tool"
    if normalized.startswith("mcp__"):
        parts = normalized.split("__", 2)
        if len(parts) == 3:
            return normalized, parts[1], parts[2]
    return normalized, None, None


def _normalize_text_content(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type in {"text", "output_text", ""}:
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        text = str(value.get("text") or value.get("content") or "").strip()
        if text:
            return text
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value).strip()
    return str(value or "").strip()


class KimiRunner(SimpleCliRunner):
    runner_name = "kimi"

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
        runtime_home = ensure_dir(self.home / "runtime" / "runners" / "kimi" / quest_id / run_id)
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        source_home = Path(str(resolved_runner_config.get("config_dir") or Path.home() / ".kimi")).expanduser()
        kimi_home = materialize_kimi_runtime_home(source_home=source_home, target_home=runtime_home)
        _sync_kimi_tree(kimi_home / "skills", source_home / "skills", quest_root / ".kimi" / "skills")

        shared_env = ensure_utf8_subprocess_env(
            {
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
            }
        )
        custom_profile = resolve_mcp_tool_profile_for_quest(quest_root)
        if custom_profile:
            shared_env["DS_CUSTOM_PROFILE"] = custom_profile
        server_names = builtin_mcp_server_names_for_custom_profile(custom_profile)
        mcp_config = {
            "mcpServers": {
                name: {
                    "command": sys.executable,
                    "args": ["-m", "deepscientist.mcp.server", "--namespace", name],
                    "env": shared_env,
                }
                for name in server_names
            }
        }
        mcp_config_path = kimi_home / "mcp.json"
        write_json(mcp_config_path, mcp_config)
        return {
            "HOME": str(runtime_home),
            "USERPROFILE": str(runtime_home),
        }, {
            "kimi_runtime_home": str(runtime_home),
            "kimi_home": str(kimi_home),
            "kimi_mcp_config": str(mcp_config_path),
        }

    def _build_command(self, request: RunRequest, prompt: str, *, runner_config: dict[str, Any] | None = None) -> list[str]:
        workspace_root = request.worktree_root or request.quest_root
        resolved_binary = resolve_runner_binary(self.binary, runner_name=self.runner_name)
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        runtime_home = self.home / "runtime" / "runners" / "kimi" / request.quest_id / request.run_id
        mcp_config_path = runtime_home / ".kimi" / "mcp.json"
        command = [
            resolved_binary or self.binary,
            "--print",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--work-dir",
            str(workspace_root),
            "--mcp-config-file",
            str(mcp_config_path),
        ]
        if bool(resolved_runner_config.get("yolo", True)):
            command.append("--yolo")
        normalized_model = str(request.model or "").strip()
        if normalized_model.lower() not in {"", "inherit", "default", "kimi-default"}:
            command.extend(["--model", normalized_model])
        agent_name = str(resolved_runner_config.get("agent") or "").strip()
        if agent_name:
            command.extend(["--agent", agent_name])
        if bool(resolved_runner_config.get("thinking", False)):
            command.append("--thinking")
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
        events: list[dict[str, Any]] = []
        texts: list[str] = []
        role = str(payload.get("role") or "").strip().lower()
        known_tools = translation_state.setdefault("known_tools", {})

        if role == "assistant":
            content = payload.get("content")
            content_items = content if isinstance(content, list) else [content]
            for item in content_items:
                if isinstance(item, dict) and str(item.get("type") or "").strip().lower() in {"think", "thinking"}:
                    reasoning = str(item.get("thinking") or item.get("text") or item.get("content") or "").strip()
                    if not reasoning:
                        continue
                    events.append(
                        {
                            "event_id": generate_id("evt"),
                            "type": "runner.reasoning",
                            "quest_id": quest_id,
                            "run_id": run_id,
                            "source": self.runner_name,
                            "skill_id": skill_id,
                            "text": reasoning,
                            "stream_id": str(payload.get("id") or run_id),
                            "message_id": str(payload.get("id") or run_id),
                            "kind": "thinking",
                            "created_at": created_at,
                        }
                    )
            rendered_text = _normalize_text_content(content)
            if rendered_text:
                texts.append(rendered_text)
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.agent_message",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": self.runner_name,
                        "skill_id": skill_id,
                        "text": rendered_text,
                        "stream_id": str(payload.get("id") or run_id),
                        "message_id": str(payload.get("id") or run_id),
                        "created_at": created_at,
                    }
                )
            for tool_call in payload.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                tool_name, mcp_server, mcp_tool = _decode_kimi_tool_name(
                    str(function.get("name") or tool_call.get("name") or "tool")
                )
                tool_call_id = str(tool_call.get("id") or generate_id("tool"))
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    rendered_args = arguments
                else:
                    rendered_args = json.dumps(arguments or {}, ensure_ascii=False)
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
                    "args": rendered_args,
                    "created_at": created_at,
                }
                if mcp_server:
                    event["mcp_server"] = mcp_server
                if mcp_tool:
                    event["mcp_tool"] = mcp_tool
                known_tools[tool_call_id] = event.copy()
                events.append(event)
            return events, texts

        if role == "tool":
            tool_call_id = str(
                payload.get("tool_call_id")
                or payload.get("toolCallID")
                or payload.get("tool_use_id")
                or generate_id("tool")
            )
            prior = known_tools.get(tool_call_id) if isinstance(known_tools, dict) else None
            tool_name, mcp_server, mcp_tool = _decode_kimi_tool_name(
                str(payload.get("name") or (prior or {}).get("tool_name") or "tool")
            )
            output = _normalize_text_content(payload.get("content"))
            status = "failed" if bool(payload.get("is_error")) or output.startswith("<system>ERROR:") else "completed"
            event = {
                "event_id": generate_id("evt"),
                "type": "runner.tool_result",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": self.runner_name,
                "skill_id": skill_id,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": status,
                "args": str((prior or {}).get("args") or ""),
                "output": output,
                "created_at": created_at,
            }
            if mcp_server or (prior or {}).get("mcp_server"):
                event["mcp_server"] = mcp_server or (prior or {}).get("mcp_server")
            if mcp_tool or (prior or {}).get("mcp_tool"):
                event["mcp_tool"] = mcp_tool or (prior or {}).get("mcp_tool")
            return [event], []

        return [], []
