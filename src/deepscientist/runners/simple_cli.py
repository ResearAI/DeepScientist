from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Any

from ..artifact import ArtifactService
from ..gitops import export_git_graph
from ..process_control import process_session_popen_kwargs
from ..prompts import PromptBuilder
from ..runtime_logs import JsonlLogger
from ..shared import append_jsonl, ensure_dir, ensure_utf8_subprocess_env, generate_id, read_yaml, utc_now, write_json, write_text
from .base import RunRequest, RunResult


class SimpleCliRunner:
    runner_name = "runner"

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
        history_root = ensure_dir(request.quest_root / ".ds" / f"{self.runner_name}_history" / request.run_id)
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
            runner_name=self.runner_name,
        )
        write_text(run_root / "prompt.md", prompt)

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

        runtime_env, runtime_meta = self._prepare_runtime(
            workspace_root=workspace_root,
            quest_root=request.quest_root,
            quest_id=request.quest_id,
            run_id=request.run_id,
            runner_config=runner_config,
        )
        env.update(runtime_env)
        env = ensure_utf8_subprocess_env(env)

        command = self._build_command(request, prompt, runner_config=runner_config)
        write_json(
            run_root / "command.json",
            {
                "command": command,
                "quest_root": str(request.quest_root),
                "workspace_root": str(workspace_root),
                "cwd": str(workspace_root),
                "turn_reason": request.turn_reason,
                "turn_intent": request.turn_intent,
                "turn_mode": request.turn_mode,
                **runtime_meta,
            },
        )

        popen_kwargs = self._subprocess_popen_kwargs(workspace_root=workspace_root, env=env)
        process = subprocess.Popen(command, **popen_kwargs)
        with self._process_lock:
            self._active_processes[request.quest_id] = process
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        try:
            if self._command_uses_stdin_prompt():
                process.stdin.write(prompt)
            process.stdin.close()

            output_parts: list[str] = []
            translation_state: dict[str, Any] = {}
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
                    "source": self.runner_name,
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "created_at": utc_now(),
                },
            )

            for raw_line in process.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                timestamp = utc_now()
                append_jsonl(stdout_events, {"timestamp": timestamp, "line": line})
                try:
                    payload = json.loads(line)
                    append_jsonl(history_events, {"timestamp": timestamp, "event": payload})
                except json.JSONDecodeError:
                    payload = {"raw": line}
                    append_jsonl(history_events, {"timestamp": timestamp, "event": payload})
                try:
                    self.artifact_service.quest_service.schedule_projection_refresh(
                        request.quest_root,
                        kinds=("details",),
                    )
                except Exception:
                    pass
                translated_events, text_parts = self._translate_event(
                    payload,
                    raw_line=line,
                    quest_id=request.quest_id,
                    run_id=request.run_id,
                    skill_id=request.skill_id,
                    created_at=timestamp,
                    translation_state=translation_state,
                )
                for event in translated_events:
                    append_jsonl(quest_events, event)
                output_parts.extend(part.strip() for part in text_parts if isinstance(part, str) and part.strip())

            stderr_text = process.stderr.read()
            exit_code = process.wait()
            output_text = next((part for part in reversed(output_parts) if part), "")
            self._emit_setup_tool_schema_warning_if_needed(
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
                    "source": self.runner_name,
                    "skill_id": request.skill_id,
                    "model": request.model,
                    "exit_code": exit_code,
                    "stderr_text": stderr_text[:2000],
                    "summary": output_text[:1000],
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
                f"runner.{self.runner_name}.completed",
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
                    "summary": output_text[:1000],
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

    def _command_uses_stdin_prompt(self) -> bool:
        return False

    def _prepare_runtime(
        self,
        *,
        workspace_root: Path,
        quest_root: Path,
        quest_id: str,
        run_id: str,
        runner_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return {}, {}

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
        return [], []

    def _load_runner_config(self) -> dict[str, Any]:
        from ..config import ConfigManager

        try:
            runners_cfg = ConfigManager(self.home).load_runners_config()
        except OSError:
            return {}
        config = runners_cfg.get(self.runner_name)
        return config if isinstance(config, dict) else {}

    def _build_command(self, request: RunRequest, prompt: str, *, runner_config: dict[str, Any] | None = None) -> list[str]:
        raise NotImplementedError

    def _emit_setup_tool_schema_warning_if_needed(
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
        lowered = str(output_text or "").lower()
        suspicious_markers = (
            "form_patch 参数",
            "没有暴露要求的 `form_patch` 参数",
            "没有暴露要求的 form_patch 参数",
            "form_patch not exposed",
            "form_patch unavailable",
            "tool did not expose form_patch",
        )
        if not any(marker.lower() in lowered for marker in suspicious_markers):
            return
        append_jsonl(
            quest_events,
            {
                "event_id": generate_id("evt"),
                "type": "runner.turn_postprocess_warning",
                "quest_id": request.quest_id,
                "run_id": request.run_id,
                "source": self.runner_name,
                "skill_id": request.skill_id,
                "summary": (
                    "The runner output claimed that `prepare_start_setup_form` did not expose the required "
                    "`form_patch` argument, but the active start-setup MCP profile does define `form_patch` "
                    "as a required top-level field. This suggests a runner/model-side tool-schema misunderstanding."
                ),
                "details": {
                    "warning_code": "start_setup_false_missing_form_patch_claim",
                    "tool_name": "prepare_start_setup_form",
                    "required_argument": "form_patch",
                    "runner_name": self.runner_name,
                },
                "created_at": utc_now(),
            },
        )
