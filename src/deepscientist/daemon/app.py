from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from ..artifact import ArtifactService
from ..bash_exec import BashExecService
from ..bash_exec.runtime import TerminalClient
from ..bridges import register_builtin_connector_bridges
from ..bridges.connectors import QQConnectorBridge
from ..channels import QQRelayChannel, get_channel_factory, list_channel_names, register_builtin_channels
from ..channels.discord_gateway import DiscordGatewayService
from ..channels.feishu_long_connection import FeishuLongConnectionService
from ..channels.qq_gateway import QQGatewayService
from ..channels.slack_socket import SlackSocketModeService
from ..channels.telegram_polling import TelegramPollingService
from ..channels.whatsapp_local_session import WhatsAppLocalSessionService
from ..cloud import CloudLinkService
from ..connector_profiles import PROFILEABLE_CONNECTOR_NAMES, connector_profile_label, list_connector_profiles, merge_connector_profile_config
from ..connector_runtime import conversation_identity_key, format_conversation_id, normalize_conversation_id, parse_conversation_id
from ..config import ConfigManager
from ..home import repo_root
from ..memory import MemoryService
from ..latex_runtime import QuestLatexService
from ..prompts import PromptBuilder
from ..prompts.builder import STANDARD_SKILLS
from ..qq_profiles import list_qq_profiles, merge_qq_profile_config
from ..quest import QuestService
from ..runners import CodexRunner, RunRequest, get_runner_factory, register_builtin_runners
from ..runtime_logs import JsonlLogger
from ..shared import append_jsonl, ensure_dir, generate_id, read_json, read_jsonl, read_text, resolve_within, run_command, slugify, utc_now, which, write_json
from ..skills import SkillInstaller
from ..team import SingleTeamService
from .api import ApiHandlers, match_route
from .sessions import SessionStore
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request as WebSocketRequest
from websockets.http11 import Response
from websockets.sync.server import Server as WebSocketServer
from websockets.sync.server import ServerConnection, serve as websocket_serve

TERMINAL_STREAM_IDLE_SLEEP_SECONDS = 0.02


class DaemonApp:
    _MAX_INBOUND_ATTACHMENT_BYTES = 25 * 1024 * 1024

    def __init__(self, home: Path) -> None:
        self.home = home.resolve()
        self.daemon_id = str(os.environ.get("DS_DAEMON_ID") or "").strip() or generate_id("daemon")
        self.daemon_managed_by = str(os.environ.get("DS_DAEMON_MANAGED_BY") or "manual").strip() or "manual"
        self.repo_root = repo_root()
        self.config_manager = ConfigManager(home)
        self.runners_config = self.config_manager.load_named("runners")
        self.connectors_config = self.config_manager.load_named_normalized("connectors")
        self.skill_installer = SkillInstaller(self.repo_root, home)
        self.quest_service = QuestService(home, skill_installer=self.skill_installer)
        self.latex_service = QuestLatexService(self.quest_service)
        self.memory_service = MemoryService(home)
        self.artifact_service = ArtifactService(home)
        self.bash_exec_service = BashExecService(home)
        self.team_service = SingleTeamService(home)
        self.cloud_service = CloudLinkService(home)
        config = self.config_manager.load_named("config")
        self.logger = JsonlLogger(home / "logs", level=config.get("logging", {}).get("level", "info"))
        self.reconciled_quests = self.quest_service.reconcile_runtime_state()
        for item in self.reconciled_quests:
            self.logger.log(
                "warning",
                "quest.runtime_reconciled",
                quest_id=item.get("quest_id"),
                previous_status=item.get("previous_status"),
                abandoned_run_id=item.get("abandoned_run_id"),
                status=item.get("status"),
            )
        self.prompt_builder = PromptBuilder(self.repo_root, home)
        self.codex_runner = CodexRunner(
            home=home,
            repo_root=self.repo_root,
            binary=self.runners_config.get("codex", {}).get("binary", "codex"),
            logger=self.logger,
            prompt_builder=self.prompt_builder,
            artifact_service=self.artifact_service,
        )
        register_builtin_runners(codex_runner=self.codex_runner)
        register_builtin_connector_bridges()
        register_builtin_channels(home=home, connectors_config=self.connectors_config)
        self.runners = {
            "codex": self._create_runner("codex"),
        }
        self.channels = {name: self._create_channel(name) for name in list_channel_names()}
        self.sessions = SessionStore()
        self._turn_lock = threading.Lock()
        self._turn_state: dict[str, dict[str, object]] = {}
        self._server: ThreadingHTTPServer | None = None
        self._terminal_attach_server: WebSocketServer | None = None
        self._terminal_attach_thread: threading.Thread | None = None
        self._terminal_attach_host: str | None = None
        self._terminal_attach_port: int | None = None
        self._serve_host: str | None = None
        self._serve_port: int | None = None
        self._shutdown_requested = threading.Event()
        self._qq_gateways: dict[str, QQGatewayService] = {}
        self._telegram_polling: dict[str, TelegramPollingService] = {}
        self._slack_socket: dict[str, SlackSocketModeService] = {}
        self._discord_gateway: dict[str, DiscordGatewayService] = {}
        self._feishu_long_connection: dict[str, FeishuLongConnectionService] = {}
        self._whatsapp_local_session: dict[str, WhatsAppLocalSessionService] = {}
        self.handlers = ApiHandlers(self)

    def list_connector_statuses(self) -> list[dict[str, object]]:
        title_by_quest = self._quest_titles_by_id()
        items = [self._augment_connector_status(channel.status(), title_by_quest=title_by_quest) for channel in self.channels.values()]
        lingzhu_config = self.connectors_config.get("lingzhu")
        if isinstance(lingzhu_config, dict):
            items.append(self._augment_connector_status(self.config_manager.lingzhu_snapshot(lingzhu_config), title_by_quest=title_by_quest))
        return items

    def _quest_titles_by_id(self) -> dict[str, str | None]:
        return {
            str(item.get("quest_id") or "").strip(): str(item.get("title") or "").strip() or None
            for item in self.quest_service.list_quests()
        }

    def _augment_connector_status(
        self,
        snapshot: dict[str, object],
        *,
        title_by_quest: dict[str, str | None] | None = None,
    ) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            return snapshot
        connector_name = str(snapshot.get("name") or "").strip().lower()
        titles = title_by_quest or self._quest_titles_by_id()
        binding_map: dict[str, dict[str, str | None]] = {}
        for raw in snapshot.get("bindings") or []:
            if not isinstance(raw, dict):
                continue
            conversation_id = str(raw.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            quest_id = str(raw.get("quest_id") or "").strip() or None
            binding_map[conversation_identity_key(conversation_id)] = {
                "quest_id": quest_id,
                "quest_title": titles.get(quest_id or ""),
            }

        def augment_target(target: object) -> dict[str, object] | None:
            if not isinstance(target, dict):
                return None
            payload = dict(target)
            conversation_id = str(payload.get("conversation_id") or "").strip()
            if not conversation_id:
                return payload
            binding = binding_map.get(conversation_identity_key(conversation_id)) or {}
            bound_quest_id = str(binding.get("quest_id") or "").strip() or None
            bound_quest_title = str(binding.get("quest_title") or "").strip() or None
            if bound_quest_id:
                payload["bound_quest_id"] = bound_quest_id
                payload["bound_quest_title"] = bound_quest_title
                payload["is_bound"] = True
                payload["warning"] = f"Currently bound to {bound_quest_id}"
            else:
                payload["bound_quest_id"] = None
                payload["bound_quest_title"] = None
                payload["is_bound"] = False
            payload["selectable"] = True
            if not payload.get("connector") and connector_name:
                payload["connector"] = connector_name
            return payload

        known_targets = [item for item in (augment_target(target) for target in snapshot.get("known_targets") or []) if item is not None]
        discovered_targets = [item for item in (augment_target(target) for target in snapshot.get("discovered_targets") or []) if item is not None]
        bindings = []
        for raw in snapshot.get("bindings") or []:
            if not isinstance(raw, dict):
                continue
            payload = dict(raw)
            quest_id = str(payload.get("quest_id") or "").strip() or None
            payload["quest_title"] = titles.get(quest_id or "")
            bindings.append(payload)
        payload = dict(snapshot)
        if known_targets:
            payload["known_targets"] = known_targets
        if discovered_targets:
            payload["discovered_targets"] = discovered_targets
            payload["target_count"] = len(discovered_targets)
        default_target = augment_target(snapshot.get("default_target"))
        if default_target is not None:
            payload["default_target"] = default_target
        if bindings:
            payload["bindings"] = bindings
        profiles_payload = []
        for raw_profile in snapshot.get("profiles") or []:
            if not isinstance(raw_profile, dict):
                continue
            profile_payload = dict(raw_profile)
            profile_payload["discovered_targets"] = [
                item
                for item in (
                    augment_target(target)
                    for target in raw_profile.get("discovered_targets") or []
                )
                if item is not None
            ]
            profile_payload["recent_conversations"] = [
                dict(item)
                for item in raw_profile.get("recent_conversations") or []
                if isinstance(item, dict)
            ]
            profile_payload["bindings"] = [
                {
                    **dict(item),
                    "quest_title": titles.get(str(item.get("quest_id") or "").strip() or ""),
                }
                for item in raw_profile.get("bindings") or []
                if isinstance(item, dict)
            ]
            profiles_payload.append(profile_payload)
        if profiles_payload:
            payload["profiles"] = profiles_payload
        return payload

    @staticmethod
    def _connector_has_delivery_target(snapshot: dict[str, object]) -> bool:
        if str(snapshot.get("main_chat_id") or "").strip():
            return True
        if str(snapshot.get("last_conversation_id") or "").strip():
            return True
        if isinstance(snapshot.get("default_target"), dict) and snapshot.get("default_target"):
            return True
        if isinstance(snapshot.get("bindings"), list) and snapshot.get("bindings"):
            return True
        if isinstance(snapshot.get("recent_conversations"), list) and snapshot.get("recent_conversations"):
            return True
        if isinstance(snapshot.get("discovered_targets"), list) and snapshot.get("discovered_targets"):
            return True
        for key in ("binding_count", "target_count"):
            try:
                if int(snapshot.get(key) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def connector_availability_summary(self) -> dict[str, object]:
        available_connectors: list[dict[str, object]] = []
        preferred_connector_name: str | None = None
        preferred_conversation_id: str | None = None
        has_enabled_external_connector = False
        has_bound_external_connector = False

        for item in self.list_connector_statuses():
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name == "local":
                continue
            enabled = bool(item.get("enabled"))
            connection_state = str(item.get("connection_state") or "").strip() or None
            has_target = self._connector_has_delivery_target(item)
            if enabled:
                has_enabled_external_connector = True
            if enabled and has_target:
                has_bound_external_connector = True
                if preferred_connector_name is None:
                    preferred_connector_name = name
                    preferred_conversation_id = str(
                        ((item.get("default_target") or {}) if isinstance(item.get("default_target"), dict) else {}).get(
                            "conversation_id"
                        )
                        or item.get("last_conversation_id")
                        or ""
                    ).strip() or None
            available_connectors.append(
                {
                    "name": name,
                    "enabled": enabled,
                    "connection_state": connection_state,
                    "binding_count": int(item.get("binding_count") or 0),
                    "target_count": int(item.get("target_count") or 0),
                    "has_delivery_target": has_target,
                }
            )

        return {
            "has_enabled_external_connector": has_enabled_external_connector,
            "has_bound_external_connector": has_bound_external_connector,
            "should_recommend_binding": not has_bound_external_connector,
            "preferred_connector_name": preferred_connector_name,
            "preferred_conversation_id": preferred_conversation_id,
            "available_connectors": available_connectors,
        }

    def _normalize_requested_connector_bindings(
        self,
        requested_connector_bindings: list[dict[str, object]] | None,
    ) -> list[dict[str, str | None]]:
        items = requested_connector_bindings if isinstance(requested_connector_bindings, list) else []
        normalized_by_connector: dict[str, dict[str, str | None]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            raw_connector_name = str(raw.get("connector") or "").strip().lower()
            conversation_id = normalize_conversation_id(raw.get("conversation_id"))
            parsed = parse_conversation_id(conversation_id)
            connector_name = raw_connector_name
            if parsed is not None:
                connector_name = str(parsed.get("connector") or connector_name).strip().lower()
            if not connector_name or connector_name == "local":
                continue
            if connector_name not in self.channels:
                continue
            if parsed is not None and str(parsed.get("connector") or "").strip().lower() != connector_name:
                continue
            normalized_by_connector[connector_name] = {
                "connector": connector_name,
                "conversation_id": conversation_id or None,
            }
        return list(normalized_by_connector.values())

    def _launcher_update_base_command(self) -> list[str]:
        node_binary = str(os.environ.get("DEEPSCIENTIST_NODE_BINARY") or "").strip() or which("node") or which("nodejs")
        launcher_path = str(os.environ.get("DEEPSCIENTIST_LAUNCHER_PATH") or "").strip()
        if not launcher_path:
            launcher_path = str(self.repo_root / "bin" / "ds.js")
        if not node_binary:
            raise RuntimeError("Node.js is not available on PATH, so DeepScientist cannot check npm updates.")
        if not Path(launcher_path).exists():
            raise RuntimeError(f"DeepScientist launcher path does not exist: {launcher_path}")
        return [node_binary, launcher_path, "update", "--home", str(self.home)]

    def system_update_status(self) -> dict[str, object]:
        command = [*self._launcher_update_base_command(), "--check", "--json"]
        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("DeepScientist update check timed out.") from exc
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Update check failed.").strip())
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("DeepScientist update check returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("DeepScientist update check returned an invalid payload.")
        return payload

    def request_system_update(self, *, action: str) -> dict[str, object]:
        normalized = str(action or "").strip().lower()
        if normalized not in {"install_latest", "remind_later", "skip_version"}:
            raise ValueError(f"Unsupported update action `{action}`.")
        command = self._launcher_update_base_command()
        if normalized == "install_latest":
            host = self._serve_host or "0.0.0.0"
            port = self._serve_port or 20999
            command.extend(
                [
                    "--yes",
                    "--background",
                    "--restart-daemon",
                    "--host",
                    str(host),
                    "--port",
                    str(port),
                    "--json",
                ]
            )
        elif normalized == "remind_later":
            command.extend(["--remind-later", "--json"])
        else:
            command.extend(["--skip-version", "--json"])

        try:
            result = subprocess.run(
                command,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("DeepScientist update request timed out.") from exc
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Update request failed.").strip())
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("DeepScientist update request returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("DeepScientist update request returned an invalid payload.")
        return payload

    def _process_terminal_attach_request(
        self,
        connection: ServerConnection,
        request: WebSocketRequest,
    ) -> Response | None:
        query = parse_qs(urlparse(request.path).query)
        token = str((query.get("token") or [""])[0] or "").strip()
        if not token:
            return Response(
                400,
                "Bad Request",
                Headers({"Content-Type": "text/plain; charset=utf-8"}),
                b"Missing terminal attach token.",
            )
        attach_token, runtime = self.bash_exec_service.resolve_terminal_attach_token(token)
        if attach_token is None:
            return Response(
                404,
                "Not Found",
                Headers({"Content-Type": "text/plain; charset=utf-8"}),
                b"Terminal attach token is invalid or expired.",
            )
        if runtime is None:
            return Response(
                409,
                "Conflict",
                Headers({"Content-Type": "text/plain; charset=utf-8"}),
                b"Terminal runtime is no longer active.",
            )
        setattr(connection, "_ds_terminal_attach_token", token)
        return None

    def _handle_terminal_attach_connection(self, connection: ServerConnection) -> None:
        token_value = str(getattr(connection, "_ds_terminal_attach_token", "") or "").strip()
        attach_token, runtime = self.bash_exec_service.consume_terminal_attach_token(token_value)
        if attach_token is None or runtime is None:
            try:
                connection.close(code=1011, reason="terminal_attach_unavailable")
            except Exception:
                pass
            return

        send_lock = threading.Lock()
        client = TerminalClient(
            client_id=generate_id("tclient"),
            send_text=connection.send,
            send_binary=connection.send,
            close=connection.close,
            send_lock=send_lock,
        )
        runtime.attach_client(client)
        try:
            session = self.bash_exec_service.get_session(attach_token.quest_root, attach_token.bash_id)
            with send_lock:
                connection.send(
                    json.dumps(
                        {
                            "type": "ready",
                            "bash_id": attach_token.bash_id,
                            "status": session.get("status"),
                            "cwd": session.get("cwd"),
                            "workdir": session.get("workdir"),
                        },
                        ensure_ascii=False,
                    )
                )
                for chunk in runtime.snapshot_replay():
                    if chunk:
                        connection.send(chunk)
            while True:
                try:
                    message = connection.recv()
                except ConnectionClosed:
                    break
                if message is None:
                    break
                if isinstance(message, bytes):
                    runtime.write_binary_input(message)
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                message_type = str(payload.get("type") or "").strip().lower()
                if message_type == "input":
                    self.bash_exec_service.append_terminal_input(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        data=str(payload.get("data") or ""),
                        source="web-pty",
                    )
                    continue
                if message_type == "binary_input":
                    raw = str(payload.get("data") or "")
                    if raw:
                        runtime.write_binary_input(base64.b64decode(raw))
                    continue
                if message_type == "resize":
                    cols = int(payload.get("cols") or 0)
                    rows = int(payload.get("rows") or 0)
                    self.bash_exec_service.resize_terminal_session(
                        attach_token.quest_root,
                        attach_token.bash_id,
                        cols=cols,
                        rows=rows,
                    )
                    continue
                if message_type == "detach":
                    break
                if message_type == "ping":
                    with send_lock:
                        connection.send(json.dumps({"type": "pong"}, ensure_ascii=False))
        except Exception as exc:
            try:
                with send_lock:
                    connection.send(
                        json.dumps(
                            {"type": "error", "message": str(exc)},
                            ensure_ascii=False,
                        )
                    )
            except Exception:
                pass
        finally:
            runtime.detach_client(client.client_id)
            try:
                connection.close()
            except Exception:
                pass

    def _start_terminal_attach_server(self, host: str, port: int) -> None:
        if self._terminal_attach_server is not None:
            return
        candidates: list[int] = []
        if port > 0 and port < 65535:
            candidates.append(port + 1)
        candidates.append(0)
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                server = websocket_serve(
                    self._handle_terminal_attach_connection,
                    host=host,
                    port=candidate,
                    process_request=self._process_terminal_attach_request,
                    compression=None,
                    max_size=None,
                    max_queue=None,
                )
                self._terminal_attach_server = server
                self._terminal_attach_host = host
                self._terminal_attach_port = int(server.socket.getsockname()[1])
                thread = threading.Thread(
                    target=server.serve_forever,
                    daemon=True,
                    name="deepscientist-terminal-attach",
                )
                thread.start()
                self._terminal_attach_thread = thread
                return
            except OSError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error

    def _stop_terminal_attach_server(self) -> None:
        server = self._terminal_attach_server
        thread = self._terminal_attach_thread
        self._terminal_attach_server = None
        self._terminal_attach_thread = None
        self._terminal_attach_host = None
        self._terminal_attach_port = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def get_runner(self, name: str):
        normalized = str(name or "").strip().lower()
        try:
            return self.runners[normalized]
        except KeyError as exc:
            available = ", ".join(sorted(self.runners)) or "none"
            raise KeyError(f"Unknown runner `{normalized}`. Available runners: {available}.") from exc

    def _create_runner(self, name: str):
        factory = get_runner_factory(name)
        return factory(home=self.home, app=self, config=self.runners_config.get(name, {}))

    def _create_channel(self, name: str):
        factory = get_channel_factory(name)
        return factory(home=self.home, app=self, config=self.connectors_config.get(name, {}))

    def reload_connectors_config(self, *, restart_background: bool = True) -> dict[str, object]:
        self.connectors_config = self.config_manager.load_named_normalized("connectors")
        register_builtin_channels(home=self.home, connectors_config=self.connectors_config)
        for name, channel in self.channels.items():
            config = self.connectors_config.get(name, {})
            if hasattr(channel, "config") and isinstance(getattr(channel, "config"), dict):
                channel.config.clear()
                if isinstance(config, dict):
                    channel.config.update(config)
        if restart_background and self._server is not None:
            self._stop_background_connectors()
            self._start_background_connectors()
        return {
            "ok": True,
            "connectors": sorted(
                name for name, config in self.connectors_config.items() if not str(name).startswith("_") and isinstance(config, dict)
            ),
        }

    def _preferred_locale(self) -> str:
        config = self.config_manager.load_named("config")
        return str(config.get("default_locale") or "zh-CN").lower()

    def _polite_copy(self, *, zh: str, en: str) -> str:
        return zh if self._preferred_locale().startswith("zh") else en

    def submit_user_message(
        self,
        quest_id: str,
        *,
        text: str,
        source: str,
        attachments: list[dict[str, object]] | None = None,
        reply_to_interaction_id: str | None = None,
        client_message_id: str | None = None,
    ) -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        previous_status = str(previous_snapshot.get("runtime_status") or previous_snapshot.get("status") or "").strip()
        message = self.quest_service.append_message(
            quest_id,
            role="user",
            content=text,
            source=source,
            attachments=[dict(item) for item in (attachments or []) if isinstance(item, dict)],
            reply_to_interaction_id=reply_to_interaction_id,
            client_message_id=client_message_id,
        )
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        auto_resumed = previous_status in {"stopped", "paused", "completed"} and runtime_status not in {"stopped", "paused", "completed"}
        if auto_resumed:
            self._append_control_event(
                quest_id,
                action="resume",
                source=f"auto:{source}",
                status=runtime_status or "active",
                interrupted=False,
                summary=f"Quest {quest_id} automatically resumed after a new user message.",
                automated=True,
            )
        with self._turn_lock:
            turn_state = dict(self._turn_state.get(quest_id) or {})
        has_live_turn = bool(turn_state.get("running")) or bool(snapshot.get("active_run_id"))
        if runtime_status == "running" and has_live_turn:
            scheduled = {
                "scheduled": True,
                "started": False,
                "queued": True,
                "reason": "queued_for_artifact_interact",
            }
        else:
            scheduled = self.schedule_turn(quest_id, reason="user_message")
        return {
            "message": message,
            "auto_resumed": auto_resumed,
            "previous_status": previous_status or None,
            **scheduled,
        }

    def create_quest(
        self,
        *,
        goal: str,
        title: str | None = None,
        quest_id: str | None = None,
        source: str = "local",
        announce_connector_binding: bool = True,
        exclude_conversation_id: str | None = None,
        preferred_connector_conversation_id: str | None = None,
        requested_connector_bindings: list[dict[str, object]] | None = None,
        force_connector_rebind: bool = False,
        requested_baseline_ref: dict[str, object] | None = None,
        startup_contract: dict[str, object] | None = None,
    ) -> dict:
        normalized_requested_bindings = self._normalize_requested_connector_bindings(requested_connector_bindings)
        snapshot = self.quest_service.create(
            goal=goal,
            title=title,
            quest_id=quest_id,
            requested_baseline_ref=dict(requested_baseline_ref) if isinstance(requested_baseline_ref, dict) else None,
            startup_contract=dict(startup_contract) if isinstance(startup_contract, dict) else None,
        )
        baseline_id = (
            str((requested_baseline_ref or {}).get("baseline_id") or "").strip()
            if isinstance(requested_baseline_ref, dict)
            else ""
        )
        variant_id = (
            str((requested_baseline_ref or {}).get("variant_id") or "").strip() or None
            if isinstance(requested_baseline_ref, dict)
            else None
        )
        if baseline_id:
            try:
                quest_root = Path(snapshot["quest_root"])
                attachment = self.artifact_service.attach_baseline(quest_root, baseline_id, variant_id)
                if not attachment.get("ok"):
                    raise RuntimeError(
                        str(attachment.get("message") or f"Unable to materialize requested baseline `{baseline_id}`.")
                    )
                self.artifact_service.confirm_baseline(
                    quest_root,
                    baseline_path=f"baselines/imported/{baseline_id}",
                    baseline_id=baseline_id,
                    variant_id=variant_id,
                    summary=f"Baseline `{baseline_id}` confirmed during quest creation.",
                )
                snapshot = self.quest_service.snapshot(snapshot["quest_id"])
            except Exception as exc:
                shutil.rmtree(Path(snapshot["quest_root"]), ignore_errors=True)
                self.logger.log(
                    "warning",
                    "quest.baseline_bootstrap_failed",
                    quest_id=snapshot.get("quest_id"),
                    baseline_id=baseline_id,
                    message=str(exc),
                )
                raise RuntimeError(
                    f"Quest creation failed because the requested baseline `{baseline_id}` could not be attached and confirmed: {exc}"
                ) from exc
        preferred_binding = normalize_conversation_id(preferred_connector_conversation_id)
        preferred_parsed = parse_conversation_id(preferred_binding)
        if normalized_requested_bindings:
            try:
                binding_result = self.update_quest_bindings(
                    snapshot["quest_id"],
                    normalized_requested_bindings,
                    force=force_connector_rebind,
                )
                if isinstance(binding_result, tuple):
                    raise RuntimeError(str(binding_result[1].get("message") or "Unable to bind connector targets."))
                if announce_connector_binding:
                    for result in binding_result.get("results") or []:
                        if not isinstance(result, dict):
                            continue
                        conversation_id = str(result.get("conversation_id") or "").strip()
                        connector_name = str(result.get("connector") or "").strip().lower()
                        if not conversation_id or not connector_name or connector_name == "local":
                            continue
                        channel = self._channel_with_bindings(connector_name)
                        channel.send(
                            {
                                "conversation_id": conversation_id,
                                "quest_id": snapshot["quest_id"],
                                "kind": "ack",
                                "message": self._quest_created_connector_message(
                                    connector_name,
                                    quest_id=snapshot["quest_id"],
                                    goal=goal,
                                    previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                                ),
                            }
                        )
                snapshot = self.quest_service.snapshot(snapshot["quest_id"])
            except Exception as exc:
                shutil.rmtree(Path(snapshot["quest_root"]), ignore_errors=True)
                self.sessions.forget(snapshot["quest_id"])
                self.logger.log(
                    "warning",
                    "quest.connector_binding_failed",
                    quest_id=snapshot.get("quest_id"),
                    message=str(exc),
                )
                raise RuntimeError(
                    f"Quest creation failed because one or more selected connector targets could not be bound: {exc}"
                ) from exc
        elif (
            preferred_binding
            and preferred_parsed
            and str(preferred_parsed.get("connector") or "").strip().lower() in self.channels
            and str(preferred_parsed.get("connector") or "").strip().lower() != "local"
        ):
            connector_name = str(preferred_parsed.get("connector") or "").strip().lower()
            result = self.update_quest_binding(snapshot["quest_id"], preferred_binding, force=True)
            if isinstance(result, tuple):
                self.logger.log(
                    "warning",
                    "quest.preferred_connector_binding_failed",
                    quest_id=snapshot.get("quest_id"),
                    conversation_id=preferred_binding,
                    status=result[0],
                    message=str(result[1].get("message") or "Unable to bind preferred connector target."),
                )
            elif announce_connector_binding:
                channel = self._channel_with_bindings(connector_name)
                channel.send(
                    {
                        "conversation_id": preferred_binding,
                        "quest_id": snapshot["quest_id"],
                        "kind": "ack",
                        "message": self._quest_created_connector_message(
                            connector_name,
                            quest_id=snapshot["quest_id"],
                            goal=goal,
                            previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                        ),
                    }
                )
        else:
            self._auto_bind_connectors_to_latest_quest(
                snapshot["quest_id"],
                goal=goal,
                source=source,
                announce=announce_connector_binding,
                exclude_conversation_id=exclude_conversation_id,
            )
        return snapshot

    def schedule_turn(self, quest_id: str, *, reason: str = "user_message") -> dict:
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["pending"] = True
            state["stop_requested"] = False
            state["reason"] = reason
            if state.get("running"):
                return {
                    "scheduled": True,
                    "started": False,
                    "queued": True,
                    "reason": reason,
                }
            state["running"] = True
            worker = threading.Thread(
                target=self._drain_turns,
                args=(quest_id,),
                daemon=True,
                name=f"deepscientist-turn-{quest_id}",
            )
            state["worker"] = worker
        worker.start()
        return {
            "scheduled": True,
            "started": True,
            "queued": False,
            "reason": reason,
        }

    def control_quest(self, quest_id: str, *, action: str, source: str = "local") -> dict:
        normalized_action = str(action or "").strip().lower()
        if normalized_action == "pause":
            return self.pause_quest(quest_id, source=source)
        if normalized_action == "stop":
            return self.stop_quest(quest_id, source=source)
        if normalized_action == "resume":
            return self.resume_quest(quest_id, source=source)
        raise ValueError(f"Unsupported quest control action `{action}`.")

    def pause_quest(self, quest_id: str, *, source: str = "local") -> dict:
        return self._interrupt_quest(quest_id, action="pause", status="paused", source=source)

    def stop_quest(self, quest_id: str, *, source: str = "local") -> dict:
        return self._interrupt_quest(quest_id, action="stop", status="stopped", source=source)

    def _interrupt_quest(self, quest_id: str, *, action: str, status: str, source: str) -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        runner_name = self._runner_name_for(previous_snapshot)
        interrupted = False
        stopped_bash_session_ids: list[str] = []
        cancelled_pending = {
            "batch_id": None,
            "cancelled_count": 0,
            "cancelled": [],
        }
        try:
            runner = self.get_runner(runner_name)
        except KeyError:
            runner = None
        if runner is not None and hasattr(runner, "interrupt"):
            interrupted = bool(getattr(runner, "interrupt")(quest_id))
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["pending"] = False
            state["stop_requested"] = True
        stopped_bash_session_ids = self._stop_active_bash_exec_sessions(
            quest_id,
            run_id=str(previous_snapshot.get("active_run_id") or "").strip() or None,
            reason=f"quest_{action}",
            user_id=source,
        )
        if action == "stop":
            cancel_reason = "cancelled_by_daemon_shutdown" if source == "local-admin" else "cancelled_by_stop"
            cancelled_pending = self.quest_service.cancel_pending_user_messages(
                quest_id,
                reason=cancel_reason,
                action=action,
                source=source,
            )
        stop_reason = "daemon_shutdown" if action == "stop" and source == "local-admin" else f"user_{action}"
        snapshot = self.quest_service.mark_turn_finished(quest_id, status=status, stop_reason=stop_reason)
        verb = "paused" if action == "pause" else "stopped"
        summary = f"Quest {quest_id} {verb}."
        if interrupted:
            summary = f"Quest {quest_id} {verb} and the active runner was interrupted."
        if stopped_bash_session_ids:
            summary = f"{summary} Stopped {len(stopped_bash_session_ids)} bash_exec session(s)."
        cancelled_count = int(cancelled_pending.get("cancelled_count") or 0)
        if cancelled_count > 0:
            summary = f"{summary} Cancelled {cancelled_count} queued user message(s)."
        event = self._append_control_event(
            quest_id,
            action=action,
            source=source,
            status=str(snapshot.get("status") or status),
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_count,
            summary=summary,
        )
        notice = self._announce_control_state(
            quest_id,
            action=action,
            source=source,
            snapshot=snapshot,
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_count,
            previous_snapshot=previous_snapshot,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "action": action,
            "interrupted": interrupted,
            "cancelled_pending_user_message_count": cancelled_count,
            "stopped_bash_session_ids": stopped_bash_session_ids,
            "snapshot": snapshot,
            "message": summary,
            "event": event,
            "notice": notice,
        }

    def _stop_active_bash_exec_sessions(
        self,
        quest_id: str,
        *,
        run_id: str | None,
        reason: str,
        user_id: str,
    ) -> list[str]:
        quest_root = self.quest_service._quest_root(quest_id)
        try:
            sessions = self.bash_exec_service.list_sessions(quest_root, limit=500)
        except Exception:
            return []

        stopped: list[str] = []
        for session in sessions:
            bash_id = str(session.get("bash_id") or "").strip()
            if not bash_id:
                continue
            kind = str(session.get("kind") or "exec").strip().lower()
            status = str(session.get("status") or "").strip().lower()
            if kind == "terminal" or status in {"completed", "failed", "terminated"}:
                continue
            session_run_id = str(session.get("agent_instance_id") or session.get("task_id") or "").strip()
            if run_id and session_run_id and session_run_id != run_id:
                continue
            try:
                self.bash_exec_service.request_stop(
                    quest_root,
                    bash_id,
                    reason=reason,
                    user_id=user_id,
                )
            except Exception:
                continue
            stopped.append(bash_id)
        return stopped

    def resume_quest(self, quest_id: str, *, source: str = "local") -> dict:
        previous_snapshot = self.quest_service.snapshot(quest_id)
        with self._turn_lock:
            state = self._turn_state.setdefault(quest_id, {"running": False, "pending": False})
            state["stop_requested"] = False
        snapshot = self.quest_service.snapshot(quest_id)
        next_status = "running" if snapshot.get("status") == "running" else "active"
        snapshot = self.quest_service.set_status(quest_id, next_status)
        summary = f"Quest {quest_id} resumed."
        event = self._append_control_event(
            quest_id,
            action="resume",
            source=source,
            status=str(snapshot.get("status") or next_status),
            interrupted=False,
            summary=summary,
        )
        notice = self._announce_control_state(
            quest_id,
            action="resume",
            source=source,
            snapshot=snapshot,
            interrupted=False,
            cancelled_pending_user_message_count=0,
            previous_snapshot=previous_snapshot,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "action": "resume",
            "interrupted": False,
            "snapshot": snapshot,
            "message": summary,
            "event": event,
            "notice": notice,
        }

    def _append_control_event(
        self,
        quest_id: str,
        *,
        action: str,
        source: str,
        status: str,
        interrupted: bool,
        summary: str,
        cancelled_pending_user_message_count: int = 0,
        automated: bool = False,
    ) -> dict:
        payload = {
            "event_id": generate_id("evt"),
            "type": "quest.control",
            "quest_id": quest_id,
            "action": action,
            "source": source,
            "status": status,
            "interrupted": interrupted,
            "cancelled_pending_user_message_count": max(0, int(cancelled_pending_user_message_count or 0)),
            "summary": summary,
            "automated": automated,
            "created_at": utc_now(),
        }
        append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", payload)
        return payload

    def _announce_control_state(
        self,
        quest_id: str,
        *,
        action: str,
        source: str,
        snapshot: dict,
        interrupted: bool,
        cancelled_pending_user_message_count: int,
        previous_snapshot: dict | None = None,
    ) -> dict:
        quest_root = self.quest_service._quest_root(quest_id)
        message = self._control_notice_message(
            quest_id,
            action=action,
            snapshot=snapshot,
            interrupted=interrupted,
            cancelled_pending_user_message_count=cancelled_pending_user_message_count,
            previous_snapshot=previous_snapshot,
        )
        history_record = self.quest_service.append_message(
            quest_id,
            role="assistant",
            content=message,
            source="system-control",
        )
        connectors = self.artifact_service._connectors_config()
        targets = self.artifact_service._select_delivery_targets(
            self.artifact_service._bound_conversations(quest_root),
            connectors=connectors,
        )
        attachments = [
            {
                "kind": "quest_control",
                "action": action,
                "status": snapshot.get("status"),
                "source": source,
                "branch": snapshot.get("branch"),
                "workspace_root": snapshot.get("current_workspace_root") or snapshot.get("quest_root"),
                "interrupted": interrupted,
                "cancelled_pending_user_message_count": int(cancelled_pending_user_message_count or 0),
                "previous_status": (
                    (previous_snapshot or {}).get("runtime_status")
                    or (previous_snapshot or {}).get("status")
                ),
                "stop_reason": snapshot.get("stop_reason"),
            }
        ]
        delivery_targets: list[str] = []
        importance = "warning" if action in {"pause", "stop"} else "info"
        for target in targets:
            channel_name = self.artifact_service._normalize_channel_name(target)
            payload = {
                "quest_root": str(quest_root),
                "quest_id": quest_id,
                "conversation_id": target,
                "kind": "progress",
                "message": message,
                "response_phase": "control",
                "importance": importance,
                "attachments": attachments,
            }
            if self.artifact_service._send_to_channel(channel_name, payload, connectors=connectors):
                delivery_targets.append(target)
        return {
            "message": message,
            "history_record": history_record,
            "delivery_targets": delivery_targets,
        }

    def _control_notice_message(
        self,
        quest_id: str,
        *,
        action: str,
        snapshot: dict,
        interrupted: bool,
        cancelled_pending_user_message_count: int,
        previous_snapshot: dict | None = None,
    ) -> str:
        branch = str(snapshot.get("branch") or "unknown").strip() or "unknown"
        workspace_root = str(snapshot.get("current_workspace_root") or snapshot.get("quest_root") or "").strip()
        if action == "resume":
            lines = [
                self._polite_copy(
                    zh="DeepScientist 已恢复运行。",
                    en="DeepScientist has resumed.",
                ),
                self._polite_copy(
                    zh="当前 Git 分支与 worktree 已保留，系统会沿用现有研究上下文继续。",
                    en="The current Git branch and worktree were kept intact, and the quest will continue from the existing research context.",
                ),
            ]
        elif action == "pause":
            lines = [
                self._polite_copy(
                    zh="DeepScientist 已从运行状态转为暂停状态。",
                    en="DeepScientist has moved from running to paused.",
                ),
                self._polite_copy(
                    zh="当前 Git 分支与 worktree 已保留。如需继续，请直接在当前聊天或 connector 中发送任意新指令，或使用 /resume；系统会沿用当前 quest 上下文继续。",
                    en="The current Git branch and worktree were kept intact. To continue, send any new instruction in this chat or connector, or use /resume; the quest will resume from the current context.",
                ),
            ]
        else:
            lines = [
                self._polite_copy(
                    zh="DeepScientist 已从运行状态转为停止状态。",
                    en="DeepScientist has moved from running to stopped.",
                ),
                self._polite_copy(
                    zh="当前 Git 分支与 worktree 已保留。如需继续，请直接在当前聊天或 connector 中发送任意新指令，或使用 /resume；系统会沿用当前 quest 上下文继续。",
                    en="The current Git branch and worktree were kept intact. To continue, send any new instruction in this chat or connector, or use /resume; the quest will resume from the current context.",
                ),
            ]
        if interrupted:
            lines.append(
                self._polite_copy(
                    zh="当前活跃 runner 已被中断。",
                    en="The active runner was interrupted.",
                )
            )
        cancelled_count = max(0, int(cancelled_pending_user_message_count or 0))
        if cancelled_count > 0:
            lines.append(
                self._polite_copy(
                    zh=f"已取消 {cancelled_count} 条排队中的用户消息。",
                    en=f"Cancelled {cancelled_count} queued user message(s).",
                )
            )
        previous_status = str(
            (previous_snapshot or {}).get("runtime_status")
            or (previous_snapshot or {}).get("status")
            or ""
        ).strip()
        if previous_status and action == "resume":
            lines.append(
                self._polite_copy(
                    zh=f"此前状态：`{previous_status}`。",
                    en=f"Previous status: `{previous_status}`.",
                )
            )
        lines.extend(
            [
                f"- Quest: `{quest_id}`",
                f"- Branch: `{branch}`",
                f"- Workspace: `{workspace_root or snapshot.get('quest_root')}`",
            ]
        )
        return "\n".join(lines)

    def _drain_turns(self, quest_id: str) -> None:
        while True:
            with self._turn_lock:
                state = self._turn_state.setdefault(quest_id, {"running": True, "pending": False})
                if not state.get("pending"):
                    state["running"] = False
                    state.pop("worker", None)
                    return
                state["pending"] = False
            self._run_quest_turn(quest_id)

    def _run_quest_turn(self, quest_id: str) -> None:
        with self._turn_lock:
            state = dict(self._turn_state.get(quest_id) or {})
        turn_reason = str(state.get("reason") or "user_message").strip() or "user_message"
        if state.get("stop_requested"):
            return
        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        if runtime_status in {"stopped", "paused", "completed", "error"} and not snapshot.get("active_run_id"):
            return
        latest_user_message = self._latest_user_message(quest_id)
        if turn_reason != "auto_continue" and latest_user_message is None:
            return

        runner_name = self._runner_name_for(snapshot)
        runner_cfg = self.runners_config.get(runner_name, {})
        skill_id = self._turn_skill_for(snapshot, latest_user_message, turn_reason=turn_reason)
        run_id = generate_id("run")
        model = str(runner_cfg.get("model", "gpt-5.4"))
        run_message = ""
        claimed_message_id: str | None = None
        if turn_reason != "auto_continue":
            run_message = str((latest_user_message or {}).get("content") or "").strip()
            claimed_message_id = str((latest_user_message or {}).get("id") or "").strip() or None
            if not run_message:
                return

        if runner_cfg.get("enabled") is False:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=f"Runner `{runner_name}` is disabled in `runners.yaml`.",
            )
            return

        try:
            runner = self.get_runner(runner_name)
        except KeyError as exc:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=str(exc),
            )
            return

        binary_issue = self._runner_binary_issue(runner_name, runner)
        if binary_issue is not None:
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=run_id,
                skill_id=skill_id,
                model=model,
                summary=binary_issue,
            )
            return

        raw_reasoning_effort = runner_cfg.get("model_reasoning_effort") if isinstance(runner_cfg, dict) else None
        reasoning_effort = (
            str(raw_reasoning_effort).strip()
            if raw_reasoning_effort is not None and str(raw_reasoning_effort).strip()
            else ("xhigh" if raw_reasoning_effort is None else None)
        )
        with self._turn_lock:
            if bool((self._turn_state.get(quest_id) or {}).get("stop_requested")):
                return
        if claimed_message_id:
            self.quest_service.claim_pending_user_message_for_turn(
                quest_id,
                message_id=claimed_message_id,
                run_id=run_id,
            )
        retry_policy = self._runner_retry_policy(runner_cfg if isinstance(runner_cfg, dict) else {})
        max_attempts = int(retry_policy.get("max_attempts") or 1)
        turn_id = generate_id("turn")
        retry_context: dict[str, Any] | None = None
        quest_root = Path(snapshot["quest_root"])
        worktree_root = Path(str(snapshot["current_workspace_root"])) if snapshot.get("current_workspace_root") else None

        for attempt_index in range(1, max_attempts + 1):
            current_run_id = run_id if attempt_index == 1 else generate_id("run")
            if attempt_index > 1:
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_started",
                    runner_name=runner_name,
                    run_id=current_run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary=f"Retry attempt {attempt_index}/{max_attempts} started.",
                    previous_run_id=str((retry_context or {}).get("previous_run_id") or "") or None,
                )

            request = RunRequest(
                quest_id=quest_id,
                quest_root=quest_root,
                worktree_root=worktree_root,
                run_id=current_run_id,
                skill_id=skill_id,
                message=run_message,
                model=model,
                approval_policy=str(runner_cfg.get("approval_policy", "on-request")),
                sandbox_mode=str(runner_cfg.get("sandbox_mode", "workspace-write")),
                turn_reason=turn_reason,
                reasoning_effort=reasoning_effort,
                turn_id=turn_id,
                attempt_index=attempt_index,
                max_attempts=max_attempts,
                retry_context=retry_context,
            )
            self.quest_service.mark_turn_started(quest_id, run_id=current_run_id, status="running")
            if attempt_index > 1:
                self.quest_service.update_runtime_state(
                    quest_root=quest_root,
                    display_status="retrying",
                    retry_state={
                        "turn_id": turn_id,
                        "attempt_index": attempt_index,
                        "max_attempts": max_attempts,
                        "last_run_id": str((retry_context or {}).get("previous_run_id") or "") or None,
                        "last_error": str((retry_context or {}).get("failure_summary") or "") or None,
                        "next_retry_at": None,
                    },
                )

            try:
                result = runner.run(request)
            except Exception as exc:  # pragma: no cover - exercised via integration behavior
                if self._turn_stop_requested(quest_id):
                    return
                failure_summary = f"Runner `{runner_name}` failed on attempt {attempt_index}/{max_attempts}: {exc}"
                retry_context = self._build_retry_context(
                    quest_id=quest_id,
                    failed_run_id=current_run_id,
                    turn_id=turn_id,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    failure_kind="exception",
                    failure_summary=failure_summary,
                    previous_exit_code=None,
                    previous_output_text="",
                    stderr_text=str(exc),
                )
                if bool(retry_policy.get("enabled")) and attempt_index < max_attempts:
                    delay_seconds = self._retry_delay_seconds(retry_policy, attempt_index=attempt_index + 1)
                    next_retry_at = utc_now() if delay_seconds <= 0 else None
                    self.quest_service.update_runtime_state(
                        quest_root=quest_root,
                        status="running",
                        display_status="retrying",
                        active_run_id=None,
                        retry_state={
                            "turn_id": turn_id,
                            "attempt_index": attempt_index,
                            "max_attempts": max_attempts,
                            "last_run_id": current_run_id,
                            "last_error": failure_summary,
                            "next_retry_at": next_retry_at,
                        },
                    )
                    self._append_retry_event(
                        quest_id,
                        event_type="runner.turn_retry_scheduled",
                        runner_name=runner_name,
                        run_id=current_run_id,
                        turn_id=turn_id,
                        skill_id=skill_id,
                        model=model,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        summary=f"Attempt {attempt_index}/{max_attempts} failed. Retrying in {delay_seconds:.1f}s.",
                        failure_summary=failure_summary,
                        backoff_seconds=delay_seconds,
                        next_attempt_index=attempt_index + 1,
                    )
                    if self._wait_for_retry_delay(quest_id, delay_seconds):
                        continue
                    self._append_retry_event(
                        quest_id,
                        event_type="runner.turn_retry_aborted",
                        runner_name=runner_name,
                        run_id=current_run_id,
                        turn_id=turn_id,
                        skill_id=skill_id,
                        model=model,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        summary="Retry sequence aborted because the quest was stopped or paused.",
                        failure_summary=failure_summary,
                    )
                    return
                exhausted_summary = f"{failure_summary} Retry budget exhausted after {attempt_index} attempt(s)."
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_exhausted",
                    runner_name=runner_name,
                    run_id=current_run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary=exhausted_summary,
                    failure_summary=failure_summary,
                )
                self._record_turn_error(
                    quest_id=quest_id,
                    runner_name=runner_name,
                    run_id=current_run_id,
                    skill_id=skill_id,
                    model=model,
                    summary=exhausted_summary,
                    retry_state=None,
                )
                return

            if self._turn_stop_requested(quest_id):
                return

            if result.ok:
                self.quest_service.update_runtime_state(quest_root=quest_root, retry_state=None)
                if result.output_text:
                    self.quest_service.append_message(
                        quest_id,
                        role="assistant",
                        content=result.output_text,
                        source=runner_name,
                        run_id=result.run_id,
                        skill_id=skill_id,
                    )
                    self._relay_quest_message_to_bound_connectors(
                        quest_id,
                        message=result.output_text,
                        kind="assistant",
                        response_phase="final",
                        importance="normal",
                        attachments=[
                            {
                                "kind": "runner_result",
                                "run_id": result.run_id,
                                "skill_id": skill_id,
                                "runner": runner_name,
                                "model": result.model,
                                "exit_code": result.exit_code,
                                "history_root": str(result.history_root),
                                "run_root": str(result.run_root),
                            }
                        ],
                    )
                self._normalize_status_after_turn(quest_id)
                return

            failure_summary = f"Runner `{runner_name}` exited with code {result.exit_code} on attempt {attempt_index}/{max_attempts}."
            stderr_excerpt = self._trim_text(result.stderr_text, limit=240)
            if stderr_excerpt:
                failure_summary = f"{failure_summary} stderr: {stderr_excerpt}"
            retry_context = self._build_retry_context(
                quest_id=quest_id,
                failed_run_id=result.run_id,
                turn_id=turn_id,
                attempt_index=attempt_index,
                max_attempts=max_attempts,
                failure_kind="exit_code",
                failure_summary=failure_summary,
                previous_exit_code=result.exit_code,
                previous_output_text=result.output_text,
                stderr_text=result.stderr_text,
            )
            if bool(retry_policy.get("enabled")) and attempt_index < max_attempts:
                delay_seconds = self._retry_delay_seconds(retry_policy, attempt_index=attempt_index + 1)
                self.quest_service.update_runtime_state(
                    quest_root=quest_root,
                    status="running",
                    display_status="retrying",
                    active_run_id=None,
                    retry_state={
                        "turn_id": turn_id,
                        "attempt_index": attempt_index,
                        "max_attempts": max_attempts,
                        "last_run_id": result.run_id,
                        "last_error": failure_summary,
                        "next_retry_at": None,
                    },
                )
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_scheduled",
                    runner_name=runner_name,
                    run_id=result.run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary=f"Attempt {attempt_index}/{max_attempts} failed. Retrying in {delay_seconds:.1f}s.",
                    failure_summary=failure_summary,
                    backoff_seconds=delay_seconds,
                    next_attempt_index=attempt_index + 1,
                )
                if self._wait_for_retry_delay(quest_id, delay_seconds):
                    continue
                self._append_retry_event(
                    quest_id,
                    event_type="runner.turn_retry_aborted",
                    runner_name=runner_name,
                    run_id=result.run_id,
                    turn_id=turn_id,
                    skill_id=skill_id,
                    model=model,
                    attempt_index=attempt_index,
                    max_attempts=max_attempts,
                    summary="Retry sequence aborted because the quest was stopped or paused.",
                    failure_summary=failure_summary,
                )
                return

            exhausted_summary = f"{failure_summary} Retry budget exhausted after {attempt_index} attempt(s)."
            self._append_retry_event(
                quest_id,
                event_type="runner.turn_retry_exhausted",
                runner_name=runner_name,
                run_id=result.run_id,
                turn_id=turn_id,
                skill_id=skill_id,
                model=model,
                attempt_index=attempt_index,
                max_attempts=max_attempts,
                summary=exhausted_summary,
                failure_summary=failure_summary,
            )
            self._record_turn_error(
                quest_id=quest_id,
                runner_name=runner_name,
                run_id=result.run_id,
                skill_id=skill_id,
                model=model,
                summary=exhausted_summary,
                retry_state=None,
            )
            return

    def _runner_name_for(self, snapshot: dict) -> str:
        configured = self.config_manager.load_named("config")
        return str(snapshot.get("runner") or configured.get("default_runner", "codex")).strip().lower()

    @staticmethod
    def _turn_skill_for(snapshot: dict, latest_user_message: dict | None, *, turn_reason: str = "user_message") -> str:
        if str(turn_reason or "").strip() == "auto_continue" or latest_user_message is None:
            active_anchor = str(snapshot.get("active_anchor") or "").strip()
            return active_anchor if active_anchor in STANDARD_SKILLS else "decision"
        reply_target = str(latest_user_message.get("reply_to_interaction_id") or "").strip()
        if reply_target:
            for item in (snapshot.get("active_interactions") or []):
                candidate_ids = {
                    str(item.get("interaction_id") or "").strip(),
                    str(item.get("artifact_id") or "").strip(),
                }
                if reply_target in candidate_ids and (
                    str(item.get("status") or "") == "waiting"
                    or str(item.get("reply_mode") or "") == "blocking"
                    or str(item.get("kind") or "") == "decision_request"
                ):
                    return "decision"
            for item in (snapshot.get("recent_reply_threads") or []):
                candidate_ids = {
                    str(item.get("interaction_id") or "").strip(),
                    str(item.get("artifact_id") or "").strip(),
                }
                if reply_target in candidate_ids and (
                    str(item.get("reply_mode") or "") == "blocking"
                    or str(item.get("kind") or "") == "decision_request"
                ):
                    return "decision"
        active_anchor = str(snapshot.get("active_anchor") or "").strip()
        return active_anchor if active_anchor in STANDARD_SKILLS else "decision"

    def _latest_user_message(self, quest_id: str) -> dict | None:
        for item in reversed(self.quest_service.history(quest_id, limit=200)):
            if str(item.get("role") or "") == "user":
                return item
        return None

    @staticmethod
    def _runner_binary_issue(runner_name: str, runner: object) -> str | None:
        binary = getattr(runner, "binary", None)
        if not isinstance(binary, str) or not binary.strip():
            return None
        candidate = binary.strip()
        if os.sep in candidate or candidate.startswith("."):
            return None if Path(candidate).expanduser().exists() else f"Runner `{runner_name}` binary was not found at `{candidate}`."
        return None if which(candidate) else f"Runner `{runner_name}` binary `{candidate}` is not on PATH."

    @staticmethod
    def _trim_text(value: object, *, limit: int = 320) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.strip()
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except TypeError:
                text = str(value)
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _coerce_positive_int(value: object, default: int) -> int:
        try:
            resolved = int(value)
        except (TypeError, ValueError):
            return default
        return resolved if resolved > 0 else default

    @staticmethod
    def _coerce_nonnegative_float(value: object, default: float) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return default
        return resolved if resolved >= 0 else default

    def _runner_retry_policy(self, runner_cfg: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(runner_cfg.get("retry_on_failure", True))
        max_attempts = min(5, self._coerce_positive_int(runner_cfg.get("retry_max_attempts", 5), 5))
        initial_backoff = self._coerce_nonnegative_float(runner_cfg.get("retry_initial_backoff_sec", 1.0), 1.0)
        multiplier = max(1.0, self._coerce_nonnegative_float(runner_cfg.get("retry_backoff_multiplier", 2.0), 2.0))
        max_backoff = max(initial_backoff, self._coerce_nonnegative_float(runner_cfg.get("retry_max_backoff_sec", 8.0), 8.0))
        return {
            "enabled": enabled,
            "max_attempts": max_attempts,
            "initial_backoff_sec": initial_backoff,
            "backoff_multiplier": multiplier,
            "max_backoff_sec": max_backoff,
        }

    def _turn_stop_requested(self, quest_id: str) -> bool:
        with self._turn_lock:
            state = dict(self._turn_state.get(quest_id) or {})
        if state.get("stop_requested"):
            return True
        snapshot = self.quest_service.snapshot(quest_id)
        return str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip() in {"paused", "stopped"}

    def _retry_delay_seconds(self, retry_policy: dict[str, Any], *, attempt_index: int) -> float:
        if attempt_index <= 1:
            return 0.0
        initial_backoff = float(retry_policy.get("initial_backoff_sec") or 0.0)
        multiplier = float(retry_policy.get("backoff_multiplier") or 2.0)
        max_backoff = float(retry_policy.get("max_backoff_sec") or initial_backoff or 0.0)
        delay = initial_backoff * pow(multiplier, max(0, attempt_index - 2))
        return max(0.0, min(delay, max_backoff))

    def _wait_for_retry_delay(self, quest_id: str, delay_seconds: float) -> bool:
        if delay_seconds <= 0:
            return not self._turn_stop_requested(quest_id)
        deadline = time.monotonic() + delay_seconds
        while time.monotonic() < deadline:
            if self._turn_stop_requested(quest_id):
                return False
            time.sleep(min(0.1, max(0.01, deadline - time.monotonic())))
        return not self._turn_stop_requested(quest_id)

    def _append_retry_event(
        self,
        quest_id: str,
        *,
        event_type: str,
        runner_name: str,
        run_id: str,
        turn_id: str,
        skill_id: str,
        model: str,
        attempt_index: int,
        max_attempts: int,
        summary: str,
        failure_summary: str | None = None,
        backoff_seconds: float | None = None,
        next_attempt_index: int | None = None,
        previous_run_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event_id": generate_id("evt"),
            "type": event_type,
            "quest_id": quest_id,
            "turn_id": turn_id,
            "run_id": run_id,
            "source": runner_name,
            "skill_id": skill_id,
            "model": model,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "summary": summary,
            "created_at": utc_now(),
        }
        if failure_summary:
            payload["failure_summary"] = failure_summary
        if backoff_seconds is not None:
            payload["backoff_seconds"] = backoff_seconds
        if next_attempt_index is not None:
            payload["next_attempt_index"] = next_attempt_index
        if previous_run_id:
            payload["previous_run_id"] = previous_run_id
        append_jsonl(self.home / "quests" / quest_id / ".ds" / "events.jsonl", payload)
        self.logger.log(
            "warning" if "scheduled" in event_type or "exhausted" in event_type else "info",
            event_type,
            quest_id=quest_id,
            run_id=run_id,
            turn_id=turn_id,
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            failure_summary=failure_summary,
            backoff_seconds=backoff_seconds,
            next_attempt_index=next_attempt_index,
            previous_run_id=previous_run_id,
        )
        return payload

    def _build_retry_context(
        self,
        *,
        quest_id: str,
        failed_run_id: str,
        turn_id: str,
        attempt_index: int,
        max_attempts: int,
        failure_kind: str,
        failure_summary: str,
        previous_exit_code: int | None,
        previous_output_text: str,
        stderr_text: str,
    ) -> dict[str, Any]:
        snapshot = self.quest_service.snapshot(quest_id)
        quest_root = Path(snapshot["quest_root"])
        workspace_root = Path(str(snapshot.get("current_workspace_root") or snapshot.get("quest_root") or quest_root))
        quest_events = read_jsonl(quest_root / ".ds" / "events.jsonl")
        run_events = [event for event in quest_events if str(event.get("run_id") or "").strip() == failed_run_id][-120:]

        recent_messages: list[str] = []
        tool_progress: list[dict[str, str]] = []
        seen_messages: set[str] = set()
        for event in run_events:
            event_type = str(event.get("type") or "").strip()
            if event_type in {"runner.delta", "runner.agent_message", "runner.reasoning"}:
                text = self._trim_text(event.get("text"), limit=280)
                if text and text not in seen_messages:
                    recent_messages.append(text)
                    seen_messages.add(text)
                continue
            if event_type not in {"runner.tool_call", "runner.tool_result"}:
                continue
            tool_progress.append(
                {
                    "tool_name": str(event.get("tool_name") or "tool").strip() or "tool",
                    "status": str(event.get("status") or "").strip(),
                    "args": self._trim_text(event.get("args"), limit=220),
                    "output": self._trim_text(event.get("output"), limit=220),
                }
            )

        git_status_lines: list[str] = []
        try:
            git_status = run_command(["git", "status", "--short"], cwd=workspace_root, check=False)
            git_status_lines = [
                line.strip()
                for line in str(git_status.stdout or git_status.stderr or "").splitlines()
                if line.strip()
            ][:12]
        except Exception:
            git_status_lines = []

        bash_sessions = self.bash_exec_service.list_sessions(quest_root, limit=3)
        bash_session_summaries = [
            {
                "bash_id": str(item.get("bash_id") or item.get("id") or "").strip(),
                "status": str(item.get("status") or "").strip(),
                "command": self._trim_text(item.get("command"), limit=180),
            }
            for item in bash_sessions[:3]
        ]

        recent_artifacts: list[str] = []
        for item in (snapshot.get("recent_artifacts") or [])[-3:]:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") or {}
            label = (
                str((payload or {}).get("artifact_id") or "").strip()
                or Path(str(item.get("path") or "artifact")).stem
            )
            summary = self._trim_text(
                (payload or {}).get("summary") or (payload or {}).get("reason") or (payload or {}).get("guidance"),
                limit=220,
            )
            recent_artifacts.append(
                " -> ".join(part for part in (str(item.get("kind") or "artifact").strip(), label, summary) if part)
            )

        return {
            "turn_id": turn_id,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "previous_run_id": failed_run_id,
            "previous_exit_code": previous_exit_code,
            "failure_kind": failure_kind,
            "failure_summary": failure_summary,
            "previous_output_text": self._trim_text(previous_output_text, limit=1800),
            "stderr_tail": self._trim_text(stderr_text, limit=1800),
            "recent_messages": recent_messages[-6:],
            "tool_progress": tool_progress[-8:],
            "workspace_summary": {
                "branch": str(snapshot.get("branch") or "").strip(),
                "git_status": git_status_lines,
                "bash_sessions": bash_session_summaries,
            },
            "recent_artifacts": [item for item in recent_artifacts if item],
        }

    def _record_turn_error(
        self,
        *,
        quest_id: str,
        runner_name: str,
        run_id: str,
        skill_id: str,
        model: str,
        summary: str,
        display_status: str = "error",
        retry_state: dict[str, Any] | None = None,
    ) -> None:
        quest_root = self.home / "quests" / quest_id
        append_jsonl(
            quest_root / ".ds" / "events.jsonl",
            {
                "event_id": generate_id("evt"),
                "type": "runner.turn_error",
                "quest_id": quest_id,
                "run_id": run_id,
                "source": runner_name,
                "skill_id": skill_id,
                "model": model,
                "summary": summary,
                "created_at": utc_now(),
            },
        )
        self.quest_service.update_runtime_state(
            quest_root=quest_root,
            status="active",
            display_status=display_status,
            active_run_id=None,
            retry_state=retry_state,
        )
        self.logger.log(
            "error",
            "runner.turn_error",
            quest_id=quest_id,
            run_id=run_id,
            runner=runner_name,
            skill_id=skill_id,
            model=model,
            summary=summary,
        )
        self._relay_quest_message_to_bound_connectors(
            quest_id,
            message=summary,
            kind="error",
            response_phase="final",
            importance="warning",
            attachments=[
                {
                    "kind": "runner_error",
                    "run_id": run_id,
                    "skill_id": skill_id,
                    "runner": runner_name,
                    "model": model,
                }
            ],
        )

    def _normalize_status_after_turn(self, quest_id: str) -> None:
        with self._turn_lock:
            if bool((self._turn_state.get(quest_id) or {}).get("stop_requested")):
                return
        snapshot = self.quest_service.snapshot(quest_id)
        current_status = str(snapshot.get("status") or snapshot.get("display_status") or "active").strip() or "active"
        normalized_status = "active" if current_status == "running" else current_status
        snapshot = self.quest_service.mark_turn_finished(quest_id, status=normalized_status)
        status = str(snapshot.get("status") or "")
        if status in {"stopped", "paused", "completed", "error"}:
            return
        if status == "waiting_for_user":
            if snapshot.get("waiting_interaction_id"):
                return
            if int(snapshot.get("pending_user_message_count") or 0) > 0:
                self.schedule_turn(quest_id, reason="queued_user_messages")
            else:
                self.schedule_turn(quest_id, reason="auto_continue")
            return
        if int(snapshot.get("pending_user_message_count") or 0) > 0:
            self.schedule_turn(quest_id, reason="queued_user_messages")
            return
        self.schedule_turn(quest_id, reason="auto_continue")

    def _relay_quest_message_to_bound_connectors(
        self,
        quest_id: str,
        *,
        message: str,
        kind: str = "assistant",
        response_phase: str | None = "final",
        importance: str | None = "normal",
        attachments: list[dict[str, object]] | None = None,
    ) -> list[str]:
        text = str(message or "").strip()
        if not text:
            return []
        quest_root = self.quest_service._quest_root(quest_id)
        connectors = self.artifact_service._connectors_config()
        targets = self.artifact_service._select_delivery_targets(
            self.artifact_service._bound_conversations(quest_root),
            connectors=connectors,
        )
        delivered: list[str] = []
        for target in targets:
            channel_name = self.artifact_service._normalize_channel_name(target)
            payload = {
                "quest_root": str(quest_root),
                "quest_id": quest_id,
                "conversation_id": target,
                "kind": kind,
                "message": text,
                "response_phase": response_phase,
                "importance": importance,
                "attachments": attachments or [],
            }
            if self.artifact_service._send_to_channel(channel_name, payload, connectors=connectors):
                delivered.append(target)
        return delivered

    def request_shutdown(self, *, source: str = "local-admin") -> dict:
        if self._shutdown_requested.is_set():
            return {
                "ok": True,
                "message": "DeepScientist daemon shutdown is already in progress.",
                "source": source,
            }
        interrupted_quests: list[str] = []
        for snapshot in self.quest_service.list_quests():
            quest_id = str(snapshot.get("quest_id") or "").strip()
            if not quest_id:
                continue
            if snapshot.get("status") != "running" and not snapshot.get("active_run_id"):
                continue
            result = self.stop_quest(quest_id, source=source)
            if result.get("ok"):
                interrupted_quests.append(quest_id)
        self._shutdown_requested.set()
        self._stop_background_connectors()
        self._stop_terminal_attach_server()
        self.bash_exec_service.shutdown()
        self.logger.log(
            "info",
            "daemon.shutdown_requested",
            source=source,
            interrupted_quests=interrupted_quests,
        )

        server = self._server

        def _shutdown_server() -> None:
            time.sleep(0.05)
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    return

        threading.Thread(
            target=_shutdown_server,
            daemon=True,
            name="deepscientist-daemon-shutdown",
        ).start()
        return {
            "ok": True,
            "message": "DeepScientist daemon shutdown requested.",
            "source": source,
            "interrupted_quests": interrupted_quests,
        }

    def handle_qq_inbound(self, body: dict) -> dict:
        return self.handle_connector_inbound("qq", body)

    def list_qq_bindings(self) -> list[dict]:
        return self._qq_channel().list_bindings()

    def list_connector_bindings(self, connector_name: str) -> list[dict]:
        channel = self._channel_with_bindings(connector_name)
        return channel.list_bindings()

    def preview_connector_binding_conflicts(
        self,
        requested_bindings: list[dict[str, object]] | None,
        *,
        quest_id: str | None = None,
    ) -> list[dict[str, object]]:
        normalized_bindings = self._normalize_requested_connector_bindings(requested_bindings)
        conflicts: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for item in normalized_bindings:
            connector_name = str(item.get("connector") or "").strip().lower()
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not connector_name or not conversation_id:
                continue
            for conflict in self._inspect_connector_binding_conflicts(quest_id, conversation_id):
                conflict_quest_id = str(conflict.get("quest_id") or "").strip()
                identity = (connector_name, conflict_quest_id)
                if not conflict_quest_id or identity in seen:
                    continue
                seen.add(identity)
                conflicts.append(
                    {
                        "connector": connector_name,
                        "conversation_id": conversation_id,
                        **conflict,
                    }
                )
        return conflicts

    def _inspect_connector_binding_conflicts(
        self,
        quest_id: str | None,
        conversation_id: str,
    ) -> list[dict[str, object]]:
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)
        if parsed is None or str(parsed.get("connector") or "").strip().lower() == "local":
            return []
        connector_name = str(parsed.get("connector") or "").strip().lower()
        if connector_name not in self.channels:
            return []
        channel = self._channel_with_bindings(connector_name)
        conversation_key = conversation_identity_key(normalized)
        titles = self._quest_titles_by_id()
        conflicts: list[dict[str, object]] = []
        existing_bound = channel.resolve_bound_quest(normalized)
        normalized_quest_id = str(quest_id or "").strip() or None
        if existing_bound and existing_bound != normalized_quest_id:
            conflicts.append(
                {
                    "quest_id": existing_bound,
                    "title": titles.get(existing_bound),
                    "reason": "connector_binding",
                }
            )
        for item in self.quest_service.list_quests():
            other_id = str(item.get("quest_id") or "").strip()
            if not other_id or other_id == normalized_quest_id:
                continue
            sources = self.quest_service.binding_sources(other_id)
            if any(conversation_identity_key(source) == conversation_key for source in sources):
                conflicts.append(
                    {
                        "quest_id": other_id,
                        "title": titles.get(other_id),
                        "reason": "quest_binding",
                    }
                )
        deduped_conflicts: list[dict[str, object]] = []
        seen_conflict_ids: set[str] = set()
        for item in conflicts:
            candidate = str(item.get("quest_id") or "").strip()
            if not candidate or candidate in seen_conflict_ids:
                continue
            seen_conflict_ids.add(candidate)
            deduped_conflicts.append(item)
        return deduped_conflicts

    def _unbind_quest_connector_bindings(
        self,
        quest_id: str,
        connector_name: str,
        *,
        preserve: set[str] | None = None,
    ) -> list[str]:
        normalized_connector = str(connector_name or "").strip().lower()
        preserve_keys = {conversation_identity_key(item) for item in (preserve or set()) if item}
        removed: list[str] = []
        if not normalized_connector or normalized_connector == "local":
            return removed
        try:
            channel = self._channel_with_bindings(normalized_connector)
        except Exception:
            return removed
        for item in channel.list_bindings():
            if str(item.get("quest_id") or "").strip() != quest_id:
                continue
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not conversation_id:
                continue
            if preserve_keys and conversation_identity_key(conversation_id) in preserve_keys:
                continue
            if channel.unbind_conversation(conversation_id, quest_id=quest_id):
                removed.append(conversation_id)
                self.sessions.unbind(quest_id, conversation_id)
        for conversation_id in removed:
            self.quest_service.unbind_source(quest_id, conversation_id)
        return removed

    def _apply_conversation_binding(
        self,
        quest_id: str,
        conversation_id: str,
        *,
        force: bool = False,
        clear_scope: str = "connector",
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)
        if parsed is None:
            return 400, {"ok": False, "message": f"Invalid connector conversation `{conversation_id}`."}
        connector_name = str(parsed.get("connector") or "").strip().lower()
        if not connector_name or connector_name == "local" or connector_name not in self.channels:
            return 400, {"ok": False, "message": f"Unknown connector `{connector_name}` for conversation `{normalized}`."}
        channel = self._channel_with_bindings(connector_name)
        conflicts = self._inspect_connector_binding_conflicts(quest_id, normalized)
        if conflicts and not force:
            return 409, {
                "ok": False,
                "conflict": True,
                "message": "Conversation is already bound to another quest.",
                "quest_id": quest_id,
                "connector": connector_name,
                "conversation_id": normalized,
                "conflicts": conflicts,
            }
        existing_bound = channel.resolve_bound_quest(normalized)
        for item in conflicts:
            other_id = str(item.get("quest_id") or "").strip()
            if other_id and other_id != quest_id:
                self.quest_service.unbind_source(other_id, normalized)
                self.sessions.unbind(other_id, normalized)
        channel.bind_conversation(normalized, quest_id)
        self.sessions.bind(quest_id, normalized)
        self.quest_service.bind_source(quest_id, "local:default")
        self.quest_service.bind_source(quest_id, normalized)
        if clear_scope == "all_external":
            removed = self._unbind_external_bindings(quest_id, preserve={normalized})
        elif clear_scope == "connector":
            removed = self._unbind_quest_connector_bindings(quest_id, connector_name, preserve={normalized})
        else:
            removed = []
        snapshot = self.quest_service.snapshot(quest_id)
        previous_quest_id = str(existing_bound or "").strip() or None
        if previous_quest_id == quest_id:
            previous_quest_id = None
        if previous_quest_id is None:
            for item in conflicts:
                candidate = str(item.get("quest_id") or "").strip()
                if candidate and candidate != quest_id:
                    previous_quest_id = candidate
                    break
        return {
            "ok": True,
            "quest_id": quest_id,
            "connector": connector_name,
            "conversation_id": normalized,
            "snapshot": snapshot,
            "removed_conversations": removed,
            "conflicts_resolved": [item.get("quest_id") for item in conflicts if item.get("quest_id")],
            "previous_quest_id": previous_quest_id,
        }

    def update_quest_connector_binding(
        self,
        quest_id: str,
        connector_name: str,
        conversation_id: str | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized_connector = str(connector_name or "").strip().lower()
        if not normalized_connector or normalized_connector == "local":
            return 400, {"ok": False, "message": "A non-local connector name is required."}
        if normalized_connector not in self.channels:
            return 400, {"ok": False, "message": f"Unknown connector `{normalized_connector}`."}

        normalized = normalize_conversation_id(conversation_id)
        if not normalized:
            removed = self._unbind_quest_connector_bindings(quest_id, normalized_connector)
            self.quest_service.bind_source(quest_id, "local:default")
            snapshot = self.quest_service.snapshot(quest_id)
            return {
                "ok": True,
                "quest_id": quest_id,
                "connector": normalized_connector,
                "conversation_id": None,
                "snapshot": snapshot,
                "removed_conversations": removed,
            }

        parsed = parse_conversation_id(normalized)
        if parsed is None:
            return 400, {"ok": False, "message": f"Invalid connector conversation `{normalized}`."}
        if str(parsed.get("connector") or "").strip().lower() != normalized_connector:
            return 400, {
                "ok": False,
                "message": f"Conversation `{normalized}` does not belong to connector `{normalized_connector}`.",
            }

        return self._apply_conversation_binding(quest_id, normalized, force=force, clear_scope="connector")

    def update_quest_bindings(
        self,
        quest_id: str,
        requested_bindings: list[dict[str, object]] | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        quest_root = self.home / "quests" / quest_id
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        normalized_bindings = self._normalize_requested_connector_bindings(requested_bindings)
        conflicts = self.preview_connector_binding_conflicts(normalized_bindings, quest_id=quest_id)
        if conflicts and not force:
            return 409, {
                "ok": False,
                "conflict": True,
                "message": "One or more connector targets are already bound to another quest.",
                "quest_id": quest_id,
                "conflicts": conflicts,
            }
        results: list[dict[str, object]] = []
        for item in normalized_bindings:
            connector_name = str(item.get("connector") or "").strip().lower()
            result = self.update_quest_connector_binding(
                quest_id,
                connector_name,
                str(item.get("conversation_id") or "").strip() or None,
                force=True if force or conflicts else False,
            )
            if isinstance(result, tuple):
                return result
            results.append(result)
        snapshot = self.quest_service.snapshot(quest_id)
        return {
            "ok": True,
            "quest_id": quest_id,
            "snapshot": snapshot,
            "results": results,
        }

    def update_quest_binding(
        self,
        quest_id: str,
        conversation_id: str | None,
        *,
        force: bool = False,
    ) -> dict | tuple[int, dict]:
        normalized = normalize_conversation_id(conversation_id)
        parsed = parse_conversation_id(normalized)

        if parsed is None or parsed.get("connector", "").lower() == "local":
            removed = self._unbind_external_bindings(quest_id)
            self.quest_service.set_binding_sources(quest_id, ["local:default"])
            snapshot = self.quest_service.snapshot(quest_id)
            return {
                "ok": True,
                "quest_id": quest_id,
                "conversation_id": None,
                "snapshot": snapshot,
                "removed_conversations": removed,
            }

        connector_name = str(parsed.get("connector") or "").strip().lower()
        if connector_name not in self.channels or connector_name == "local":
            return 400, {"ok": False, "message": f"Unknown connector `{connector_name}` for conversation `{normalized}`."}
        return self._apply_conversation_binding(quest_id, normalized, force=force, clear_scope="all_external")

    def delete_quest(self, quest_id: str, *, source: str = "web") -> dict | tuple[int, dict]:
        quests_root = self.home / "quests"
        try:
            quest_root = resolve_within(quests_root, quest_id)
        except ValueError:
            return 400, {"ok": False, "message": "Invalid quest id."}
        if not quest_root.joinpath("quest.yaml").exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

        snapshot = self.quest_service.snapshot(quest_id)
        runtime_status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip().lower()
        if runtime_status == "running" or snapshot.get("active_run_id"):
            try:
                self.stop_quest(quest_id, source=source)
            except Exception:
                pass

        stopped_bash_sessions: list[str] = []
        try:
            for session in self.bash_exec_service.list_sessions(quest_root, limit=500):
                status = str(session.get("status") or "").strip().lower()
                if status in {"completed", "failed", "terminated"}:
                    continue
                bash_id = str(session.get("bash_id") or "").strip()
                if not bash_id:
                    continue
                try:
                    self.bash_exec_service.request_stop(
                        quest_root,
                        bash_id,
                        reason="quest_deleted",
                        user_id=source,
                    )
                    stopped_bash_sessions.append(bash_id)
                except Exception:
                    continue
        except Exception:
            stopped_bash_sessions = []

        removed_conversations = self._unbind_external_bindings(quest_id)
        self.sessions.forget(quest_id)

        try:
            shutil.rmtree(quest_root)
        except FileNotFoundError:
            return {"ok": True, "quest_id": quest_id, "deleted": False}

        self.logger.log(
            "info",
            "quest.deleted",
            quest_id=quest_id,
            source=source,
            removed_conversations=removed_conversations,
            stopped_bash_sessions=stopped_bash_sessions,
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "deleted": True,
            "removed_conversations": removed_conversations,
            "stopped_bash_sessions": stopped_bash_sessions,
        }

    def handle_connector_inbound(self, connector_name: str, body: dict) -> dict:
        channel = self._channel_with_bindings(connector_name)
        ingested = channel.ingest(body)
        if not ingested.get("accepted", False):
            return {
                "ok": True,
                "accepted": False,
                "reason": ingested.get("normalized", {}).get("reason"),
                "normalized": ingested.get("normalized"),
            }
        normalized = ingested["normalized"]
        if connector_name == "qq":
            qq_binding = self._maybe_bind_qq_main_chat(normalized)
            if qq_binding is not None:
                normalized = {
                    **normalized,
                    "_qq_main_chat_binding": qq_binding,
                }
        reply = self._route_connector_message(connector_name, normalized)
        return {
            "ok": True,
            "accepted": True,
            "normalized": normalized,
            "reply": reply,
        }

    def _route_connector_message(self, connector_name: str, message: dict) -> dict:
        channel = self._channel_with_bindings(connector_name)
        connector_label = self._connector_label(connector_name)
        conversation_id = str(message.get("conversation_id") or "")
        text = str(message.get("text") or "").strip()
        command_prefix = channel.command_prefix()
        quest_id = channel.resolve_bound_quest(conversation_id)

        if text.startswith(command_prefix):
            command_name, args = self._parse_prefixed_command(text, command_prefix)
            if command_name == "help":
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "help",
                        "message": self._connector_home_help(connector_name, message=message),
                    }
                )
            if command_name in {"projects", "quests", "list"}:
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "projects",
                        "message": self._format_projects_list(),
                    }
                )
            if command_name == "new":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供研究目标，例如 `/new 复现一个图神经网络基线`。",
                                en="Please provide a quest goal first, for example `/new reproduce a graph baseline`.",
                            ),
                        }
                    )
                previous_quest_id = quest_id
                goal_text = " ".join(args).strip()
                created = self.create_quest(
                    goal=goal_text,
                    source=f"{connector_name}:connector",
                    announce_connector_binding=True,
                    exclude_conversation_id=conversation_id,
                )
                self.update_quest_binding(created["quest_id"], conversation_id, force=True)
                self.submit_user_message(
                    created["quest_id"],
                    text=goal_text,
                    source=conversation_id,
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": created["quest_id"],
                        "kind": "ack",
                        "message": self._with_qq_main_chat_notice(
                            message,
                            self._quest_created_connector_message(
                                connector_name,
                                quest_id=created["quest_id"],
                                goal=goal_text,
                                previous_quest_id=previous_quest_id,
                            ),
                        ),
                    }
                )
            if command_name == "use":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/use 001`。",
                                en="Please provide a quest id first, for example `/use 001`.",
                            ),
                        }
                    )
                target_quest = args[0]
                if target_quest in {"latest", "newest"}:
                    quests = self.quest_service.list_quests()
                    target_quest = str(quests[0]["quest_id"]) if quests else ""
                if not (self.home / "quests" / target_quest / "quest.yaml").exists():
                    available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"老师，目前没有找到 quest `{target_quest}`。可用 quest 包括：{available}。",
                                en=f"I could not find quest `{target_quest}`. Available quests: {available}.",
                            ),
                        }
                    )
                self.update_quest_binding(target_quest, conversation_id, force=True)
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": target_quest,
                        "kind": "ack",
                        "message": self._polite_copy(
                            zh=f"老师，已将当前 {connector_label} 会话绑定到 {target_quest}，我会继续推进并同步计划。",
                            en=f"Received. I’ve bound this {connector_label} conversation to {target_quest} and will keep the plan moving.",
                        ),
                    }
                )
            if command_name == "delete":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/delete 001 --yes`（删除是危险操作，需要确认）。",
                                en="Please provide a quest id, for example `/delete 001 --yes` (destructive; requires confirmation).",
                            ),
                        }
                    )
                target_quest = str(args[0] or "").strip()
                if target_quest in {"latest", "newest"}:
                    quests = self.quest_service.list_quests()
                    target_quest = str(quests[0]["quest_id"]) if quests else ""
                confirmed = any(str(item).strip().lower() in {"--yes", "--force", "-y"} for item in args[1:])
                if not confirmed:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"即将删除 quest `{target_quest}`（不可恢复）。如确认，请发送：`/delete {target_quest} --yes`。",
                                en=f"About to delete quest `{target_quest}` (irreversible). To confirm, send: `/delete {target_quest} --yes`.",
                            ),
                        }
                    )
                if not target_quest:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供 quest id，例如 `/delete 001 --yes`。",
                                en="Please provide a quest id, for example `/delete 001 --yes`.",
                            ),
                        }
                    )
                if not (self.home / "quests" / target_quest / "quest.yaml").exists():
                    available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh=f"老师，目前没有找到 quest `{target_quest}`。可用 quest 包括：{available}。",
                                en=f"I could not find quest `{target_quest}`. Available quests: {available}.",
                            ),
                        }
                    )
                delete_result = self.delete_quest(target_quest, source=f"{connector_name}:connector")
                if isinstance(delete_result, tuple):
                    _, payload = delete_result
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": str(payload.get("message") or "Failed to delete quest."),
                        }
                    )
                follow_hint = self._polite_copy(
                    zh="如需继续，请使用 `/projects` 查看列表，或 `/use latest` 绑定最新 quest。",
                    en="To continue, use `/projects` to list quests, or `/use latest` to bind the newest quest.",
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "quest_deleted",
                        "message": self._polite_copy(
                            zh=f"老师，已删除 quest `{target_quest}`。\n{follow_hint}",
                            en=f"Deleted quest `{target_quest}`.\n{follow_hint}",
                        ),
                    }
                )

            if quest_id is None and command_name and command_name not in {"help", "projects", "quests", "list", "new", "use", "delete"}:
                auto_bound = self._maybe_auto_bind_connector_conversation(connector_name, conversation_id)
                if auto_bound is not None:
                    quest_id = str(auto_bound.get("quest_id") or "").strip() or None

            if command_name in {"stop", "resume"}:
                target_quest_id = quest_id
                if args:
                    target_quest_id = self._resolve_quest_reference(args[0])
                if not self._quest_exists(target_quest_id):
                    if args:
                        requested = str(args[0] or "").strip() or "<quest_id>"
                        available = ", ".join(item["quest_id"] for item in self.quest_service.list_quests()[:6]) or "none"
                        return channel.send(
                            {
                                "conversation_id": conversation_id,
                                "kind": "ack",
                                "message": self._polite_copy(
                                    zh=f"老师，目前没有找到 quest `{requested}`。可用 quest 包括：{available}。",
                                    en=f"I could not find quest `{requested}`. Available quests: {available}.",
                                ),
                            }
                        )
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "kind": "ack",
                            "message": self._connector_home_help(connector_name, message=message),
                        }
                    )
                target_quest_id = str(target_quest_id or "").strip()
                bound_quest_id = str(channel.resolve_bound_quest(conversation_id) or "").strip() or None
                self.sessions.bind(target_quest_id, conversation_id)
                self.quest_service.bind_source(target_quest_id, conversation_id)
                result = self.control_quest(
                    target_quest_id,
                    action=command_name,
                    source=f"{connector_name}:connector",
                )
                return self._connector_control_reply(
                    connector_name,
                    conversation_id=conversation_id,
                    quest_id=target_quest_id,
                    action=command_name,
                    result=result,
                    deliver_directly=bound_quest_id != target_quest_id,
                )

            if quest_id is None:
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "kind": "ack",
                        "message": self._connector_home_help(connector_name, message=message),
                    }
                )

            self.sessions.bind(quest_id, conversation_id)
            self.quest_service.bind_source(quest_id, conversation_id)
            if command_name == "status":
                snapshot = self.quest_service.snapshot(quest_id)
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "status",
                        "message": self._format_status(snapshot),
                    }
                )
            if command_name == "summary":
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "summary",
                        "message": self._format_summary(quest_id),
                    }
                )
            if command_name == "metrics":
                run_id = args[0] if args else None
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "metrics",
                        "message": self._format_metrics(quest_id, run_id=run_id),
                    }
                )
            if command_name == "graph":
                graph = self.artifact_service.render_git_graph(self.home / "quests" / quest_id)
                attachments = [
                    {"kind": "path", "path": graph["graph"].get("png_path") or graph["graph"].get("svg_path")},
                    {"kind": "path", "path": graph["graph"].get("json_path")},
                ]
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "graph",
                        "message": self._format_graph_reply(quest_id, graph["graph"]),
                        "attachments": [item for item in attachments if item.get("path")],
                    }
                )
            if command_name == "terminal":
                quest_root = self.home / "quests" / quest_id
                workspace_root = self.quest_service.active_workspace_root(quest_root)
                session = self.bash_exec_service.ensure_terminal_session(
                    quest_root,
                    quest_id=quest_id,
                    cwd=workspace_root,
                    source=f"{connector_name}:connector",
                    conversation_id=conversation_id,
                    user_id=f"user:{connector_name}",
                )
                if args and args[0] == "-R":
                    restored = self.bash_exec_service.terminal_restore_payload(
                        quest_root,
                        str(session.get("bash_id") or ""),
                        command_limit=10,
                        output_limit=40,
                    )
                    commands = [
                        str(item.get("command") or "").strip()
                        for item in restored.get("latest_commands") or []
                        if str(item.get("command") or "").strip()
                    ]
                    tail_preview = [
                        str(item.get("line") or "").strip()
                        for item in (restored.get("tail") or [])[-4:]
                        if str(item.get("line") or "").strip()
                    ]
                    lines = [
                        f"Terminal `{restored.get('session_id')}`",
                        f"status: {restored.get('status') or 'unknown'}",
                        f"cwd: {restored.get('cwd') or session.get('cwd') or quest_root}",
                    ]
                    if commands:
                        lines.append("latest commands:")
                        lines.extend(f"- {item}" for item in reversed(commands[-10:]))
                    if tail_preview:
                        lines.append("recent output:")
                        lines.extend(f"- {item}" for item in tail_preview)
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "terminal_restore",
                            "message": "\n".join(lines),
                        }
                    )
                if args:
                    command_text = " ".join(args).rstrip()
                    result = self.bash_exec_service.append_terminal_input(
                        quest_root,
                        str(session.get("bash_id") or ""),
                        data=f"{command_text}\n",
                        source=f"{connector_name}:connector",
                        user_id=f"user:{connector_name}",
                        conversation_id=conversation_id,
                    )
                    cwd_value = str(result.get("session", {}).get("cwd") or session.get("cwd") or quest_root)
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "terminal",
                            "message": self._polite_copy(
                                zh=f"已发送到终端 `{session.get('bash_id')}`，当前路径：`{cwd_value}`。\n命令：`{command_text}`",
                                en=f"Sent to terminal `{session.get('bash_id')}` at `{cwd_value}`.\nCommand: `{command_text}`",
                            ),
                        }
                    )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "terminal",
                        "message": self._polite_copy(
                            zh=f"终端 `{session.get('bash_id')}` 已就绪。\n状态：{session.get('status')}\n当前路径：`{session.get('cwd')}`",
                            en=f"Terminal `{session.get('bash_id')}` is ready.\nstatus: {session.get('status')}\ncwd: `{session.get('cwd')}`",
                        ),
                    }
                )
            if command_name == "approve":
                if not args:
                    return channel.send(
                        {
                            "conversation_id": conversation_id,
                            "quest_id": quest_id,
                            "kind": "ack",
                            "message": self._polite_copy(
                                zh="老师您好，请先提供决策 id，例如 `/approve decision-001`。",
                                en="Please provide a decision id, for example `/approve decision-001`.",
                            ),
                        }
                    )
                decision_id = args[0]
                reason = " ".join(args[1:]).strip() or self._polite_copy(
                    zh=f"由 {connector_label} 侧确认通过。",
                    en=f"Approved from {connector_label}.",
                )
                result = self.artifact_service.record(
                    self.home / "quests" / quest_id,
                    {
                        "kind": "approval",
                        "decision_id": decision_id,
                        "reason": reason,
                        "source": {
                            "kind": "user",
                            "conversation_id": conversation_id,
                            "user_id": message.get("sender_id"),
                        },
                        "raw_text": text,
                    },
                )
                return channel.send(
                    {
                        "conversation_id": conversation_id,
                        "quest_id": quest_id,
                        "kind": "approval_result",
                        "message": self._polite_copy(
                            zh=f"Approval recorded for `{decision_id}`. 老师，已记录通过决定。原因：{reason}",
                            en=f"Approval recorded for `{decision_id}`. Reason: {reason}",
                        ),
                        "attachments": [{"kind": "path", "path": result.get("path")}],
                    }
                )

        if quest_id is None:
            auto_bound = self._maybe_auto_bind_connector_conversation(connector_name, conversation_id)
            if auto_bound is not None:
                quest_id = str(auto_bound.get("quest_id") or "").strip() or None

        if quest_id is None:
            return channel.send(
                {
                    "conversation_id": conversation_id,
                    "kind": "ack",
                    "message": self._connector_home_help(connector_name, message=message),
                }
            )

        self.sessions.bind(quest_id, conversation_id)
        materialized_attachments = self._materialize_connector_attachments(
            quest_id=quest_id,
            connector_name=connector_name,
            conversation_id=conversation_id,
            message_id=str(message.get("message_id") or "").strip() or None,
            attachments=[dict(item) for item in (message.get("attachments") or []) if isinstance(item, dict)],
        )
        self.submit_user_message(
            quest_id,
            text=self._connector_message_text_with_attachment_notice(
                original_text=text,
                attachments=materialized_attachments,
            ),
            source=conversation_id,
            attachments=materialized_attachments,
        )
        return channel.send(
            {
                "conversation_id": conversation_id,
                "quest_id": quest_id,
                "kind": "ack",
                "message": self._with_qq_main_chat_notice(
                    message,
                    self._polite_copy(
                        zh=f"老师，已收到您的消息，当前会话已绑定到 {quest_id}。我会继续推进，并通过后续消息同步进展。",
                        en=f"Received. This conversation is bound to {quest_id}; I’ll continue the work and keep you updated with the next progress checkpoint.",
                    ),
                ),
            }
        )

    def _connector_message_text_with_attachment_notice(
        self,
        *,
        original_text: str,
        attachments: list[dict[str, object]],
    ) -> str:
        base = str(original_text or "").strip()
        if not attachments:
            return base
        lines: list[str] = []
        if base:
            lines.extend([base, ""])
        lines.append(
            self._polite_copy(
                zh="系统提示：用户刚刚发送了附件。请优先阅读这些 quest 本地文件，再继续处理这条请求：",
                en="System note: the user just sent attachments. Read these quest-local files first before continuing this request:",
            )
        )
        for index, item in enumerate(attachments, start=1):
            label = str(
                item.get("name")
                or item.get("quest_relative_path")
                or item.get("path")
                or item.get("url")
                or f"attachment-{index}"
            ).strip()
            content_type = str(item.get("content_type") or "").strip()
            location = str(item.get("path") or item.get("url") or "unavailable").strip()
            error = str(item.get("download_error") or "").strip()
            suffix = f" ({content_type})" if content_type else ""
            if error:
                lines.append(f"- {label}{suffix}: {location} | download_error={error}")
            else:
                lines.append(f"- {label}{suffix}: {location}")
        return "\n".join(lines).strip()

    def _materialize_connector_attachments(
        self,
        *,
        quest_id: str,
        connector_name: str,
        conversation_id: str,
        message_id: str | None,
        attachments: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not attachments:
            return []
        quest_root = self.home / "quests" / quest_id
        batch_slug = slugify(message_id or generate_id("userfile"), default=generate_id("userfile"))
        batch_root = ensure_dir(quest_root / "userfiles" / connector_name / batch_slug)
        materialized: list[dict[str, object]] = []
        for index, raw_item in enumerate(attachments, start=1):
            materialized.append(
                self._materialize_single_connector_attachment(
                    connector_name=connector_name,
                    quest_root=quest_root,
                    batch_root=batch_root,
                    index=index,
                    attachment=dict(raw_item),
                )
            )
        write_json(
            batch_root / "manifest.json",
            {
                "connector": connector_name,
                "quest_id": quest_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "materialized_at": utc_now(),
                "attachments": materialized,
            },
        )
        return materialized

    def _materialize_single_connector_attachment(
        self,
        *,
        connector_name: str,
        quest_root: Path,
        batch_root: Path,
        index: int,
        attachment: dict[str, object],
    ) -> dict[str, object]:
        resolved = dict(attachment)
        name = str(resolved.get("name") or "").strip()
        content_type = str(resolved.get("content_type") or "").strip()
        url = str(resolved.get("url") or "").strip()
        target_path = batch_root / self._connector_attachment_filename(index=index, name=name, content_type=content_type)
        resolved["manifest_path"] = str(batch_root / "manifest.json")
        resolved["batch_path"] = str(batch_root)
        if not url:
            resolved["materialized"] = False
            resolved["download_error"] = "missing_download_url"
            return resolved
        try:
            size_bytes = self._download_connector_attachment(
                connector_name=connector_name,
                url=url,
                target_path=target_path,
            )
            resolved["path"] = str(target_path)
            resolved["quest_relative_path"] = str(target_path.relative_to(quest_root))
            resolved["size_bytes"] = int(size_bytes)
            resolved["materialized"] = True
            resolved["downloaded_at"] = utc_now()
            return resolved
        except Exception as exc:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            resolved["materialized"] = False
            resolved["download_error"] = str(exc)
            return resolved

    def _download_connector_attachment(
        self,
        *,
        connector_name: str,
        url: str,
        target_path: Path,
    ) -> int:
        request = Request(url)
        for key, value in self._connector_attachment_headers(connector_name).items():
            request.add_header(key, value)
        ensure_dir(target_path.parent)
        total = 0
        with urlopen(request, timeout=20) as response:  # noqa: S310
            with target_path.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self._MAX_INBOUND_ATTACHMENT_BYTES:
                        raise ValueError(
                            f"attachment exceeds max inbound size limit ({self._MAX_INBOUND_ATTACHMENT_BYTES} bytes)"
                        )
                    handle.write(chunk)
        return total

    def _connector_attachment_headers(self, connector_name: str) -> dict[str, str]:
        if str(connector_name or "").strip().lower() != "qq":
            return {}
        config = self.connectors_config.get("qq", {})
        if not isinstance(config, dict):
            return {}
        app_id = str(config.get("app_id") or "").strip()
        app_secret = QQConnectorBridge.read_secret(config, "app_secret", "app_secret_env")
        if not app_id or not app_secret:
            return {}
        return {
            "Authorization": f"QQBot {QQConnectorBridge._access_token(app_id, app_secret)}",
        }

    @staticmethod
    def _connector_attachment_filename(*, index: int, name: str, content_type: str) -> str:
        raw_name = str(name or "").strip()
        suffix = Path(raw_name).suffix if raw_name else ""
        if not suffix and content_type:
            suffix = mimetypes.guess_extension(content_type, strict=False) or ""
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        stem_source = Path(raw_name).stem if raw_name else f"attachment-{index:03d}"
        stem = slugify(stem_source, default=f"attachment-{index:03d}")
        return f"{stem}{suffix or '.bin'}"

    def _qq_channel(self) -> QQRelayChannel:
        return self.channels["qq"]  # type: ignore[return-value]

    def _auto_bind_connectors_to_latest_quest(
        self,
        quest_id: str,
        *,
        goal: str,
        source: str,
        announce: bool,
        exclude_conversation_id: str | None = None,
    ) -> list[str]:
        candidates: list[tuple[str, str]] = []
        for connector_name, channel in self.channels.items():
            if connector_name == "local":
                continue
            connector_config = self.connectors_config.get(connector_name, {})
            if not isinstance(connector_config, dict):
                continue
            if not connector_config.get("enabled", False):
                continue
            if not connector_config.get("auto_bind_dm_to_active_quest", False):
                continue
            for conversation_id in self._latest_connector_conversation_ids(connector_name):
                if not conversation_id or conversation_id == exclude_conversation_id:
                    continue
                candidates.append((connector_name, conversation_id))

        if not candidates:
            return []

        bound_conversations: list[str] = []
        seen_identity_keys: set[str] = set()
        for connector_name, conversation_id in candidates:
            original_identity = conversation_identity_key(conversation_id)
            if original_identity in seen_identity_keys:
                continue
            result = self._apply_conversation_binding(quest_id, conversation_id, force=True, clear_scope="none")
            if isinstance(result, tuple):
                continue
            bound_conversation = str(result.get("conversation_id") or "").strip() or conversation_id
            identity_key = conversation_identity_key(bound_conversation)
            if identity_key in seen_identity_keys:
                continue
            seen_identity_keys.add(identity_key)
            bound_conversations.append(bound_conversation)
            if announce:
                channel = self._channel_with_bindings(connector_name)
                channel.send(
                    {
                        "conversation_id": bound_conversation,
                        "quest_id": quest_id,
                        "kind": "ack",
                        "message": self._quest_created_connector_message(
                            connector_name,
                            quest_id=quest_id,
                            goal=goal,
                            previous_quest_id=str(result.get("previous_quest_id") or "").strip() or None,
                        ),
                    }
                )
        return bound_conversations

    def _latest_connector_conversation_id(self, connector_name: str) -> str:
        candidates = self._latest_connector_conversation_ids(connector_name)
        return candidates[0] if candidates else ""

    def _latest_connector_conversation_ids(self, connector_name: str) -> list[str]:
        conversation_ids: list[str] = []
        if connector_name == "qq":
            qq_config = self.connectors_config.get("qq", {})
            if isinstance(qq_config, dict):
                profiles = list_qq_profiles(qq_config)
                encode_profile_id = len(profiles) > 1
                for profile in profiles:
                    main_chat_id = str(profile.get("main_chat_id") or "").strip()
                    profile_id = str(profile.get("profile_id") or "").strip()
                    if main_chat_id:
                        conversation_ids.append(
                            format_conversation_id(
                                "qq",
                                "direct",
                                main_chat_id,
                                profile_id=profile_id if encode_profile_id else None,
                            )
                        )
        elif connector_name in PROFILEABLE_CONNECTOR_NAMES:
            connector_config = self.connectors_config.get(connector_name, {})
            if isinstance(connector_config, dict):
                for profile in list_connector_profiles(connector_name, connector_config):
                    profile_id = str(profile.get("profile_id") or "").strip()
                    if not profile_id:
                        continue
                    runtime_state = read_json(
                        self.home / "logs" / "connectors" / connector_name / "profiles" / profile_id / "runtime.json",
                        {},
                    )
                    if isinstance(runtime_state, dict):
                        runtime_last_conversation_id = str(runtime_state.get("last_conversation_id") or "").strip()
                        if runtime_last_conversation_id:
                            conversation_ids.append(runtime_last_conversation_id)
        state_path = self.home / "logs" / "connectors" / connector_name / "state.json"
        state = read_json(state_path, {})
        if isinstance(state, dict):
            last_conversation_id = str(state.get("last_conversation_id") or "").strip()
            if last_conversation_id:
                conversation_ids.append(last_conversation_id)
            for item in state.get("recent_conversations") or []:
                if not isinstance(item, dict):
                    continue
                conversation_id = str(item.get("conversation_id") or "").strip()
                if conversation_id:
                    conversation_ids.append(conversation_id)
        runtime_state = read_json(self.home / "logs" / "connectors" / connector_name / "runtime.json", {})
        if isinstance(runtime_state, dict):
            runtime_last_conversation_id = str(runtime_state.get("last_conversation_id") or "").strip()
            if runtime_last_conversation_id:
                conversation_ids.append(runtime_last_conversation_id)
        try:
            channel = self._channel_with_bindings(connector_name)
            for item in channel.list_bindings():
                conversation_id = str(item.get("conversation_id") or "").strip()
                if conversation_id:
                    conversation_ids.append(conversation_id)
        except Exception:
            pass
        ordered: list[str] = []
        seen: set[str] = set()
        for conversation_id in conversation_ids:
            identity = conversation_identity_key(conversation_id)
            if not conversation_id or identity in seen:
                continue
            seen.add(identity)
            ordered.append(conversation_id)
        return ordered

    def _latest_quest_id(self) -> str | None:
        quests = self.quest_service.list_quests()
        if not quests:
            return None
        quest_id = str(quests[0].get("quest_id") or "").strip()
        return quest_id or None

    def _quest_exists(self, quest_id: str | None) -> bool:
        normalized = str(quest_id or "").strip()
        if not normalized:
            return False
        return (self.home / "quests" / normalized / "quest.yaml").exists()

    def _resolve_quest_reference(self, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if normalized in {"latest", "newest"}:
            return self._latest_quest_id()
        return normalized

    def _connector_control_reply(
        self,
        connector_name: str,
        *,
        conversation_id: str,
        quest_id: str,
        action: str,
        result: dict[str, Any],
        deliver_directly: bool,
    ) -> dict:
        channel = self._channel_with_bindings(connector_name)
        snapshot = result.get("snapshot") or {}
        event = result.get("event") or {}
        payload = {
            "conversation_id": conversation_id,
            "quest_id": quest_id,
            "kind": "progress",
            "message": str((result.get("notice") or {}).get("message") or result.get("message") or "").strip(),
            "response_phase": "control",
            "importance": "warning" if action in {"pause", "stop"} else "info",
            "attachments": [
                {
                    "kind": "quest_control",
                    "action": action,
                    "status": snapshot.get("status"),
                    "source": event.get("source"),
                    "branch": snapshot.get("branch"),
                    "workspace_root": snapshot.get("current_workspace_root") or snapshot.get("quest_root"),
                    "interrupted": bool(result.get("interrupted")),
                    "cancelled_pending_user_message_count": int(
                        result.get("cancelled_pending_user_message_count") or 0
                    ),
                    "stop_reason": snapshot.get("stop_reason"),
                }
            ],
        }
        if deliver_directly:
            return channel.send(payload)
        formatted = channel._format_outbound(payload) if hasattr(channel, "_format_outbound") else payload
        return {
            "ok": True,
            "queued": False,
            "channel": connector_name,
            "payload": formatted,
            "delivery": {
                "ok": True,
                "queued": False,
                "transport": f"{connector_name}-control",
            },
        }

    def _maybe_auto_bind_connector_conversation(self, connector_name: str, conversation_id: str) -> dict | None:
        connector_config = self.connectors_config.get(connector_name, {})
        if not isinstance(connector_config, dict):
            return None
        if not connector_config.get("enabled", False):
            return None
        if not connector_config.get("auto_bind_dm_to_active_quest", False):
            return None
        latest_quest_id = self._latest_quest_id()
        if latest_quest_id is None:
            return None
        result = self.update_quest_binding(latest_quest_id, conversation_id, force=True)
        if isinstance(result, tuple):
            return None
        return result

    def _connector_home_help(self, connector_name: str, *, message: dict) -> str:
        quests = self.quest_service.list_quests()
        latest = str(quests[0]["quest_id"]) if quests else "none"
        body = self._polite_copy(
            zh=(
                "当前这个 connector 会话还没有绑定 quest。\n"
                "在创建或绑定 quest 之前，仅支持以下关键字：\n"
                "- `/help`：查看帮助\n"
                f"- `/projects` 或 `/list`：查看最近的 quest（当前最新：`{latest}`）\n"
                "- `/use <quest_id>`：绑定指定 quest\n"
                "- `/use latest`：直接绑定当前最新 quest\n"
                "- `/new <goal>`：新建一个 quest 并自动绑定当前会话\n"
                "- `/stop [quest_id|latest]`：停止当前或指定 quest\n"
                "- `/resume [quest_id|latest]`：恢复当前或指定 quest\n"
                "- `/delete <quest_id> --yes`：删除指定 quest（危险操作，需要确认）\n"
                "如果当前已经存在最新 quest，除上述 home 命令外的普通文本或工作命令会自动绑定到最新 quest 并继续执行；如果当前还没有任何 quest，普通文本会先返回这份帮助。"
            ),
            en=(
                "This connector conversation is not bound to any quest yet.\n"
                "Before a quest is created or selected, only these commands are available:\n"
                "- `/help`: show help\n"
                f"- `/projects` or `/list`: list recent quests (latest: `{latest}`)\n"
                "- `/use <quest_id>`: bind a specific quest\n"
                "- `/use latest`: bind the latest quest\n"
                "- `/new <goal>`: create a new quest and bind this conversation\n"
                "- `/stop [quest_id|latest]`: stop the current or selected quest\n"
                "- `/resume [quest_id|latest]`: resume the current or selected quest\n"
                "- `/delete <quest_id> --yes`: delete a quest (destructive; requires confirmation)\n"
                "If a latest quest already exists, plain text or quest commands will auto-bind this conversation to it; if no quest exists yet, plain text will return this help instead of going to the agent."
            ),
        )
        return self._with_qq_main_chat_notice(message, body)

    def _unbind_external_bindings(self, quest_id: str, *, preserve: set[str] | None = None) -> list[str]:
        preserve_keys = {conversation_identity_key(item) for item in (preserve or set()) if item}
        removed: list[str] = []
        for connector_name in sorted(self.channels.keys()):
            if connector_name == "local":
                continue
            try:
                channel = self._channel_with_bindings(connector_name)
            except Exception:
                continue
            for item in channel.list_bindings():
                if str(item.get("quest_id") or "").strip() != quest_id:
                    continue
                conversation_id = str(item.get("conversation_id") or "").strip()
                if not conversation_id:
                    continue
                if preserve_keys and conversation_identity_key(conversation_id) in preserve_keys:
                    continue
                if channel.unbind_conversation(conversation_id, quest_id=quest_id):
                    removed.append(conversation_id)
                    self.sessions.unbind(quest_id, conversation_id)
        for conversation_id in removed:
            self.quest_service.unbind_source(quest_id, conversation_id)
        return removed

    def _format_projects_list(self) -> str:
        quests = self.quest_service.list_quests()
        if not quests:
            return self._polite_copy(
                zh="当前还没有 quest。可以发送 `/new <goal>` 来创建一个新的 quest。",
                en="There is no quest yet. Use `/new <goal>` to create one.",
            )
        lines = [
            self._polite_copy(
                zh="最近的 quest 如下：",
                en="Recent quests:",
            )
        ]
        for item in quests[:6]:
            lines.append(
                f"- `{item['quest_id']}` · {item.get('title') or item['quest_id']} · {item.get('status') or 'active'}"
            )
        lines.append(
            self._polite_copy(
                zh="发送 `/use <quest_id>`、`/use latest`、`/projects` 或 `/list` 可以继续。",
                en="Use `/use <quest_id>`, `/use latest`, `/projects`, or `/list` to continue.",
            )
        )
        return "\n".join(lines)

    def _channel_with_bindings(self, name: str):
        channel = self.channels.get(name)
        if channel is None:
            raise KeyError(f"Unknown connector `{name}`.")
        for attr in (
            "ingest",
            "bind_conversation",
            "unbind_conversation",
            "resolve_bound_quest",
            "list_bindings",
            "command_prefix",
        ):
            if not hasattr(channel, attr):
                raise TypeError(f"Connector `{name}` does not implement `{attr}`.")
        return channel

    @staticmethod
    def _connector_label(name: str) -> str:
        normalized = (name or "").strip().lower()
        if normalized == "qq":
            return "QQ"
        if normalized == "feishu":
            return "Feishu"
        if normalized == "whatsapp":
            return "WhatsApp"
        return normalized.title() or "Connector"

    @staticmethod
    def _parse_prefixed_command(text: str, prefix: str) -> tuple[str, list[str]]:
        stripped = text[len(prefix):].strip()
        if not stripped:
            return "", []
        parts = stripped.split()
        return parts[0].lower(), parts[1:]

    def _maybe_bind_qq_main_chat(self, message: dict) -> dict | None:
        chat_type = str(message.get("chat_type") or "").strip().lower()
        if chat_type != "direct":
            return None
        profile_id = str(message.get("profile_id") or "").strip() or None
        chat_id = str(message.get("chat_id") or message.get("direct_id") or "").strip()
        if not chat_id:
            parsed = parse_conversation_id(message.get("conversation_id"))
            if parsed is not None and str(parsed.get("connector") or "").strip().lower() == "qq":
                chat_id = str(parsed.get("chat_id") or "").strip()
                profile_id = str(parsed.get("profile_id") or "").strip() or profile_id
        if not chat_id:
            return None
        result = self.config_manager.bind_qq_main_chat(profile_id=profile_id, chat_id=chat_id)
        if not result.get("ok"):
            self.logger.log(
                "warning",
                "connector.qq_main_chat_bind_failed",
                chat_id=chat_id,
                profile_id=profile_id,
                errors=result.get("errors") or [],
            )
            return None
        if not result.get("saved"):
            return None
        self.reload_connectors_config(restart_background=False)
        return {
            "chat_id": chat_id,
            "profile_id": result.get("profile_id"),
            "profile_label": result.get("profile_label"),
            "saved_at": result.get("saved_at"),
        }

    def _with_qq_main_chat_notice(self, message: dict, base: str) -> str:
        binding = message.get("_qq_main_chat_binding")
        if not isinstance(binding, dict):
            return base
        chat_id = str(binding.get("chat_id") or "").strip()
        if not chat_id:
            return base
        profile_label = str(binding.get("profile_label") or "").strip()
        notice = self._polite_copy(
            zh=(
                f"已自动检测并保存当前 QQ openid：`{chat_id}`。"
                f"{f'当前 bot：{profile_label}。' if profile_label else ''}您现在可以在 settings 页面看到这个绑定结果。"
            ),
            en=(
                f"I automatically detected and saved this QQ openid: `{chat_id}`. "
                f"{f'Current bot: {profile_label}. ' if profile_label else ''}"
                "You can now see the binding in settings."
            ),
        )
        return f"{notice}\n\n{base}"

    def _quest_created_connector_message(
        self,
        connector_name: str,
        *,
        quest_id: str,
        goal: str,
        previous_quest_id: str | None = None,
    ) -> str:
        normalized_goal = str(goal or "").strip() or "（未提供具体任务）"
        previous = str(previous_quest_id or "").strip()
        restore_zh = (
            f"\n如果需要恢复到原先绑定的 quest，请发送：`/use {previous}`。"
            if previous and previous != quest_id
            else ""
        )
        restore_en = (
            f"\nIf you need to switch back to the previously bound quest, send: `/use {previous}`."
            if previous and previous != quest_id
            else ""
        )
        return self._polite_copy(
            zh=(
                f"老师，已顺利创建新的 quest `{quest_id}`。\n"
                f"我即将为您完成以下任务：{normalized_goal}\n"
                f"当前 {self._connector_label(connector_name)} 会话接下来会自动使用这个新 quest 保持连接。\n"
            )
            + restore_zh,
            en=(
                f"Created a new quest `{quest_id}` successfully.\n"
                f"I am about to work on: {normalized_goal}\n"
                f"This {self._connector_label(connector_name)} conversation will now stay attached to the new quest automatically.\n"
            )
            + restore_en,
        )

    def _profiled_connector_configs(self, connector_name: str) -> list[tuple[str, str | None, dict[str, Any]]]:
        connector_config = self.connectors_config.get(connector_name, {})
        if not isinstance(connector_config, dict):
            return []
        profiles = list_connector_profiles(connector_name, connector_config)
        encode_profile_id = len(profiles) > 1
        items: list[tuple[str, str | None, dict[str, Any]]] = []
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if not profile_id:
                continue
            merged = merge_connector_profile_config(connector_name, connector_config, profile)
            merged["encode_profile_id"] = encode_profile_id
            items.append((profile_id, connector_profile_label(connector_name, profile), merged))
        return items

    def _start_background_connectors(self) -> None:
        qq_config = self.connectors_config.get("qq", {})
        if isinstance(qq_config, dict) and not self._qq_gateways:
            profiles = list_qq_profiles(qq_config)
            encode_profile_id = len(profiles) > 1
            for profile in profiles:
                profile_id = str(profile.get("profile_id") or "").strip()
                profile_config = merge_qq_profile_config(qq_config, profile)
                profile_config["encode_profile_id"] = encode_profile_id
                gateway = QQGatewayService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("qq", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.qq_gateway",
                        profile_id=_profile_id,
                        message=message,
                    ),
                )
                if gateway.start():
                    self._qq_gateways[profile_id] = gateway
        if not self._telegram_polling:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("telegram"):
                polling = TelegramPollingService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("telegram", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.telegram_polling",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if polling.start():
                    self._telegram_polling[profile_id] = polling
        if not self._slack_socket:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("slack"):
                slack = SlackSocketModeService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("slack", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.slack_socket",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if slack.start():
                    self._slack_socket[profile_id] = slack
        if not self._discord_gateway:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("discord"):
                discord = DiscordGatewayService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("discord", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.discord_gateway",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if discord.start():
                    self._discord_gateway[profile_id] = discord
        if not self._feishu_long_connection:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("feishu"):
                feishu = FeishuLongConnectionService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("feishu", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.feishu_long_connection",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if feishu.start():
                    self._feishu_long_connection[profile_id] = feishu
        if not self._whatsapp_local_session:
            for profile_id, profile_label, profile_config in self._profiled_connector_configs("whatsapp"):
                whatsapp = WhatsAppLocalSessionService(
                    home=self.home,
                    config=profile_config,
                    on_event=lambda event: self.handle_connector_inbound("whatsapp", event),
                    log=lambda level, message, _profile_id=profile_id: self.logger.log(
                        level,
                        "connector.whatsapp_local_session",
                        profile_id=_profile_id,
                        message=message,
                    ),
                    profile_id=profile_id,
                    profile_label=profile_label,
                    encode_profile_id=bool(profile_config.get("encode_profile_id")),
                )
                if whatsapp.start():
                    self._whatsapp_local_session[profile_id] = whatsapp

    def _stop_background_connectors(self) -> None:
        gateways = list(self._qq_gateways.values())
        self._qq_gateways = {}
        for gateway in gateways:
            gateway.stop()
        polling = list(self._telegram_polling.values())
        self._telegram_polling = {}
        for item in polling:
            item.stop()
        slack = list(self._slack_socket.values())
        self._slack_socket = {}
        for item in slack:
            item.stop()
        discord = list(self._discord_gateway.values())
        self._discord_gateway = {}
        for item in discord:
            item.stop()
        feishu = list(self._feishu_long_connection.values())
        self._feishu_long_connection = {}
        for item in feishu:
            item.stop()
        whatsapp = list(self._whatsapp_local_session.values())
        self._whatsapp_local_session = {}
        for item in whatsapp:
            item.stop()

    @staticmethod
    def _format_status(snapshot: dict) -> str:
        latest_metric = (snapshot.get("summary") or {}).get("latest_metric")
        pending = snapshot.get("pending_decisions") or []
        counts = snapshot.get("counts") or {}
        bound_conversations = snapshot.get("bound_conversations") or []
        lines = [
            f"Quest {snapshot.get('quest_id')}",
            "Quest Status",
            f"- quest_id: {snapshot.get('quest_id')}",
            f"- title: {snapshot.get('title')}",
            f"- status: {snapshot.get('status')}",
            f"- anchor: {snapshot.get('active_anchor')}",
            f"- runner: {snapshot.get('runner')}",
            f"- branch: {snapshot.get('branch')}",
            f"- active_run_id: {snapshot.get('active_run_id') or 'none'}",
            f"- quest_root: {snapshot.get('quest_root')}",
            f"- updated_at: {snapshot.get('updated_at')}",
            f"- history_count: {snapshot.get('history_count')}",
            f"- artifact_count: {snapshot.get('artifact_count')}",
            f"- memory_cards: {counts.get('memory_cards', 0)}",
            f"- pending_decisions: {len(pending)}",
            f"- bound_conversations: {', '.join(str(item) for item in bound_conversations) if bound_conversations else 'none'}",
        ]
        status_line = ((snapshot.get("summary") or {}).get("status_line") or "").strip()
        if status_line:
            lines.append(f"- summary: {status_line}")
        if isinstance(latest_metric, dict) and latest_metric.get("key"):
            lines.append(f"- latest_metric: {latest_metric.get('key')} = {latest_metric.get('value')}")
        if pending:
            lines.append(f"- pending_decision_ids: {', '.join(str(item) for item in pending[:8])}")
        return "\n".join(lines)

    def _format_summary(self, quest_id: str) -> str:
        snapshot = self.quest_service.snapshot(quest_id)
        title = str(snapshot.get("title") or "").strip()
        status = str(snapshot.get("runtime_status") or snapshot.get("status") or "").strip()
        summary = read_text(self.home / "quests" / quest_id / "SUMMARY.md").strip()
        header_lines = [f"quest_id: {quest_id}"]
        if title and title != quest_id:
            header_lines.append(f"title: {title}")
        if status:
            header_lines.append(f"status: {status}")
        if not summary:
            header_lines.append("summary: No summary has been written yet.")
            return "\n".join(header_lines)
        header = "\n".join(header_lines)
        remaining = max(0, 1800 - len(header) - 2)
        return f"{header}\n\n{summary[:remaining]}"

    def _format_metrics(self, quest_id: str, *, run_id: str | None = None) -> str:
        quest_root = self.home / "quests" / quest_id
        run_paths = sorted((quest_root / "artifacts" / "runs").glob("*.json"))
        if not run_paths:
            snapshot = self.quest_service.snapshot(quest_id)
            latest_metric = (snapshot.get("summary") or {}).get("latest_metric")
            if isinstance(latest_metric, dict) and latest_metric.get("key"):
                return f"{latest_metric.get('key')} = {latest_metric.get('value')}"
            return "No metrics are available yet."
        matches = []
        for path in run_paths:
            payload = read_json(path, {})
            if run_id and payload.get("run_id") != run_id:
                continue
            matches.append(payload)
        if not matches:
            return f"No run metrics found for `{run_id}`."
        latest = matches[-1]
        metrics = latest.get("metrics") or latest.get("metrics_summary") or {}
        if isinstance(metrics, dict) and metrics:
            compact = ", ".join(f"{key}={value}" for key, value in list(metrics.items())[:6])
            return f"{latest.get('run_id') or latest.get('artifact_id')}: {compact}"
        summary = str(latest.get("summary") or "No structured metrics were recorded.")
        return f"{latest.get('run_id') or latest.get('artifact_id')}: {summary}"

    @staticmethod
    def _format_graph_reply(quest_id: str, graph: dict) -> str:
        branch = graph.get("branch")
        head = graph.get("head")
        lines = graph.get("lines") or []
        return (
            f"Git graph refreshed for {quest_id}.\n"
            f"Branch: {branch}\n"
            f"Head: {head}\n"
            f"Recent commits: {min(len(lines), 8)} shown in the attached graph."
        )

    def _wants_event_stream(self, path: str, headers: dict[str, str]) -> bool:
        query = self.handlers.parse_query(path)
        stream_value = ((query.get("stream") or [""])[0] or "").strip().lower()
        accept = str(headers.get("Accept") or headers.get("accept") or "").lower()
        return stream_value in {"1", "true", "yes", "stream"} or "text/event-stream" in accept

    @staticmethod
    def _write_sse_event(
        handler: BaseHTTPRequestHandler,
        *,
        event: str,
        data: dict,
        event_id: str | None = None,
    ) -> None:
        if event_id:
            handler.wfile.write(f"id: {event_id}\n".encode("utf-8"))
        handler.wfile.write(f"event: {event}\n".encode("utf-8"))
        rendered = json.dumps(data, ensure_ascii=False)
        for line in rendered.splitlines() or ["{}"]:
            handler.wfile.write(f"data: {line}\n".encode("utf-8"))
        handler.wfile.write(b"\n")
        handler.wfile.flush()

    @staticmethod
    def _parse_bash_log_jsonl_line(raw_line: bytes) -> dict[str, Any] | None:
        stripped = raw_line.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @classmethod
    def _read_bash_log_delta(
        cls,
        log_path: Path,
        *,
        offset: int,
        pending: bytes,
        min_seq: int,
    ) -> tuple[list[dict[str, Any]], int, bytes]:
        if not log_path.exists():
            return [], 0, pending

        current_size = log_path.stat().st_size
        safe_offset = max(0, min(offset, current_size))
        with log_path.open("rb") as handle:
            handle.seek(safe_offset)
            chunk = handle.read()
            next_offset = handle.tell()

        if not chunk:
            return [], next_offset, pending

        payload = pending + chunk
        lines = payload.split(b"\n")
        remainder = b""
        if payload and not payload.endswith(b"\n"):
            remainder = lines.pop()

        fresh_entries: list[dict[str, Any]] = []
        for raw_line in lines:
            entry = cls._parse_bash_log_jsonl_line(raw_line.rstrip(b"\r"))
            if not entry:
                continue
            try:
                seq = int(entry.get("seq") or 0)
            except (TypeError, ValueError):
                seq = 0
            if seq <= min_seq:
                continue
            fresh_entries.append(entry)

        return fresh_entries, next_offset, remainder

    def stream_quest_events(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        path: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        query = self.handlers.parse_query(path)
        after = int((query.get("after") or ["0"])[0] or "0")
        limit = max(1, min(int((query.get("limit") or ["200"])[0] or "200"), 200))
        format_name = ((query.get("format") or ["acp"])[0] or "acp").lower()
        session_id = ((query.get("session_id") or [f"quest:{quest_id}"])[0] or f"quest:{quest_id}")
        last_event_id = str((headers or {}).get("Last-Event-ID") or (headers or {}).get("last-event-id") or "").strip()
        current_cursor = max(after, int(last_event_id)) if last_event_id.isdigit() else after
        heartbeat_at = time.monotonic()
        idle_sleep_seconds = 0.35

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        try:
            while True:
                stream_path = f"/api/quests/{quest_id}/events?{urlencode({'after': current_cursor, 'limit': limit, 'format': format_name, 'session_id': session_id})}"
                payload = self.handlers.quest_events(quest_id, path=stream_path)
                updates = payload.get("acp_updates") or []
                if updates:
                    for update in updates:
                        update_cursor = str(((update.get("params") or {}).get("update") or {}).get("cursor") or "")
                        self._write_sse_event(
                            handler,
                            event="acp_update",
                            data=update,
                            event_id=update_cursor or None,
                        )
                    current_cursor = int(payload.get("cursor") or current_cursor)
                    self._write_sse_event(
                        handler,
                        event="cursor",
                        data={"cursor": current_cursor, "quest_id": quest_id},
                    )
                    heartbeat_at = time.monotonic()
                    idle_sleep_seconds = 0.2
                else:
                    now = time.monotonic()
                    if now - heartbeat_at >= 10:
                        handler.wfile.write(b": keep-alive\n\n")
                        handler.wfile.flush()
                        heartbeat_at = now
                    idle_sleep_seconds = min(1.5, idle_sleep_seconds * 1.35)
                time.sleep(idle_sleep_seconds)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def stream_bash_sessions(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        path: str,
    ) -> None:
        quest_root = self.quest_service._quest_root(quest_id)
        query = self.handlers.parse_query(path)
        status = ((query.get("status") or [""])[0] or "").strip() or None
        limit_raw = ((query.get("limit") or ["200"])[0] or "200").strip()
        chat_session_id = ((query.get("chat_session_id") or [""])[0] or "").strip() or None
        try:
            limit = max(1, min(int(limit_raw), 500))
        except ValueError:
            limit = 200
        agent_ids = [
            item.strip()
            for item in (((query.get("agent_ids") or [""])[0] or "").split(","))
            if item.strip()
        ]
        agent_instance_ids = [
            item.strip()
            for item in (((query.get("agent_instance_ids") or [""])[0] or "").split(","))
            if item.strip()
        ]

        def list_payload() -> list[dict[str, object]]:
            return self.bash_exec_service.list_sessions(
                quest_root,
                status=status,
                agent_ids=agent_ids or None,
                agent_instance_ids=agent_instance_ids or None,
                chat_session_id=chat_session_id,
                limit=limit,
            )

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        previous_snapshot: dict[str, dict[str, object]] = {}
        heartbeat_at = time.monotonic()
        try:
            while True:
                sessions = list_payload()
                current_snapshot = {
                    str(item.get("bash_id") or ""): item
                    for item in sessions
                    if item.get("bash_id")
                }
                if not previous_snapshot:
                    self._write_sse_event(
                        handler,
                        event="snapshot",
                        data={"sessions": sessions},
                    )
                    previous_snapshot = current_snapshot
                    heartbeat_at = time.monotonic()
                else:
                    changed = [
                        session
                        for bash_id, session in current_snapshot.items()
                        if previous_snapshot.get(bash_id) != session
                    ]
                    removed = set(previous_snapshot) - set(current_snapshot)
                    for session in changed:
                        self._write_sse_event(
                            handler,
                            event="session",
                            data={"session": session},
                        )
                    for bash_id in removed:
                        self._write_sse_event(
                            handler,
                            event="session",
                            data={"session": {"bash_id": bash_id, "status": "terminated"}},
                        )
                    if changed or removed:
                        previous_snapshot = current_snapshot
                        heartbeat_at = time.monotonic()
                    elif time.monotonic() - heartbeat_at >= 10:
                        handler.wfile.write(b": keep-alive\n\n")
                        handler.wfile.flush()
                        heartbeat_at = time.monotonic()
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def stream_bash_logs(
        self,
        handler: BaseHTTPRequestHandler,
        *,
        quest_id: str,
        bash_id: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        quest_root = self.quest_service._quest_root(quest_id)
        last_event_raw = str((headers or {}).get("Last-Event-ID") or (headers or {}).get("last-event-id") or "").strip()
        last_event_id = int(last_event_raw) if last_event_raw.isdigit() else None

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        handler.wfile.write(b"retry: 1000\n\n")
        handler.wfile.flush()

        previous_progress = None
        previous_status = None
        previous_exit_code = None
        cursor = last_event_id or 0
        initialized = False
        heartbeat_at = time.monotonic()
        log_path = self.bash_exec_service.log_path(quest_root, bash_id)
        log_offset = 0
        pending_bytes = b""
        try:
            while True:
                session = self.bash_exec_service.get_session(quest_root, bash_id)
                latest_status = str(session.get("status") or "")
                latest_exit_code = session.get("exit_code")

                if not initialized:
                    if last_event_id is None:
                        entries, meta = self.bash_exec_service.read_log_entries(
                            quest_root,
                            bash_id,
                            limit=200,
                            before_seq=None,
                            order="asc",
                        )
                        latest_seq = int(meta.get("latest_seq") or 0)
                        self._write_sse_event(
                            handler,
                            event="snapshot",
                            event_id=str(latest_seq) if latest_seq else None,
                            data={
                                "bash_id": bash_id,
                                "tail_limit": meta.get("tail_limit"),
                                "tail_start_seq": meta.get("tail_start_seq"),
                                "latest_seq": meta.get("latest_seq"),
                                "lines": [
                                    {
                                        "seq": entry.get("seq"),
                                        "stream": entry.get("stream"),
                                        "line": entry.get("line"),
                                        "timestamp": entry.get("timestamp"),
                                    }
                                    for entry in entries
                                ],
                                "progress": session.get("last_progress"),
                            },
                        )
                        cursor = latest_seq
                        heartbeat_at = time.monotonic()

                    fresh_entries, log_offset, pending_bytes = self._read_bash_log_delta(
                        log_path,
                        offset=0,
                        pending=b"",
                        min_seq=cursor,
                    )
                    for entry in fresh_entries:
                        cursor = int(entry.get("seq") or cursor)
                        self._write_sse_event(
                            handler,
                            event="log",
                            event_id=str(cursor),
                            data={
                                "bash_id": bash_id,
                                "seq": entry.get("seq"),
                                "stream": entry.get("stream"),
                                "line": entry.get("line"),
                                "timestamp": entry.get("timestamp"),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    previous_progress = session.get("last_progress")
                    previous_status = latest_status
                    previous_exit_code = latest_exit_code
                    initialized = True

                    if latest_status in {"completed", "failed", "terminated"}:
                        self._write_sse_event(
                            handler,
                            event="done",
                            data={
                                "bash_id": bash_id,
                                "status": latest_status,
                                "exit_code": latest_exit_code,
                                "finished_at": session.get("finished_at"),
                            },
                        )
                        return
                else:
                    if log_path.exists() and log_path.stat().st_size < log_offset:
                        self._write_sse_event(
                            handler,
                            event="gap",
                            data={
                                "bash_id": bash_id,
                                "from_seq": cursor or None,
                                "to_seq": None,
                                "tail_limit": 200,
                            },
                        )
                        log_offset = 0
                        pending_bytes = b""
                        heartbeat_at = time.monotonic()

                    fresh_entries, log_offset, pending_bytes = self._read_bash_log_delta(
                        log_path,
                        offset=log_offset,
                        pending=pending_bytes,
                        min_seq=cursor,
                    )
                    for entry in fresh_entries:
                        cursor = int(entry.get("seq") or cursor)
                        self._write_sse_event(
                            handler,
                            event="log",
                            event_id=str(cursor),
                            data={
                                "bash_id": bash_id,
                                "seq": entry.get("seq"),
                                "stream": entry.get("stream"),
                                "line": entry.get("line"),
                                "timestamp": entry.get("timestamp"),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    if session.get("last_progress") != previous_progress and session.get("last_progress") is not None:
                        previous_progress = session.get("last_progress")
                        self._write_sse_event(
                            handler,
                            event="progress",
                            data={
                                "bash_id": bash_id,
                                **dict(session.get("last_progress") or {}),
                            },
                        )
                        heartbeat_at = time.monotonic()

                    if latest_status in {"completed", "failed", "terminated"} and (
                        latest_status != previous_status or latest_exit_code != previous_exit_code
                    ):
                        previous_status = latest_status
                        previous_exit_code = latest_exit_code
                        self._write_sse_event(
                            handler,
                            event="done",
                            data={
                                "bash_id": bash_id,
                                "status": latest_status,
                                "exit_code": latest_exit_code,
                                "finished_at": session.get("finished_at"),
                            },
                        )
                        heartbeat_at = time.monotonic()
                        return

                    previous_status = latest_status
                    previous_exit_code = latest_exit_code

                    if time.monotonic() - heartbeat_at >= 10:
                        handler.wfile.write(b": keep-alive\n\n")
                        handler.wfile.flush()
                        heartbeat_at = time.monotonic()
                time.sleep(TERMINAL_STREAM_IDLE_SLEEP_SECONDS)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def serve(self, host: str, port: int) -> None:
        app = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._dispatch("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._dispatch("POST")

            def do_PUT(self) -> None:  # noqa: N802
                self._dispatch("PUT")

            def do_PATCH(self) -> None:  # noqa: N802
                self._dispatch("PATCH")

            def do_DELETE(self) -> None:  # noqa: N802
                self._dispatch("DELETE")

            def _dispatch(self, method: str) -> None:
                parsed = urlparse(self.path)
                route_name, params = match_route(method, parsed.path)
                if route_name is None:
                    self._write_json(404, {"ok": False, "message": "Not Found"})
                    return
                if route_name == "quest_events" and app._wants_event_stream(self.path, dict(self.headers.items())):
                    try:
                        app.stream_quest_events(self, **params, path=self.path, headers=dict(self.headers.items()))
                    except Exception as exc:
                        self._write_json(500, {"ok": False, "message": str(exc)})
                    return
                if route_name == "bash_sessions_stream":
                    try:
                        app.stream_bash_sessions(self, **params, path=self.path)
                    except Exception as exc:
                        self._write_json(500, {"ok": False, "message": str(exc)})
                    return
                if route_name == "bash_log_stream":
                    try:
                        app.stream_bash_logs(self, **params, headers=dict(self.headers.items()))
                    except Exception as exc:
                        self._write_json(500, {"ok": False, "message": str(exc)})
                    return
                if route_name == "terminal_stream":
                    try:
                        app.stream_bash_logs(self, quest_id=params["quest_id"], bash_id=params["session_id"], headers=dict(self.headers.items()))
                    except Exception as exc:
                        self._write_json(500, {"ok": False, "message": str(exc)})
                    return

                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length else b""
                body = {}
                if raw_body and self.headers.get("Content-Type", "").startswith("application/json"):
                    body = app.handlers.parse_body(raw_body)

                try:
                    result = getattr(app.handlers, route_name)
                    if route_name == "asset":
                        status, headers, content = result(**params)
                        self.send_response(status)
                        for key, value in headers.items():
                            self.send_header(key, value)
                        self.end_headers()
                        self.wfile.write(content)
                        return
                    if route_name in {
                        "quest_events",
                        "bash_sessions",
                        "bash_logs",
                        "git_log",
                        "git_compare",
                        "git_commit",
                        "git_diff_file",
                        "git_commit_file",
                        "explorer",
                        "quest_search",
                        "node_traces",
                        "node_trace",
                        "document_asset",
                        "terminal_restore",
                        "terminal_history",
                    }:
                        payload = result(**params, path=self.path)
                    elif method == "GET":
                        payload = result(**params) if params else result()
                    elif route_name in {"document_open", "document_asset_upload", "chat", "command", "quest_control", "config_save", "quest_create", "quest_baseline_binding", "run_create", "qq_inbound", "connector_inbound", "docs_open", "admin_shutdown", "bash_stop", "quest_settings", "quest_bindings", "quest_delete", "terminal_session_ensure", "terminal_attach", "terminal_input", "stage_view", "latex_init", "latex_compile", "system_update_action"}:
                        payload = result(**params, body=body)
                    elif route_name == "config_validate":
                        payload = result(body)
                    elif route_name == "config_test":
                        payload = result(body)
                    elif method in {"PUT", "PATCH"}:
                        payload = result(**params, body=body)
                    elif route_name == "memory":
                        payload = result(app.handlers.parse_query(self.path))
                    else:
                        payload = result(**params) if params else result()
                except Exception as exc:
                    self._write_json(500, {"ok": False, "message": str(exc)})
                    return

                if isinstance(payload, tuple) and len(payload) == 2:
                    status, body = payload
                    self._write_json(status, body)
                    return
                if isinstance(payload, tuple) and len(payload) == 3:
                    status, headers, content = payload
                    self.send_response(status)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.end_headers()
                    if isinstance(content, str):
                        self.wfile.write(content.encode("utf-8"))
                    else:
                        self.wfile.write(content)
                    return
                self._write_json(200, payload)

            def _write_json(self, code: int, payload: dict | list) -> None:
                encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        server = ThreadingHTTPServer((host, port), RequestHandler)
        server.daemon_threads = True
        self._server = server
        self._serve_host = host
        self._serve_port = port
        self._shutdown_requested.clear()
        self._start_terminal_attach_server(host, port)
        self._start_background_connectors()
        print(f"DeepScientist daemon listening on http://{host}:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._stop_background_connectors()
            self._stop_terminal_attach_server()
            self.bash_exec_service.shutdown()
            self._server = None
            self._serve_host = None
            self._serve_port = None
            server.server_close()
