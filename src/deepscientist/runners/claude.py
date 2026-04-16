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
from ..claude_cli_compat import materialize_claude_runtime_home
from ..config import ConfigManager
from ..prompts import PromptBuilder
from ..runtime_logs import JsonlLogger
from ..shared import append_jsonl, ensure_dir, generate_id, read_yaml, resolve_runner_binary, utc_now, write_json, write_text
from .base import RunRequest, RunResult
from .codex import _compact_tool_event_payload

_ALLOWED_MCP_TOOLS = "mcp__memory,mcp__artifact,mcp__bash_exec"


def _truncate_leaf_text(text: str, *, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(int(limit * 0.7), 256)
    tail = max(limit - head - 64, 128)
    omitted = max(len(text) - head - tail, 0)
    return f"{text[:head].rstrip()}\n...[truncated {omitted} chars]...\n{text[-tail:].lstrip()}"


def _structured_text(value: object, *, limit: int = 16_000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _truncate_leaf_text(value.strip(), limit=limit)
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        text = str(value)
    return _truncate_leaf_text(text, limit=limit)


def _decode_mcp_tool_name(name: str) -> tuple[str, str]:
    normalized = str(name or "").strip()
    if not normalized.startswith("mcp__"):
        return "", normalized
    parts = normalized.split("__")
    if len(parts) >= 3:
        return parts[1], "__".join(parts[2:])
    if len(parts) == 2:
        return parts[1], ""
    return "", normalized


def _block_text(block: dict[str, Any]) -> str:
    block_type = str(block.get("type") or "").strip().lower()
    if block_type == "text":
        return str(block.get("text") or "").strip()
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    pieces.append(text)
        return "\n".join(pieces).strip()
    return ""


def _tool_result_output(block: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    payload = block.get("content")
    if isinstance(payload, dict):
        return _structured_text(payload), payload
    if isinstance(payload, list):
        texts: list[str] = []
        for item in payload:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("content") or "").strip()
                if text:
                    texts.append(text)
        joined = "\n".join(texts).strip()
        if joined:
            try:
                parsed = json.loads(joined)
            except json.JSONDecodeError:
                return joined, None
            if isinstance(parsed, dict):
                return _structured_text(parsed), parsed
            return joined, None
        return "", None
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return "", None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text, None
        if isinstance(parsed, dict):
            return _structured_text(parsed), parsed
        return text, None
    text = str(block.get("text") or "").strip()
    return text, None


def _tool_result_metadata(
    *,
    quest_id: str,
    run_id: str,
    tool_name: str,
    tool_use_id: str,
    parsed_result: dict[str, Any] | None,
) -> dict[str, Any]:
    server, tool = _decode_mcp_tool_name(tool_name)
    metadata: dict[str, Any] = {
        "quest_id": quest_id,
        "run_id": run_id,
        "session_id": f"quest:{quest_id}",
        "tool_call_id": tool_use_id,
    }
    if server:
        metadata["mcp_server"] = server
    if tool:
        metadata["mcp_tool"] = tool
    if isinstance(parsed_result, dict):
        for key in (
            "bash_id",
            "status",
            "command",
            "cwd",
            "workdir",
            "started_at",
            "finished_at",
            "exit_code",
            "stop_reason",
            "log_path",
        ):
            value = parsed_result.get(key)
            if value not in {None, ""}:
                metadata[key] = value
    return metadata


def _claude_events(
    payload: dict[str, Any],
    *,
    quest_id: str,
    run_id: str,
    skill_id: str,
    known_tool_names: dict[str, str],
    created_at: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    event_type = str(payload.get("type") or "").strip().lower()
    events: list[dict[str, Any]] = []
    output_parts: list[str] = []

    if event_type in {"assistant", "user"}:
        message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
        message_id = str(message.get("id") or payload.get("id") or "").strip() or None
        content = message.get("content") if isinstance(message.get("content"), list) else []
        text_blocks: list[str] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type == "text":
                text = _block_text(block)
                if text:
                    text_blocks.append(text)
                continue
            if block_type == "tool_use" and event_type == "assistant":
                tool_call_id = str(block.get("id") or "").strip() or generate_id("tool")
                tool_name = str(block.get("name") or "").strip() or "tool"
                known_tool_names[tool_call_id] = tool_name
                server, tool = _decode_mcp_tool_name(tool_name)
                args_payload = block.get("input") if isinstance(block.get("input"), dict) else {}
                metadata: dict[str, Any] = {
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "session_id": f"quest:{quest_id}",
                    "tool_call_id": tool_call_id,
                }
                if server:
                    metadata["mcp_server"] = server
                if tool:
                    metadata["mcp_tool"] = tool
                if isinstance(args_payload, dict):
                    for key in ("mode", "id", "workdir", "cwd", "timeout_seconds"):
                        value = args_payload.get(key)
                        if value not in {None, ""}:
                            metadata["bash_id" if key == "id" and server == "bash_exec" and tool == "bash_exec" else key] = value
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.tool_call",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": "claude",
                        "skill_id": skill_id,
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "args": _structured_text(args_payload, limit=8_000),
                        "mcp_server": server or None,
                        "mcp_tool": tool or None,
                        "metadata": metadata,
                        "created_at": created_at,
                    }
                )
                continue
            if block_type == "tool_result":
                tool_use_id = str(block.get("tool_use_id") or "").strip()
                tool_name = known_tool_names.get(tool_use_id, "")
                server, tool = _decode_mcp_tool_name(tool_name)
                output_text, parsed_result = _tool_result_output(block)
                metadata = _tool_result_metadata(
                    quest_id=quest_id,
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    parsed_result=parsed_result,
                )
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.tool_result",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": "claude",
                        "skill_id": skill_id,
                        "tool_name": tool_name or "tool_result",
                        "tool_call_id": tool_use_id or None,
                        "status": "failed" if bool(block.get("is_error")) else "completed",
                        "output": output_text,
                        "mcp_server": server or None,
                        "mcp_tool": tool or None,
                        "metadata": metadata,
                        "created_at": created_at,
                    }
                )

        if text_blocks:
            text = "\n".join(part for part in text_blocks if part.strip()).strip()
            if text:
                output_parts.append(text)
                events.append(
                    {
                        "event_id": generate_id("evt"),
                        "type": "runner.agent_message",
                        "quest_id": quest_id,
                        "run_id": run_id,
                        "source": "claude",
                        "skill_id": skill_id,
                        "text": text,
                        "stream_id": message_id,
                        "message_id": message_id,
                        "created_at": created_at,
                    }
                )
        return [_compact_tool_event_payload(event) for event in events], output_parts

    if event_type == "result":
        text = str(payload.get("result") or payload.get("text") or "").strip()
        if text:
            output_parts.append(text)
        if bool(payload.get("is_error")) and text:
            events.append(
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.agent_message",
                    "quest_id": quest_id,
                    "run_id": run_id,
                    "source": "claude",
                    "skill_id": skill_id,
                    "text": text,
                    "created_at": created_at,
                }
            )
        return [_compact_tool_event_payload(event) for event in events], output_parts

    raw_text = str(payload.get("raw") or "").strip()
    if raw_text:
        output_parts.append(raw_text)
    return events, output_parts


class ClaudeRunner:
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

    def run(self, request: RunRequest) -> RunResult:
        workspace_root = request.worktree_root or request.quest_root
        run_root = ensure_dir(request.quest_root / ".ds" / "runs" / request.run_id)
        history_root = ensure_dir(request.quest_root / ".ds" / "claude_history" / request.run_id)
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
        write_text(run_root / "prompt.md", prompt)

        claude_home = self._prepare_project_claude_home(
            workspace_root,
            runner_config=runner_config,
        )
        mcp_config_path = self._write_mcp_config(
            run_root / "claude-mcp.json",
            quest_root=request.quest_root,
            workspace_root=workspace_root,
            quest_id=request.quest_id,
            run_id=request.run_id,
        )
        command = self._build_command(
            request,
            prompt,
            mcp_config_path=mcp_config_path,
            runner_config=runner_config,
        )
        write_json(
            run_root / "command.json",
            {
                "command": command,
                "claude_home": str(claude_home),
                "mcp_config": str(mcp_config_path),
                "quest_root": str(request.quest_root),
                "workspace_root": str(workspace_root),
                "cwd": str(workspace_root),
                "turn_reason": request.turn_reason,
                "turn_intent": request.turn_intent,
                "turn_mode": request.turn_mode,
            },
        )

        env = dict(os.environ)
        runner_env = runner_config.get("env") if isinstance(runner_config.get("env"), dict) else {}
        for key, value in runner_env.items():
            env_key = str(key or "").strip()
            if not env_key or value is None:
                continue
            env_value = str(value)
            if env_value == "":
                continue
            env[env_key] = env_value
        env["HOME"] = str(claude_home)
        env["USERPROFILE"] = str(claude_home)
        env["DEEPSCIENTIST_HOME"] = str(self.home)
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
        popen_kwargs: dict[str, Any] = {
            "cwd": str(workspace_root),
            "env": env,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **popen_kwargs)
        with self._process_lock:
            self._active_processes[request.quest_id] = process
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        try:
            process.stdin.write(prompt)
            if not prompt.endswith("\n"):
                process.stdin.write("\n")
            process.stdin.close()

            output_parts: list[str] = []
            final_output_parts: list[str] = []
            known_tool_names: dict[str, str] = {}
            history_events = history_root / "events.jsonl"
            stdout_events = run_root / "stdout.jsonl"
            quest_events = request.quest_root / ".ds" / "events.jsonl"

            append_jsonl(
                quest_events,
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_start",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "claude",
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "created_at": utc_now(),
                },
            )

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
                events, message_output_parts = _claude_events(
                    payload,
                    quest_id=request.quest_id,
                    run_id=request.run_id,
                    skill_id=request.skill_id,
                    known_tool_names=known_tool_names,
                    created_at=timestamp,
                )
                for event in events:
                    append_jsonl(quest_events, event)
                    if event.get("type") == "runner.agent_message":
                        text = event.get("text")
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
            append_jsonl(
                quest_events,
                {
                    "event_id": generate_id("evt"),
                    "type": "runner.turn_finish",
                    "quest_id": request.quest_id,
                    "run_id": request.run_id,
                    "source": "claude",
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
                "output_text": output_text,
                "stderr_text": stderr_text,
                "completed_at": utc_now(),
            }
            write_json(run_root / "result.json", result_payload)
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
                current = self._active_processes.get(request.quest_id)
                if current is process:
                    self._active_processes.pop(request.quest_id, None)

    def interrupt(self, quest_id: str) -> bool:
        with self._process_lock:
            process = self._active_processes.get(quest_id)
        if process is None:
            return False

        interrupted = True
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except (ValueError, OSError):
                try:
                    process.terminate()
                except OSError:
                    return False
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                try:
                    process.terminate()
                except OSError:
                    return False
        try:
            process.wait(timeout=5)
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

    def _build_command(
        self,
        request: RunRequest,
        prompt: str,
        *,
        mcp_config_path: Path,
        runner_config: dict[str, Any] | None = None,
    ) -> list[str]:
        resolved_binary = resolve_runner_binary(self.binary, runner_name="claude")
        command = [
            resolved_binary or self.binary,
            "-p",
            "--input-format",
            "text",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--allowedTools",
            _ALLOWED_MCP_TOOLS,
            "--mcp-config",
            str(mcp_config_path),
            "--strict-mcp-config",
        ]
        normalized_model = str(request.model or "").strip().lower()
        if normalized_model not in {"", "inherit", "default", "claude-default"}:
            command.extend(["--model", str(request.model).strip()])
        return command

    def _prepare_project_claude_home(
        self,
        workspace_root: Path,
        *,
        runner_config: dict[str, Any] | None = None,
    ) -> Path:
        target = ensure_dir(workspace_root / ".ds" / "claude-home")
        resolved_runner_config = runner_config if isinstance(runner_config, dict) else self._load_runner_config()
        configured_home = str(resolved_runner_config.get("config_dir") or str(Path.home() / ".claude"))
        materialize_claude_runtime_home(
            source_home=configured_home,
            target_home=target,
        )
        return target

    def _write_mcp_config(
        self,
        path: Path,
        *,
        quest_root: Path,
        workspace_root: Path,
        quest_id: str,
        run_id: str,
    ) -> Path:
        pythonpath = os.environ.get("PYTHONPATH", "")
        shared_env = {
            "DEEPSCIENTIST_HOME": str(self.home),
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
        }
        if pythonpath:
            shared_env["PYTHONPATH"] = pythonpath
        mcp_servers = {}
        for name in ("memory", "artifact", "bash_exec"):
            mcp_servers[name] = {
                "command": sys.executable,
                "args": ["-m", "deepscientist.mcp.server", "--namespace", name],
                "env": shared_env,
            }
        write_json(path, {"mcpServers": mcp_servers})
        return path

    def _load_runner_config(self) -> dict[str, Any]:
        try:
            config = ConfigManager(self.home).load_runners_config()
        except OSError:
            return {}
        raw = config.get("claude", {})
        return raw if isinstance(raw, dict) else {}
