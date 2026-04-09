from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote

from ...acp import OptionalACPBridge, build_session_descriptor, build_session_update, get_acp_bridge_status
from ...bash_exec.service import DEFAULT_TERMINAL_SESSION_ID
from ... import __version__ as DEEPSCIENTIST_VERSION
from ...gitops import commit_detail, compare_refs, diff_file_between_refs, diff_file_for_commit, export_git_graph, log_ref_history
from ...memory import MemoryService
from ...quest import QuestService
from ...shared import generate_id, read_json, read_text, resolve_within, run_command, sha256_text, utc_now
from ...runners import RunRequest

_COPILOT_LEAD_MESSAGE = (
    "我是 DeepScientist，任何事情都可以找我帮忙。"
    "你可以让我读论文、改代码、看实验、整理思路，或者直接开始执行一个任务。"
)


class ApiHandlers:
    def __init__(self, app: "DaemonApp") -> None:
        self.app = app

    def _fresh_quest_service(self) -> QuestService:
        return QuestService(self.app.home, skill_installer=self.app.skill_installer)

    def _fresh_memory_service(self) -> MemoryService:
        return MemoryService(self.app.home)

    def root(self) -> tuple[int, dict, str]:
        dist_root = self._ui_dist_root()
        if dist_root is None:
            return 200, self._html_headers(), self._ui_build_required_page()
        payload = dist_root.joinpath("index.html").read_text(encoding="utf-8")
        payload = self._inject_ui_runtime(payload)
        return 200, self._html_headers(), payload

    def spa_root(self, spa_path: str) -> tuple[int, dict, str]:
        return self.root()

    def ui_asset(self, ui_path: str) -> tuple[int, dict, bytes]:
        dist_root = self._ui_dist_root()
        if dist_root is None:
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"UI bundle is not built."
        path = resolve_within(dist_root, ui_path)
        if not path.exists() or not path.is_file():
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, self._asset_headers(mime_type), path.read_bytes()

    @staticmethod
    def _html_headers() -> dict[str, str]:
        return {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, max-age=0, must-revalidate",
        }

    @staticmethod
    def _asset_headers(mime_type: str) -> dict[str, str]:
        return {
            "Content-Type": mime_type,
            "Cache-Control": "no-store, max-age=0, must-revalidate",
        }

    def _ui_dist_root(self) -> Path | None:
        dist_root = self.app.repo_root / "src" / "ui" / "dist"
        if dist_root.exists() and dist_root.joinpath("index.html").exists():
            return dist_root
        return None

    def _inject_ui_runtime(self, payload: str) -> str:
        runtime_payload = {
            "surface": "quest",
            "version": DEEPSCIENTIST_VERSION,
            "homePath": str(self.app.home),
            "auth": self.app.browser_auth_runtime_payload(),
            "supports": {
                "productApis": False,
                "socketIo": False,
                "notifications": False,
                "points": False,
                "arxiv": True,
                "cliFrontend": False,
            },
        }
        bootstrap = (
            "<script>"
            f"window.__DEEPSCIENTIST_RUNTIME__ = {json.dumps(runtime_payload, ensure_ascii=False)};"
            "</script>"
        )
        if "</head>" in payload:
            return payload.replace("</head>", f"{bootstrap}</head>", 1)
        if "<body>" in payload:
            return payload.replace("<body>", f"<body>{bootstrap}", 1)
        return f"{bootstrap}{payload}"

    def _ui_build_required_page(self) -> str:
        repo_root = html.escape(str(self.app.repo_root))
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>DeepScientist UI build required</title>
    <link rel="stylesheet" href="/assets/fonts/ds-fonts.css" />
    <style>
      :root {{
        color-scheme: light dark;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(120% 80% at 14% 0%, rgba(215, 198, 174, 0.32), transparent 58%),
          radial-gradient(80% 70% at 88% 12%, rgba(159, 177, 194, 0.28), transparent 56%),
          linear-gradient(180deg, rgba(250, 247, 241, 0.98), rgba(244, 239, 233, 0.98));
        color: #1f2937;
      }}
      .panel {{
        width: min(720px, calc(100vw - 32px));
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 28px;
        background: rgba(255, 255, 255, 0.78);
        backdrop-filter: blur(18px);
        box-shadow: 0 24px 80px -52px rgba(18, 24, 32, 0.35);
        padding: 28px;
      }}
      h1 {{ margin: 0 0 12px; font-size: 1.6rem; }}
      p {{ margin: 0 0 16px; line-height: 1.7; }}
      pre {{
        margin: 0;
        padding: 14px 16px;
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.05);
        overflow: auto;
      }}
    </style>
  </head>
  <body>
    <main class="panel">
      <h1>DeepScientist UI bundle is not built yet</h1>
      <p>The daemon is running, but the local Copilot-style web workspace requires the React bundle in <code>src/ui/dist</code>.</p>
      <p>From <code>{repo_root}</code>, run:</p>
      <pre>npm --prefix src/ui install
npm --prefix src/ui run build</pre>
      <p>For live frontend development, you can also run <code>npm --prefix src/ui run dev</code> in a separate terminal.</p>
    </main>
  </body>
</html>
"""

    def health(self) -> dict:
        return {
            "status": "ok",
            "home": str(self.app.home.resolve()),
            "daemon_id": self.app.daemon_id,
            "managed_by": self.app.daemon_managed_by,
            "pid": os.getpid(),
            "auth_enabled": self.app.browser_auth_enabled,
            "sessions": self.app.sessions.snapshot(),
        }

    def auth_login(self, body: dict | None = None) -> tuple[int, dict, str] | tuple[int, dict]:
        if not self.app.browser_auth_enabled:
            payload = {
                "ok": True,
                "authenticated": True,
                "auth_enabled": False,
            }
            return 200, {"Content-Type": "application/json; charset=utf-8"}, json.dumps(payload, ensure_ascii=False)

        candidate = str(((body or {}) if isinstance(body, dict) else {}).get("token") or "").strip()
        if not candidate:
            return 400, {
                "ok": False,
                "message": "Token is required.",
                "auth_required": True,
                "auth_enabled": True,
            }
        if not self.app.browser_auth_matches(candidate):
            return 401, {
                "ok": False,
                "message": "Invalid token.",
                "auth_required": True,
                "auth_enabled": True,
            }
        payload = {
            "ok": True,
            "authenticated": True,
            "auth_enabled": True,
            "token_masked": self.app.masked_browser_auth_token(),
        }
        return (
            200,
            {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store, max-age=0, must-revalidate",
                "Set-Cookie": self.app._browser_auth_cookie_header(candidate),
            },
            json.dumps(payload, ensure_ascii=False),
        )

    def auth_token(self) -> dict:
        return {
            "ok": True,
            "auth_enabled": self.app.browser_auth_enabled,
            "token": self.app.browser_auth_token,
            "token_masked": self.app.masked_browser_auth_token(),
        }

    def auth_rotate(self, body: dict | None = None) -> tuple[int, dict, str] | tuple[int, dict]:
        if not self.app.browser_auth_enabled:
            payload = {
                "ok": True,
                "auth_enabled": False,
                "rotated": False,
                "token": None,
                "token_masked": None,
            }
            return 200, {"Content-Type": "application/json; charset=utf-8"}, json.dumps(payload, ensure_ascii=False)

        rotated = self.app.rotate_browser_auth_token()
        payload = {
            "ok": True,
            "auth_enabled": True,
            "rotated": True,
            "token": rotated,
            "token_masked": self.app.masked_browser_auth_token(),
        }
        return (
            200,
            {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store, max-age=0, must-revalidate",
                "Set-Cookie": self.app._browser_auth_cookie_header(rotated),
            },
            json.dumps(payload, ensure_ascii=False),
        )

    def system_update(self) -> dict:
        return self.app.system_update_status()

    def system_update_action(self, body: dict) -> dict:
        action = str(body.get("action") or "").strip().lower()
        return self.app.request_system_update(action=action)

    def cli_health(self) -> dict:
        online_channels = [
            snapshot
            for snapshot in self.app.list_connector_statuses()
            if snapshot.get("enabled") is not False
        ]
        return {
            "status": "ok",
            "timestamp": utc_now(),
            "checks": {
                "local": {
                    "status": "online",
                    "online_count": len(online_channels),
                    "active_connections": len(self.app.sessions.snapshot()),
                    "local_connections": len(self.app.sessions.snapshot()),
                }
            },
        }

    def admin_shutdown(self, body: dict) -> dict:
        source = str(body.get("source") or "local-admin").strip() or "local-admin"
        expected_daemon_id = str(body.get("daemon_id") or "").strip()
        if expected_daemon_id and expected_daemon_id != self.app.daemon_id:
            return {
                "ok": False,
                "message": "Daemon identity mismatch.",
                "daemon_id": self.app.daemon_id,
            }
        return self.app.request_shutdown(source=source)

    def acp_status(self) -> dict:
        return get_acp_bridge_status().as_dict()

    def connectors(self) -> list[dict]:
        return self.app.list_connector_statuses()

    def connectors_availability(self) -> dict:
        return self.app.connector_availability_summary()

    def weixin_login_qr_start(self, body: dict | None = None) -> dict:
        payload = body if isinstance(body, dict) else {}
        return self.app.start_weixin_login_qr(force=bool(payload.get("force")))

    def weixin_login_qr_wait(self, body: dict | None = None) -> dict:
        payload = body if isinstance(body, dict) else {}
        return self.app.wait_weixin_login_qr(
            session_key=str(payload.get("session_key") or "").strip(),
            timeout_ms=int(payload.get("timeout_ms") or 1_500),
        )

    def lingzhu_health(self) -> dict:
        return self.app.lingzhu_health_payload()

    def baselines(self) -> list[dict]:
        return self.app.artifact_service.baselines.list_entries()

    def baseline_delete(self, baseline_id: str) -> dict | tuple[int, dict]:
        try:
            return self.app.artifact_service.delete_baseline(baseline_id)
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "baseline_id": baseline_id}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc), "baseline_id": baseline_id}

    def qq_bindings(self) -> list[dict]:
        return self.app.list_qq_bindings()

    def connector_bindings(self, connector: str) -> list[dict]:
        return self.app.list_connector_bindings(connector)

    def qq_inbound(self, body: dict) -> dict:
        return self.app.handle_qq_inbound(body)

    def connector_profile_delete(self, connector: str, profile_id: str) -> dict | tuple[int, dict]:
        return self.app.delete_connector_profile(connector, profile_id)

    def connector_inbound(self, connector: str, body: dict) -> dict:
        return self.app.handle_connector_inbound(connector, body)

    def quests(self) -> list[dict]:
        return self.app.quest_service.list_quests()

    def quest_next_id(self) -> dict:
        return {
            "quest_id": self.app.quest_service.preview_next_numeric_quest_id(),
        }

    def quest_create(self, body: dict) -> dict:
        goal = body.get("goal", "").strip()
        title = body.get("title", "").strip() or None
        quest_id = body.get("quest_id", "").strip() or None
        source = body.get("source", "").strip() or "web"
        preferred_connector_conversation_id = (
            str(body.get("preferred_connector_conversation_id") or "").strip() or None
        )
        requested_connector_bindings = (
            [dict(item) for item in body.get("requested_connector_bindings") if isinstance(item, dict)]
            if isinstance(body.get("requested_connector_bindings"), list)
            else []
        )
        force_connector_rebind_raw = body.get("force_connector_rebind")
        if force_connector_rebind_raw is None:
            force_connector_rebind = True
        else:
            force_connector_rebind = bool(force_connector_rebind_raw) and str(force_connector_rebind_raw).strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        auto_bind_latest_connectors_raw = body.get("auto_bind_latest_connectors")
        if auto_bind_latest_connectors_raw is None:
            auto_bind_latest_connectors = True
        else:
            auto_bind_latest_connectors = bool(auto_bind_latest_connectors_raw) and str(
                auto_bind_latest_connectors_raw
            ).strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        requested_baseline_ref = body.get("requested_baseline_ref")
        startup_contract = body.get("startup_contract")
        auto_start = body.get("auto_start") is True
        initial_message = str(body.get("initial_message") or "").strip()
        if not goal:
            return {"ok": False, "message": "Quest goal is required."}
        if requested_connector_bindings and not force_connector_rebind:
            conflicts = self.app.preview_connector_binding_conflicts(requested_connector_bindings)
            if conflicts:
                return 409, {
                    "ok": False,
                    "conflict": True,
                    "message": "One or more selected connector targets are already bound to another quest.",
                    "conflicts": conflicts,
                }
        try:
            snapshot = self.app.create_quest(
                goal=goal,
                title=title,
                quest_id=quest_id,
                source=source,
                preferred_connector_conversation_id=preferred_connector_conversation_id,
                requested_connector_bindings=requested_connector_bindings,
                force_connector_rebind=force_connector_rebind,
                auto_bind_latest_connectors=auto_bind_latest_connectors,
                requested_baseline_ref=requested_baseline_ref if isinstance(requested_baseline_ref, dict) else None,
                startup_contract=startup_contract if isinstance(startup_contract, dict) else None,
            )
        except FileExistsError as exc:
            return 409, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}
        except RuntimeError as exc:
            return 409, {"ok": False, "message": str(exc)}
        workspace_mode = (
            str(startup_contract.get("workspace_mode") or "").strip().lower()
            if isinstance(startup_contract, dict)
            else ""
        )
        if workspace_mode in {"copilot", "autonomous"}:
            quest_root = self.app.quest_service._quest_root(snapshot["quest_id"])
            self.app.quest_service.update_research_state(quest_root, workspace_mode=workspace_mode)
            if workspace_mode == "copilot":
                self.app.quest_service.append_message(
                    snapshot["quest_id"],
                    "assistant",
                    _COPILOT_LEAD_MESSAGE,
                    source="deepscientist",
                )
                self.app.quest_service.update_runtime_state(
                    quest_root=quest_root,
                    status="idle",
                    display_status="idle",
                )
                self.app.quest_service.set_continuation_state(
                    quest_root,
                    policy="wait_for_user_or_resume",
                    anchor="decision",
                    reason="copilot_mode",
                )
            snapshot = self.app.quest_service.snapshot(snapshot["quest_id"])
        payload: dict[str, object] = {"ok": True, "snapshot": snapshot}
        if auto_start:
            startup = self.app.submit_user_message(
                snapshot["quest_id"],
                text=initial_message or goal,
                source=source,
            )
            payload["startup"] = startup
            payload["snapshot"] = self.app.quest_service.snapshot(snapshot["quest_id"])
        return payload

    def quest_baseline_binding(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        baseline_id = str(body.get("baseline_id") or "").strip()
        variant_id = str(body.get("variant_id") or "").strip() or None
        if not baseline_id:
            return 400, {"ok": False, "message": "`baseline_id` is required."}
        quest_root = Path(self.app.home / "quests" / quest_id)
        if not quest_root.exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        attachment_result = self.app.artifact_service.attach_baseline(quest_root, baseline_id, variant_id)
        if not attachment_result.get("ok"):
            return 409, {
                "ok": False,
                "conflict": True,
                "message": str(
                    attachment_result.get("message")
                    or "Baseline is attached but not materializable yet; cannot confirm baseline gate automatically."
                ),
                "quest_id": quest_id,
                "binding_action": "attach_failed",
                "attachment": attachment_result.get("attachment"),
                "snapshot": self.app.quest_service.snapshot(quest_id),
            }
        attachment = attachment_result.get("attachment") if isinstance(attachment_result, dict) else None
        materialization = attachment.get("materialization") if isinstance(attachment, dict) else None
        materialization_status = str((materialization or {}).get("status") or "").strip().lower()
        if materialization_status and materialization_status != "ok":
            return 409, {
                "ok": False,
                "conflict": True,
                "message": "Baseline is attached but not materializable yet; cannot confirm baseline gate automatically.",
                "quest_id": quest_id,
                "binding_action": "attach_only",
                "attachment": attachment,
                "snapshot": self.app.quest_service.snapshot(quest_id),
            }
        try:
            confirm = self.app.artifact_service.confirm_baseline(
                quest_root,
                baseline_path=f"baselines/imported/{baseline_id}",
                baseline_id=baseline_id,
                variant_id=variant_id,
                summary=f"Baseline `{baseline_id}` confirmed via API binding.",
            )
        except FileNotFoundError as exc:
            return 409, {"ok": False, "message": str(exc), "quest_id": quest_id}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc), "quest_id": quest_id}
        snapshot = self.app.quest_service.snapshot(quest_id)
        return {
            "ok": True,
            "quest_id": quest_id,
            "binding_action": "attach_and_confirm",
            "attachment": attachment,
            "baseline_registry_entry": confirm.get("baseline_registry_entry"),
            "snapshot": snapshot,
        }

    def quest_baseline_unbind(self, quest_id: str) -> dict | tuple[int, dict]:
        quest_root = Path(self.app.home / "quests" / quest_id)
        if not quest_root.exists():
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        quest_data = self.app.quest_service.update_baseline_state(
            quest_root,
            baseline_gate="pending",
            confirmed_baseline_ref=None,
            active_anchor="baseline",
        )
        return {
            "ok": True,
            "quest_id": quest_id,
            "binding_action": "cleared",
            "baseline_gate": quest_data.get("baseline_gate"),
            "snapshot": self.app.quest_service.snapshot(quest_id),
        }

    def quest(self, quest_id: str) -> dict:
        try:
            return self.app.quest_service.snapshot(quest_id)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def quest_delete(self, quest_id: str, body: dict | None = None) -> dict | tuple[int, dict]:
        source = "web"
        if body and body.get("source"):
            source = str(body.get("source") or "").strip() or "web"
        return self.app.delete_quest(quest_id, source=source)

    def quest_settings(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        updates = {
            "title": body.get("title") if "title" in body else None,
            "active_anchor": body.get("active_anchor") if "active_anchor" in body else None,
            "default_runner": body.get("default_runner") if "default_runner" in body else None,
            "workspace_mode": body.get("workspace_mode") if "workspace_mode" in body else None,
        }
        if all(value is None for value in updates.values()):
            return {
                "ok": True,
                "snapshot": self.app.quest_service.snapshot(quest_id),
            }
        previous_snapshot = self.app.quest_service.snapshot(quest_id) if updates.get("workspace_mode") else None
        try:
            snapshot = self.app.quest_service.update_settings(quest_id, **updates)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}
        # When switching from copilot to autonomous, schedule a turn if the
        # quest was parked so it can start making progress autonomously.
        if previous_snapshot is not None:
            prev_policy = str(previous_snapshot.get("continuation_policy") or "").strip().lower()
            new_policy = str(snapshot.get("continuation_policy") or "").strip().lower()
            prev_status = str(previous_snapshot.get("status") or previous_snapshot.get("runtime_status") or "").strip().lower()
            if (
                prev_policy == "wait_for_user_or_resume"
                and new_policy == "auto"
                and prev_status not in {"completed", "paused", "error"}
            ):
                self.app.resume_quest(quest_id, source="auto:workspace_mode_switch")
                self.app.schedule_turn(quest_id, reason="autonomous_mode_activated")
        return {
            "ok": True,
            "snapshot": snapshot,
        }

    def quest_bindings(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        previous_external = self.app._quest_external_binding(quest_id)
        requested_bindings = (
            [dict(item) for item in body.get("bindings") if isinstance(item, dict)]
            if isinstance(body.get("bindings"), list)
            else []
        )
        conversation_id = str(body.get("conversation_id") or body.get("source") or "").strip() or None
        connector_name = str(body.get("connector") or "").strip() or None
        force_raw = body.get("force")
        force = bool(force_raw) and str(force_raw).strip().lower() not in {"0", "false", "no", "off"}
        if requested_bindings:
            result = self.app.update_quest_bindings(quest_id, requested_bindings, force=force)
        elif connector_name:
            result = self.app.update_quest_connector_binding(quest_id, connector_name, conversation_id, force=force)
        else:
            result = self.app.update_quest_binding(quest_id, conversation_id, force=force)
        if isinstance(result, tuple):
            return result
        current_external = self.app._quest_external_binding(quest_id)
        transition = self.app._binding_transition_summary(
            quest_id=quest_id,
            previous_conversation_id=previous_external,
            current_conversation_id=current_external,
        )
        self.app._announce_binding_transition(transition, notify_new=True, notify_old=True)
        return {
            **result,
            "binding_transition": transition,
        }

    def quest_session(self, quest_id: str) -> dict:
        try:
            snapshot = self.app.quest_service.snapshot_fast(quest_id)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}
        for kind in ("details", "canvas", "git_canvas"):
            try:
                self.app.quest_service.prime_projection(quest_id, kind)
            except Exception:
                continue
        self.app.schedule_latest_quest_terminal_prewarm(quest_id)
        return {
            "ok": True,
            "quest_id": quest_id,
            "snapshot": snapshot,
            "acp_session": build_session_descriptor(snapshot),
        }

    def quest_events(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        after = int((query.get("after") or ["0"])[0] or "0")
        before_raw = ((query.get("before") or [""])[0] or "").strip()
        before = int(before_raw) if before_raw.isdigit() else None
        limit = int((query.get("limit") or ["200"])[0] or "200")
        tail_raw = ((query.get("tail") or ["0"])[0] or "0").strip().lower()
        tail = tail_raw in {"1", "true", "yes", "on"}
        format_name = ((query.get("format") or ["both"])[0] or "both").lower()
        session_id = ((query.get("session_id") or [f"quest:{quest_id}"])[0] or f"quest:{quest_id}")
        payload = self.app.quest_service.events(
            quest_id,
            after=after,
            before=before,
            limit=limit,
            tail=tail,
        )
        if format_name in {"acp", "both"}:
            payload["acp_updates"] = [
                build_session_update(
                    event,
                    quest_id=quest_id,
                    cursor=event["cursor"],
                    session_id=session_id,
                )
                for event in payload["events"]
            ]
        if format_name in {"acp_sdk", "both"}:
            bridge = OptionalACPBridge()
            payload["acp_sdk_available"] = bridge.is_available()
            payload["acp_sdk_notifications"] = [
                notification
                for event in payload["events"]
                for notification in [bridge.build_sdk_notification(session_id=session_id, event=event)]
                if notification is not None
            ]
        if format_name == "acp":
            payload["events"] = []
            payload.pop("acp_sdk_notifications", None)
        elif format_name == "acp_sdk":
            payload["events"] = []
            payload.pop("acp_updates", None)
        payload["format"] = format_name
        payload["session_id"] = session_id
        return payload

    def quest_artifacts(self, quest_id: str) -> dict:
        return self.app.quest_service.artifacts(quest_id)

    def history(self, quest_id: str) -> list[dict]:
        return self.app.quest_service.history(quest_id)

    def bash_sessions(self, quest_id: str, path: str) -> list[dict]:
        query = self.parse_query(path)
        status = ((query.get("status") or [""])[0] or "").strip() or None
        kind = ((query.get("kind") or [""])[0] or "").strip() or None
        chat_session_id = ((query.get("chat_session_id") or [""])[0] or "").strip() or None
        limit_raw = ((query.get("limit") or ["200"])[0] or "200").strip()
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
        quest_root = self.app.quest_service._quest_root(quest_id)
        return self.app.bash_exec_service.list_sessions(
            quest_root,
            status=status,
            kind=kind,
            agent_ids=agent_ids or None,
            agent_instance_ids=agent_instance_ids or None,
            chat_session_id=chat_session_id,
            limit=limit,
        )

    def bash_session(self, quest_id: str, bash_id: str) -> dict | tuple[int, dict]:
        quest_root = self.app.quest_service._quest_root(quest_id)
        try:
            return self.app.bash_exec_service.get_session(quest_root, bash_id)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown bash session `{bash_id}`."}

    def bash_logs(self, quest_id: str, bash_id: str, path: str) -> tuple[int, dict, bytes]:
        query = self.parse_query(path)
        limit_raw = ((query.get("limit") or ["200"])[0] or "200").strip()
        before_seq_raw = ((query.get("before_seq") or [""])[0] or "").strip()
        after_seq_raw = ((query.get("after_seq") or [""])[0] or "").strip()
        order = ((query.get("order") or ["asc"])[0] or "asc").strip().lower()
        try:
            limit = max(1, min(int(limit_raw), 1000))
        except ValueError:
            limit = 200
        before_seq = int(before_seq_raw) if before_seq_raw.isdigit() else None
        after_seq = int(after_seq_raw) if after_seq_raw.isdigit() else None
        quest_root = self.app.quest_service._quest_root(quest_id)
        try:
            entries, meta = self.app.bash_exec_service.read_log_entries(
                quest_root,
                bash_id,
                limit=limit,
                before_seq=before_seq,
                after_seq=after_seq,
                order=order,
            )
        except FileNotFoundError:
            payload = json.dumps({"ok": False, "message": f"Unknown bash session `{bash_id}`."}, ensure_ascii=False).encode("utf-8")
            return 404, {"Content-Type": "application/json; charset=utf-8"}, payload
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Bash-Log-Tail-Limit": str(meta.get("tail_limit") or ""),
            "X-Bash-Log-Tail-Start-Seq": str(meta.get("tail_start_seq") or ""),
            "X-Bash-Log-Latest-Seq": str(meta.get("latest_seq") or ""),
        }
        payload = json.dumps(entries, ensure_ascii=False).encode("utf-8")
        return 200, headers, payload

    def bash_stop(self, quest_id: str, bash_id: str, body: dict) -> dict | tuple[int, dict]:
        quest_root = self.app.quest_service._quest_root(quest_id)
        wait = bool(body.get("wait"))
        timeout_seconds_raw = body.get("timeout_seconds")
        timeout_seconds = timeout_seconds_raw if isinstance(timeout_seconds_raw, int) and timeout_seconds_raw > 0 else None
        try:
            session = self.app.bash_exec_service.request_stop(
                quest_root,
                bash_id,
                reason=str(body.get("reason") or "").strip() or None,
                user_id="web-react",
                force=bool(body.get("force")),
            )
        except FileNotFoundError:
            return 404, {"success": False, "status": "not_found"}
        if wait:
            session = self.app.bash_exec_service.wait_for_session(quest_root, bash_id, timeout_seconds=timeout_seconds)
        return {
            "success": True,
            "status": session.get("status"),
            "session": session,
        }

    def terminal_session_ensure(self, quest_id: str, body: dict | None = None) -> dict:
        payload = body or {}
        quest_root = self.app.quest_service._quest_root(quest_id)
        workspace_root = self.app.quest_service.active_workspace_root(quest_root)
        requested_bash_id = str(payload.get("bash_id") or "").strip() or None
        requested_label = str(payload.get("label") or "").strip() or None
        requested_cwd = str(payload.get("cwd") or "").strip() or None
        create_new_raw = payload.get("create_new")
        create_new = bool(create_new_raw) and str(create_new_raw).strip().lower() not in {"0", "false", "no", "off"}

        bash_id = requested_bash_id
        if create_new:
            # `terminal-main` is reserved for the default terminal session.
            if not bash_id or bash_id == DEFAULT_TERMINAL_SESSION_ID:
                bash_id = generate_id("terminal")
            # Guard against collisions (e.g., fast repeated clicks).
            for _ in range(8):
                if not self.app.bash_exec_service.meta_path(quest_root, bash_id).exists():
                    break
                bash_id = generate_id("terminal")
        bash_id = bash_id or DEFAULT_TERMINAL_SESSION_ID

        cwd_path = workspace_root
        if requested_cwd:
            candidate = Path(requested_cwd).expanduser()
            if candidate.is_absolute():
                cwd_path = candidate
            else:
                cwd_path = (workspace_root / candidate)

        session = self.app.bash_exec_service.ensure_terminal_session(
            quest_root,
            quest_id=quest_id,
            bash_id=bash_id,
            label=requested_label,
            cwd=cwd_path,
            source=str(payload.get("source") or "web-react").strip() or "web-react",
            conversation_id=str(payload.get("conversation_id") or "").strip() or None,
            user_id=str(payload.get("user_id") or "").strip() or None,
        )
        return {
            "ok": True,
            "session": session,
        }

    def terminal_input(self, quest_id: str, session_id: str, body: dict) -> dict | tuple[int, dict]:
        quest_root = self.app.quest_service._quest_root(quest_id)
        try:
            result = self.app.bash_exec_service.append_terminal_input(
                quest_root,
                session_id,
                data=str(body.get("data") or ""),
                source=str(body.get("source") or "web-react").strip() or "web-react",
                user_id=str(body.get("user_id") or "").strip() or None,
                conversation_id=str(body.get("conversation_id") or "").strip() or None,
            )
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown terminal session `{session_id}`."}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}
        return result

    def terminal_attach(self, quest_id: str, session_id: str, body: dict | None = None) -> dict | tuple[int, dict]:
        _unused = body or {}
        quest_root = self.app.quest_service._quest_root(quest_id)
        try:
            session = self.app.bash_exec_service.get_session(quest_root, session_id)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown terminal session `{session_id}`."}
        if str(session.get("status") or "").lower() in {"completed", "failed", "terminated"}:
            return 409, {"ok": False, "message": "terminal_session_inactive", "session": session}
        try:
            token = self.app.bash_exec_service.issue_terminal_attach_token(quest_root, session_id)
        except ValueError as exc:
            return 409, {"ok": False, "message": str(exc), "session": session}
        attach_port = self.app._terminal_attach_port
        if not attach_port:
            return 503, {"ok": False, "message": "terminal_attach_server_unavailable", "session": session}
        return {
            "ok": True,
            "port": attach_port,
            "path": "/terminal/attach",
            "token": token["token"],
            "expires_at": token["expires_at"],
            "session": session,
        }

    def terminal_restore(self, quest_id: str, session_id: str, path: str) -> dict | tuple[int, dict]:
        query = self.parse_query(path)
        commands_raw = ((query.get("commands") or ["10"])[0] or "10").strip()
        output_raw = ((query.get("output") or ["80"])[0] or "80").strip()
        try:
            command_limit = max(1, min(int(commands_raw), 50))
        except ValueError:
            command_limit = 10
        try:
            output_limit = max(1, min(int(output_raw), 400))
        except ValueError:
            output_limit = 80
        quest_root = self.app.quest_service._quest_root(quest_id)
        try:
            return self.app.bash_exec_service.terminal_restore_payload(
                quest_root,
                session_id,
                command_limit=command_limit,
                output_limit=output_limit,
            )
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown terminal session `{session_id}`."}

    def terminal_history(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        limit_raw = ((query.get("limit") or ["20"])[0] or "20").strip()
        try:
            limit = max(1, min(int(limit_raw), 100))
        except ValueError:
            limit = 20
        quest_root = self.app.quest_service._quest_root(quest_id)
        sessions = self.app.bash_exec_service.list_sessions(
            quest_root,
            limit=limit,
        )
        terminal_sessions = [item for item in sessions if str(item.get("kind") or "") == "terminal"]
        exec_sessions = [item for item in sessions if str(item.get("kind") or "exec") != "terminal"]
        default_session_id = terminal_sessions[0]["bash_id"] if terminal_sessions else None
        return {
            "ok": True,
            "default_session_id": default_session_id,
            "terminal_sessions": terminal_sessions,
            "exec_sessions": exec_sessions[:limit],
        }

    def quest_control(self, quest_id: str, body: dict) -> dict:
        action = str(body.get("action") or "").strip().lower()
        source = str(body.get("source") or "local-ui").strip() or "local-ui"
        if action not in {"pause", "stop", "resume"}:
            return {"ok": False, "message": "Quest control action must be `pause`, `stop` or `resume`."}
        return self.app.control_quest(quest_id, action=action, source=source)

    def workflow(self, quest_id: str) -> dict:
        payload = self.app.quest_service.workflow(quest_id)
        projection_state = str(((payload or {}).get("projection_status") or {}).get("state") or "").strip().lower()
        if projection_state and projection_state != "ready":
            if isinstance(payload, dict):
                payload["optimization_frontier"] = None
            return payload
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        try:
            frontier = self.app.artifact_service.get_optimization_frontier(quest_root)
        except Exception:
            frontier = {"ok": False}
        if isinstance(payload, dict):
            payload["optimization_frontier"] = frontier.get("optimization_frontier") if isinstance(frontier, dict) else None
        return payload

    def quest_layout(self, quest_id: str) -> dict:
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        payload = self.app.quest_service.read_lab_canvas_state(quest_root)
        return {
            "layout_json": payload.get("layout_json") if isinstance(payload.get("layout_json"), dict) else {},
            "updated_at": payload.get("updated_at"),
        }

    def quest_layout_update(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        raw_layout = body.get("layout_json")
        if raw_layout is not None and not isinstance(raw_layout, dict):
            return 400, {"ok": False, "message": "`layout_json` must be an object."}
        payload = self.app.quest_service.update_lab_canvas_state(
            quest_root,
            layout_json=dict(raw_layout or {}),
        )
        return {
            "layout_json": payload.get("layout_json") if isinstance(payload.get("layout_json"), dict) else {},
            "updated_at": payload.get("updated_at"),
        }

    def node_traces(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        selection_type = ((query.get("selection_type") or [""])[0] or "").strip() or None
        return self.app.quest_service.node_traces(quest_id, selection_type=selection_type)

    def node_trace(self, quest_id: str, node_ref: str, path: str) -> dict:
        query = self.parse_query(path)
        selection_type = ((query.get("selection_type") or [""])[0] or "").strip() or None
        return self.app.quest_service.node_trace(
            quest_id,
            unquote(node_ref),
            selection_type=selection_type,
        )

    def stage_view(self, quest_id: str, body: dict) -> dict:
        return self.app.quest_service.stage_view(quest_id, selection=body)

    def graph(self, quest_id: str) -> dict:
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return export_git_graph(quest_root, quest_root / "artifacts" / "graphs")

    def metrics_timeline(self, quest_id: str) -> dict:
        return self.app.quest_service.metrics_timeline(quest_id)

    def baseline_compare(self, quest_id: str) -> dict:
        return self.app.quest_service.baseline_compare(quest_id)

    def git_branches(self, quest_id: str) -> dict:
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        payload = self.app.quest_service.git_branch_canvas(quest_id)
        research_state = self.app.quest_service.read_research_state(quest_root)
        active_workspace_branch = str(research_state.get("current_workspace_branch") or "").strip() or None
        research_head_branch = str(research_state.get("research_head_branch") or "").strip() or None
        payload["active_workspace_ref"] = active_workspace_branch
        payload["research_head_ref"] = research_head_branch
        payload["workspace_mode"] = str(research_state.get("workspace_mode") or "quest").strip() or "quest"
        projection_state = str(((payload or {}).get("projection_status") or {}).get("state") or "").strip().lower()
        if projection_state and projection_state != "ready" and not (payload.get("nodes") or []):
            return payload
        quest_data = self.app.quest_service.read_quest_yaml(quest_root)
        active_anchor = str(quest_data.get("active_anchor") or "").strip().lower()
        active_analysis_campaign_id = str(research_state.get("active_analysis_campaign_id") or "").strip() or None
        current_workspace_branch = str(research_state.get("current_workspace_branch") or "").strip() or None
        workspace_mode = str(research_state.get("workspace_mode") or "").strip().lower() or "quest"
        paper_parent_branch = str(research_state.get("paper_parent_branch") or "").strip() or None
        paper_parent_run_id = str(research_state.get("paper_parent_run_id") or "").strip() or None
        next_pending_slice_id = str(research_state.get("next_pending_slice_id") or "").strip() or None
        try:
            branch_summary = self.app.artifact_service.list_research_branches(quest_root)
        except Exception:
            branch_summary = {"branches": []}
        try:
            optimization_frontier = self.app.artifact_service.get_optimization_frontier(quest_root)
        except Exception:
            optimization_frontier = {"ok": False}
        branch_summary_by_name = {
            str(item.get("branch_name") or "").strip(): item
            for item in (branch_summary.get("branches") or [])
            if str(item.get("branch_name") or "").strip()
        }
        frontier_payload = (
            dict(optimization_frontier.get("optimization_frontier") or {})
            if isinstance(optimization_frontier, dict)
            and isinstance(optimization_frontier.get("optimization_frontier"), dict)
            else {}
        )
        best_branch_name = str(((frontier_payload.get("best_branch") or {}) if isinstance(frontier_payload.get("best_branch"), dict) else {}).get("branch_name") or "").strip() or None
        stagnant_branch_names = {
            str(item.get("branch_name") or "").strip()
            for item in (frontier_payload.get("stagnant_branches") or [])
            if isinstance(item, dict) and str(item.get("branch_name") or "").strip()
        }
        fusion_candidate_names = {
            str(item.get("branch_name") or "").strip()
            for item in (frontier_payload.get("fusion_candidates") or [])
            if isinstance(item, dict) and str(item.get("branch_name") or "").strip()
        }
        candidate_count_by_branch: dict[str, int] = {}
        for item in frontier_payload.get("implementation_candidates") or []:
            if not isinstance(item, dict):
                continue
            branch_name = str(item.get("branch") or "").strip()
            if not branch_name:
                continue
            candidate_count_by_branch[branch_name] = candidate_count_by_branch.get(branch_name, 0) + 1
        active_campaign = {}
        if active_analysis_campaign_id:
            try:
                active_campaign = self.app.artifact_service.get_analysis_campaign(
                    quest_root,
                    campaign_id=active_analysis_campaign_id,
                )
            except Exception:
                active_campaign = {}
        campaign_parent_branch = (
            str(active_campaign.get("parent_branch") or "").strip() or None
            if isinstance(active_campaign, dict)
            else None
        )
        campaign_paper_line_branch = (
            str(active_campaign.get("paper_line_branch") or "").strip() or None
            if isinstance(active_campaign, dict)
            else None
        )
        campaign_slices = [
            dict(item)
            for item in ((active_campaign or {}).get("slices") or [])
            if isinstance(item, dict)
        ]
        campaign_total_slices = len(campaign_slices)
        campaign_completed_slices = sum(
            1 for item in campaign_slices if str(item.get("status") or "").strip().lower() == "completed"
        )
        slice_by_branch = {
            str(item.get("branch") or "").strip(): item
            for item in campaign_slices
            if str(item.get("branch") or "").strip()
        }

        def resolve_workflow_state(ref: str, summary: dict[str, object] | None) -> dict[str, object]:
            branch_kind = self.app.artifact_service._branch_kind_from_name(ref)
            has_main_result = bool((summary or {}).get("has_main_result"))
            workflow_state: dict[str, object] = {
                "analysis_state": "none",
                "writing_state": "not_ready",
                "analysis_campaign_id": active_analysis_campaign_id,
                "total_slices": campaign_total_slices or None,
                "completed_slices": campaign_completed_slices or None,
                "next_pending_slice_id": next_pending_slice_id,
                "paper_parent_branch": paper_parent_branch,
                "paper_parent_run_id": paper_parent_run_id,
                "status_reason": None,
            }
            if branch_kind == "analysis":
                slice_entry = slice_by_branch.get(ref)
                slice_status = str((slice_entry or {}).get("status") or "pending").strip().lower() or "pending"
                if slice_status == "completed":
                    workflow_state["analysis_state"] = "completed"
                    workflow_state["status_reason"] = "Analysis slice completed."
                elif ref == current_workspace_branch or str((slice_entry or {}).get("slice_id") or "").strip() == next_pending_slice_id:
                    workflow_state["analysis_state"] = "active"
                    workflow_state["status_reason"] = (
                        f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                        if campaign_total_slices
                        else "Analysis slice active."
                    )
                else:
                    workflow_state["analysis_state"] = "pending"
                    workflow_state["status_reason"] = "Analysis slice pending."
                return workflow_state
            if branch_kind == "paper":
                if campaign_paper_line_branch and ref == campaign_paper_line_branch and next_pending_slice_id is not None:
                    workflow_state["analysis_state"] = "active"
                    workflow_state["writing_state"] = "blocked_by_analysis"
                    workflow_state["status_reason"] = (
                        f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                        + (f" · next: {next_pending_slice_id}" if next_pending_slice_id else "")
                    )
                    return workflow_state
                if ref == current_workspace_branch and workspace_mode == "paper":
                    workflow_state["writing_state"] = "completed" if active_anchor == "finalize" else "active"
                    workflow_state["status_reason"] = (
                        "Writing finalized." if active_anchor == "finalize" else "Writing workspace active."
                    )
                else:
                    workflow_state["writing_state"] = "ready"
                    workflow_state["status_reason"] = "Writing workspace prepared."
                return workflow_state
            if campaign_parent_branch and not campaign_paper_line_branch and ref == campaign_parent_branch:
                workflow_state["analysis_state"] = "completed" if next_pending_slice_id is None else "active"
                if has_main_result:
                    workflow_state["writing_state"] = "ready" if next_pending_slice_id is None else "blocked_by_analysis"
                workflow_state["status_reason"] = (
                    "Analysis complete. Ready for writing."
                    if next_pending_slice_id is None
                    else (
                        f"Analysis {campaign_completed_slices}/{campaign_total_slices} done"
                        + (f" · next: {next_pending_slice_id}" if next_pending_slice_id else "")
                    )
                )
                return workflow_state
            if has_main_result:
                workflow_state["writing_state"] = "ready"
                workflow_state["status_reason"] = "Main experiment recorded. Ready for writing."
                return workflow_state
            workflow_state["status_reason"] = "Awaiting main experiment result."
            return workflow_state

        for node in payload.get("nodes", []):
            ref = str(node.get("ref") or "").strip()
            if not ref:
                continue
            summary = branch_summary_by_name.get(ref)
            node["active_workspace"] = ref == active_workspace_branch
            node["research_head"] = ref == research_head_branch
            node["workflow_state"] = resolve_workflow_state(ref, summary if isinstance(summary, dict) else None)
            if not isinstance(summary, dict):
                continue
            node["branch_no"] = summary.get("branch_no")
            node["idea_title"] = summary.get("idea_title")
            node["idea_problem"] = summary.get("idea_problem")
            node["next_target"] = summary.get("next_target")
            node["lineage_intent"] = summary.get("lineage_intent")
            node["parent_branch"] = summary.get("parent_branch")
            node["foundation_ref"] = summary.get("foundation_ref")
            node["foundation_reason"] = summary.get("foundation_reason")
            node["idea_md_path"] = summary.get("idea_md_path")
            node["idea_draft_path"] = summary.get("idea_draft_path")
            node["latest_main_experiment"] = summary.get("latest_main_experiment")
            node["experiment_count"] = summary.get("experiment_count")
            node["has_main_result"] = summary.get("has_main_result")
            node["optimization_mode"] = frontier_payload.get("mode")
            node["optimization_best"] = ref == best_branch_name
            node["optimization_stagnant"] = ref in stagnant_branch_names
            node["optimization_fusion_candidate"] = ref in fusion_candidate_names
            node["optimization_candidate_count"] = candidate_count_by_branch.get(ref, 0)
        return payload

    def git_canvas(self, quest_id: str) -> dict:
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        payload = self.app.quest_service.git_commit_canvas(quest_id)
        research_state = self.app.quest_service.read_research_state(quest_root)
        active_workspace_branch = str(research_state.get("current_workspace_branch") or "").strip() or None
        payload["active_workspace_ref"] = active_workspace_branch
        payload["workspace_mode"] = str(research_state.get("workspace_mode") or "copilot").strip() or "copilot"
        return payload

    def git_log(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        ref = ((query.get("ref") or [""])[0] or "").strip()
        base = ((query.get("base") or [""])[0] or "").strip() or None
        limit_raw = ((query.get("limit") or ["30"])[0] or "30").strip()
        if not ref:
            return {"ok": False, "message": "`ref` is required."}
        try:
            limit = max(1, min(int(limit_raw), 100))
        except ValueError:
            limit = 30
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return log_ref_history(quest_root, ref=ref, base=base, limit=limit)

    def git_compare(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        base = ((query.get("base") or [""])[0] or "").strip()
        head = ((query.get("head") or [""])[0] or "").strip()
        if not base or not head:
            return {"ok": False, "message": "`base` and `head` are required."}
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return compare_refs(quest_root, base=base, head=head)

    def git_commit(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        sha = ((query.get("sha") or [""])[0] or "").strip()
        if not sha:
            return {"ok": False, "message": "`sha` is required."}
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return commit_detail(quest_root, sha=sha)

    def git_diff_file(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        base = ((query.get("base") or [""])[0] or "").strip()
        head = ((query.get("head") or [""])[0] or "").strip()
        file_path = ((query.get("path") or [""])[0] or "").strip()
        if not base or not head or not file_path:
            return {"ok": False, "message": "`base`, `head`, and `path` are required."}
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return diff_file_between_refs(quest_root, base=base, head=head, path=file_path)

    def file_change_diff(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        run_id = ((query.get("run_id") or [""])[0] or "").strip()
        event_id = ((query.get("event_id") or [""])[0] or "").strip() or None
        raw_path = ((query.get("path") or [""])[0] or "").strip()
        if not run_id or not raw_path:
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id or None,
                event_id=event_id,
                message="`run_id` and `path` are required.",
                ok=False,
            )

        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        run_artifact = read_json(quest_root / ".ds" / "runs" / run_id / "artifact.json", default={})
        if not isinstance(run_artifact, dict):
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id,
                event_id=event_id,
                message="Historical patch unavailable. Run artifact metadata is missing.",
                ok=False,
            )

        record = run_artifact.get("record") if isinstance(run_artifact.get("record"), dict) else {}
        checkpoint = run_artifact.get("checkpoint") if isinstance(run_artifact.get("checkpoint"), dict) else {}
        base = str(record.get("head_commit") or "").strip()
        head = str(checkpoint.get("head") or "").strip()
        branch = str(record.get("branch") or "").strip() or None
        workspace_root = self._file_change_workspace_root(run_artifact, record)
        relative_path = None
        display_path = None

        if not base or not head:
            relative_path = self._relative_file_change_path(None, raw_path, workspace_root)
            display_path = self._display_file_change_path(quest_root, raw_path, relative_path=relative_path)
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id,
                event_id=event_id,
                base=base,
                head=head,
                branch=branch,
                relative_path=relative_path,
                display_path=display_path,
                message="Historical patch unavailable. Run artifact metadata is missing the recorded commit range.",
                ok=True,
            )

        repo_root = self._resolve_git_repo_root_for_file_change(raw_path, workspace_root)
        relative_path = self._relative_file_change_path(repo_root, raw_path, workspace_root)
        display_path = self._display_file_change_path(quest_root, raw_path, relative_path=relative_path)

        if repo_root is None or not relative_path:
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id,
                event_id=event_id,
                base=base,
                head=head,
                branch=branch,
                relative_path=relative_path,
                display_path=display_path,
                message="Historical patch unavailable. DeepScientist could not map this file to a git worktree.",
                ok=True,
            )

        try:
            diff = diff_file_between_refs(repo_root, base=base, head=head, path=relative_path)
        except Exception:
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id,
                event_id=event_id,
                base=base,
                head=head,
                branch=branch,
                relative_path=relative_path,
                display_path=display_path,
                message=(
                    "Historical patch unavailable. The saved run checkpoint does not match the git repository "
                    "that currently owns this file."
                ),
                ok=True,
            )

        if (
            not diff.get("binary")
            and not diff.get("lines")
            and int(diff.get("added") or 0) == 0
            and int(diff.get("removed") or 0) == 0
        ):
            return self._file_change_diff_unavailable(
                raw_path=raw_path,
                run_id=run_id,
                event_id=event_id,
                base=base,
                head=head,
                branch=branch,
                relative_path=relative_path,
                display_path=display_path,
                message=(
                    "Historical patch unavailable. This event only preserved file-level metadata or the edit "
                    "did not land in the run's final checkpoint."
                ),
                ok=True,
            )

        return {
            **diff,
            "available": True,
            "source": "run_range",
            "display_path": display_path or relative_path,
            "run_id": run_id,
            "event_id": event_id,
            "branch": branch,
            "message": None,
        }

    def git_commit_file(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        sha = ((query.get("sha") or [""])[0] or "").strip()
        file_path = ((query.get("path") or [""])[0] or "").strip()
        if not sha or not file_path:
            return {"ok": False, "message": "`sha` and `path` are required."}
        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        return diff_file_for_commit(quest_root, sha=sha, path=file_path)

    def graph_asset(self, quest_id: str, kind: str) -> tuple[int, dict, bytes]:
        graph = self.graph(quest_id)
        key = f"{kind}_path"
        raw_path = graph.get(key)
        if not raw_path:
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"

        quest_root = self._fresh_quest_service()._quest_root(quest_id)
        raw_file = Path(str(raw_path))
        if raw_file.is_absolute():
            try:
                relative = raw_file.relative_to(quest_root)
            except ValueError:
                return 400, {"Content-Type": "text/plain; charset=utf-8"}, b"Invalid graph path"
            path = resolve_within(quest_root, str(relative))
        else:
            path = resolve_within(quest_root, str(raw_file))

        if not path.exists() or not path.is_file():
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, {"Content-Type": mime_type}, path.read_bytes()

    def runs(self, quest_id: str) -> list[dict]:
        return self.app.quest_service.snapshot(quest_id).get("recent_runs", [])

    def arxiv_list(self, path: str = "") -> dict | tuple[int, dict]:
        query = self.parse_query(path)
        quest_id = ((query.get("project_id") or [""])[0] or "").strip()
        if not quest_id:
            return 400, {"ok": False, "message": "`project_id` is required."}
        quest_root = self.app.quest_service._quest_root(quest_id)
        return self.app.artifact_service.arxiv(mode="list", quest_root=quest_root)

    def arxiv_import(self, body: dict | None = None) -> dict | tuple[int, dict]:
        body = body or {}
        quest_id = str(body.get("project_id") or "").strip()
        paper_id = str(body.get("arxiv_id") or "").strip()
        if not quest_id:
            return 400, {"ok": False, "message": "`project_id` is required."}
        if not paper_id:
            return 400, {"ok": False, "message": "`arxiv_id` is required."}
        quest_root = self.app.quest_service._quest_root(quest_id)
        result = self.app.artifact_service.arxiv(
            paper_id,
            mode="read",
            full_text=False,
            quest_root=quest_root,
        )
        if not result.get("ok"):
            return 400, result
        return {
            "status": str(result.get("status") or "processing"),
            "metadata_status": str(result.get("metadata_status") or ""),
            "metadata_pending": bool(result.get("metadata_pending")),
            "title": str(result.get("title") or ""),
            "message": str(result.get("message") or ""),
            "abs_url": str(result.get("abs_url") or ""),
            "file_id": str(result.get("file_id") or ""),
            "document_id": str(result.get("document_id") or ""),
            "arxiv_id": str(result.get("paper_id") or paper_id),
        }

    def annotations_file(self, file_id: str, path: str = "") -> dict | tuple[int, dict]:
        try:
            return self.app.annotation_service.list_annotations(file_id)
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "file_id": file_id}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc), "file_id": file_id}

    def annotations_project(self, project_id: str, path: str = "") -> dict | tuple[int, dict]:
        query = self.parse_query(path)
        search_query = ((query.get("q") or [""])[0] or "").strip() or None
        color = ((query.get("color") or [""])[0] or "").strip() or None
        tag = ((query.get("tag") or [""])[0] or "").strip() or None
        page_raw = ((query.get("page") or [""])[0] or "").strip()
        limit_raw = ((query.get("limit") or ["100"])[0] or "100").strip()
        try:
            page = int(page_raw) if page_raw else None
        except ValueError:
            page = None
        try:
            limit = max(1, min(int(limit_raw), 500))
        except ValueError:
            limit = 100
        try:
            return self.app.annotation_service.search_annotations(
                project_id,
                query=search_query,
                color=color,
                tag=tag,
                page=page,
                limit=limit,
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "project_id": project_id}

    def annotation_create(self, body: dict) -> dict | tuple[int, dict]:
        file_id = str(body.get("file_id") or "").strip()
        if not file_id:
            return 400, {"ok": False, "message": "`file_id` is required."}
        try:
            return self.app.annotation_service.create_annotation(
                file_id=file_id,
                position=body.get("position"),
                content=body.get("content"),
                comment=body.get("comment"),
                kind=body.get("kind"),
                color=body.get("color"),
                tags=body.get("tags"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "file_id": file_id}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc), "file_id": file_id}

    def annotation_detail(self, annotation_id: str) -> dict | tuple[int, dict]:
        try:
            return self.app.annotation_service.get_annotation(annotation_id)
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "annotation_id": annotation_id}

    def annotation_update(self, annotation_id: str, body: dict) -> dict | tuple[int, dict]:
        try:
            return self.app.annotation_service.update_annotation(
                annotation_id,
                comment=body.get("comment") if "comment" in body else None,
                kind=body.get("kind") if "kind" in body else None,
                position=body.get("position") if "position" in body else None,
                content=body.get("content") if "content" in body else None,
                color=body.get("color") if "color" in body else None,
                tags=body.get("tags") if "tags" in body else None,
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "annotation_id": annotation_id}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc), "annotation_id": annotation_id}

    def annotation_delete(self, annotation_id: str) -> dict | tuple[int, dict]:
        try:
            return self.app.annotation_service.delete_annotation(annotation_id)
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc), "annotation_id": annotation_id}

    def quest_memory(self, quest_id: str) -> list[dict]:
        quest_service = self._fresh_quest_service()
        return self._fresh_memory_service().list_cards(
            scope="quest",
            quest_root=quest_service._quest_root(quest_id),
        )

    def documents(self, quest_id: str) -> list[dict]:
        try:
            return self.app.quest_service.list_documents(quest_id)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def explorer(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        revision = ((query.get("revision") or [""])[0] or "").strip() or None
        mode = ((query.get("mode") or [""])[0] or "").strip() or None
        profile = ((query.get("profile") or [""])[0] or "").strip() or None
        try:
            return self.app.quest_service.explorer(
                quest_id,
                revision=revision,
                mode=mode,
                profile=profile,
            )
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def quest_search(self, quest_id: str, path: str) -> dict:
        query = self.parse_query(path)
        term = ((query.get("q") or [""])[0] or "").strip()
        try:
            limit = int(((query.get("limit") or ["50"])[0] or "50").strip())
        except ValueError:
            limit = 50
        try:
            return self.app.quest_service.search_files(quest_id, term=term, limit=limit)
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def quest_file_create_folder(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        try:
            return self._fresh_quest_service().create_workspace_folder(
                quest_id,
                name=body.get("name"),
                parent_path=body.get("parent_path"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc)}
        except FileExistsError as exc:
            return 409, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}

    def quest_file_upload(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        file_name = str(body.get("file_name") or "").strip()
        content_base64 = str(body.get("content_base64") or "").strip()
        mime_type = str(body.get("mime_type") or "").strip() or None
        if not file_name:
            return 400, {"ok": False, "message": "`file_name` is required."}
        if not content_base64:
            return 400, {"ok": False, "message": "`content_base64` is required."}
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "Invalid `content_base64` payload."}
        try:
            return self._fresh_quest_service().upload_workspace_file(
                quest_id,
                file_name=file_name,
                content=content,
                mime_type=mime_type,
                parent_path=body.get("parent_path"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc)}
        except FileExistsError as exc:
            return 409, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}

    def quest_file_rename(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        try:
            return self._fresh_quest_service().rename_workspace_entry(
                quest_id,
                path=body.get("path"),
                new_name=body.get("new_name"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc)}
        except FileExistsError as exc:
            return 409, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}

    def quest_file_move(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        try:
            return self._fresh_quest_service().move_workspace_entries(
                quest_id,
                paths=body.get("paths"),
                target_parent_path=body.get("target_parent_path"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc)}
        except FileExistsError as exc:
            return 409, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}

    def quest_file_delete(self, quest_id: str, body: dict) -> dict | tuple[int, dict]:
        try:
            return self._fresh_quest_service().delete_workspace_entries(
                quest_id,
                paths=body.get("paths"),
            )
        except FileNotFoundError as exc:
            return 404, {"ok": False, "message": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "message": str(exc)}

    def document_asset(self, quest_id: str, path: str) -> tuple[int, dict, bytes]:
        quest_service = self._fresh_quest_service()
        query = self.parse_query(path)
        document_id = (query.get("document_id") or [""])[0].strip()
        if not document_id:
            return 400, {"Content-Type": "text/plain; charset=utf-8"}, b"`document_id` is required."
        if document_id.startswith("git::"):
            quest_root = quest_service._quest_root(quest_id)
            revision, relative = quest_service._parse_git_document_id(document_id)
            if not quest_service._git_revision_exists(quest_root, revision):
                return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
            file_path = Path(relative)
            mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            content = quest_service._read_git_bytes(quest_root, revision, relative)
            return 200, self._asset_headers(mime_type), content
        path, _writable, _scope, _source_kind = quest_service.resolve_document(quest_id, document_id)
        if not path.exists() or not path.is_file():
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, self._asset_headers(mime_type), path.read_bytes()

    def document_open(self, quest_id: str, body: dict) -> dict:
        try:
            return self._fresh_quest_service().open_document(quest_id, body["document_id"])
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def document_asset_upload(self, quest_id: str, body: dict) -> dict:
        document_id = str(body.get("document_id") or "").strip()
        file_name = str(body.get("file_name") or "").strip()
        mime_type = str(body.get("mime_type") or "").strip()
        content_base64 = str(body.get("content_base64") or "").strip()
        kind = str(body.get("kind") or "image").strip() or "image"
        if not document_id:
            return {"ok": False, "message": "`document_id` is required."}
        if not file_name:
            return {"ok": False, "message": "`file_name` is required."}
        if not content_base64:
            return {"ok": False, "message": "`content_base64` is required."}
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError):
            return {"ok": False, "message": "Invalid `content_base64` payload."}
        try:
            return self.app.quest_service.save_document_asset(
                quest_id,
                document_id,
                file_name=file_name,
                mime_type=mime_type or None,
                content=content,
                kind=kind,
            )
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def document_save(self, quest_id: str, document_id: str, body: dict) -> dict:
        try:
            return self.app.quest_service.save_document(
                quest_id,
                document_id,
                body["content"],
                previous_revision=body.get("revision"),
            )
        except FileNotFoundError:
            return 404, {"ok": False, "message": f"Unknown quest `{quest_id}`."}

    def latex_init(self, project_id: str, body: dict) -> dict:
        return self.app.latex_service.init_project(
            project_id,
            name=body.get("name", ""),
            parent_id=body.get("parent_id"),
            template=body.get("template"),
            compiler=body.get("compiler"),
        )

    def latex_compile(self, project_id: str, folder_id: str, body: dict) -> dict:
        return self.app.latex_service.compile(
            project_id,
            folder_id,
            compiler=body.get("compiler"),
            main_file_id=body.get("main_file_id"),
            stop_on_first_error=body.get("stop_on_first_error"),
            auto=body.get("auto"),
        )

    def latex_builds(self, project_id: str, folder_id: str, path: str) -> list[dict]:
        query = self.parse_query(path)
        limit_raw = ((query.get("limit") or ["10"])[0] or "10").strip()
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 10
        return self.app.latex_service.list_builds(project_id, folder_id, limit=limit)

    def latex_build(self, project_id: str, folder_id: str, build_id: str) -> dict:
        return self.app.latex_service.get_build(project_id, folder_id, build_id)

    def latex_build_pdf(self, project_id: str, folder_id: str, build_id: str) -> tuple[int, dict, bytes]:
        payload, file_name = self.app.latex_service.get_build_pdf(project_id, folder_id, build_id)
        headers = {
            **self._asset_headers("application/pdf"),
            "Content-Disposition": f'inline; filename="{file_name}"',
        }
        return 200, headers, payload

    def latex_build_log(self, project_id: str, folder_id: str, build_id: str) -> tuple[int, dict, bytes]:
        text = self.app.latex_service.get_build_log_text(project_id, folder_id, build_id)
        return 200, self._asset_headers("text/plain; charset=utf-8"), text.encode("utf-8")

    def latex_archive(self, project_id: str, folder_id: str) -> tuple[int, dict, bytes]:
        payload, file_name = self.app.latex_service.create_sources_archive(project_id, folder_id)
        headers = {
            **self._asset_headers("application/zip"),
            "Content-Disposition": f'attachment; filename="{file_name}"',
        }
        return 200, headers, payload

    def chat(self, quest_id: str, body: dict) -> dict:
        text = body.get("text", "").strip()
        if not text:
            return {"ok": False, "message": "Empty message."}
        source = body.get("source", "api")
        self.app.sessions.bind(quest_id, source)
        payload = self.app.submit_user_message(
            quest_id,
            text=text,
            source=source,
            reply_to_interaction_id=body.get("reply_to_interaction_id"),
            client_message_id=body.get("client_message_id"),
        )
        return {
            "ok": True,
            "ack": f"Received for {quest_id}. Stored and queued for execution.",
            **payload,
        }

    def command(self, quest_id: str, body: dict) -> dict:
        raw_command = body.get("command", "").strip()
        if not raw_command:
            return {"ok": False, "message": "Empty command."}

        source = body.get("source", "api")
        self.app.sessions.bind(quest_id, source)
        normalized_command = raw_command if raw_command.startswith("/") else f"/{raw_command}"
        command_name, args = self.app._parse_prefixed_command(normalized_command, "/")
        if not command_name:
            return {"ok": False, "message": "Empty command."}

        def append_command_reply(kind: str, message: str, **extra: object) -> dict:
            reply = self.app.quest_service.append_message(
                quest_id,
                role="assistant",
                content=message,
                source="command",
            )
            return {
                "ok": True,
                "type": kind,
                "message": message,
                "message_record": reply,
                **extra,
            }

        if command_name == "status":
            snapshot = self.quest(quest_id)
            return append_command_reply("status", self.app._format_status(snapshot), snapshot=snapshot)

        if command_name == "summary":
            return append_command_reply("summary", self.app._format_summary(quest_id))

        if command_name == "metrics":
            run_id = args[0] if args else None
            return append_command_reply("metrics", self.app._format_metrics(quest_id, run_id=run_id), run_id=run_id)

        if command_name == "graph":
            graph = self.graph(quest_id)
            return append_command_reply("graph", self.app._format_graph_reply(quest_id, graph), graph=graph)

        if command_name == "terminal":
            quest_root = self.app.quest_service._quest_root(quest_id)
            workspace_root = self.app.quest_service.active_workspace_root(quest_root)
            session = self.app.bash_exec_service.ensure_terminal_session(
                quest_root,
                quest_id=quest_id,
                cwd=workspace_root,
                source=source,
                conversation_id=source,
                user_id="user:web-react",
            )
            if args and args[0] == "-R":
                restored = self.app.bash_exec_service.terminal_restore_payload(
                    quest_root,
                    str(session.get("bash_id") or ""),
                    command_limit=10,
                    output_limit=40,
                )
                commands = [str(item.get("command") or "").strip() for item in restored.get("latest_commands") or []]
                tail = restored.get("tail") or []
                tail_preview = [
                    str(item.get("line") or "").strip()
                    for item in tail[-4:]
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
                return append_command_reply(
                    "terminal_restore",
                    "\n".join(lines),
                    session=restored.get("session"),
                    restore=restored,
                )
            if args:
                command_text = " ".join(args).rstrip()
                result = self.app.bash_exec_service.append_terminal_input(
                    quest_root,
                    str(session.get("bash_id") or ""),
                    data=f"{command_text}\n",
                    source=source,
                    user_id="user:web-react",
                    conversation_id=source,
                )
                cwd_value = str(result.get("session", {}).get("cwd") or session.get("cwd") or quest_root)
                return append_command_reply(
                    "terminal",
                    f"Sent to terminal `{session.get('bash_id')}` in `{cwd_value}`:\n{command_text}",
                    session=result.get("session"),
                    terminal=result,
                )
            return append_command_reply(
                "terminal",
                f"Terminal `{session.get('bash_id')}` ready.\nstatus: {session.get('status')}\ncwd: {session.get('cwd')}",
                session=session,
            )

        if command_name == "approve":
            if not args:
                return {
                    "ok": False,
                    "message": "Please provide a decision id, for example `/approve decision-001 Proceed`.",
                }
            decision_id = args[0]
            reason = " ".join(args[1:]).strip() or "Approved from local UI."
            approval = self.app.artifact_service.record(
                self.app.quest_service._quest_root(quest_id),
                {
                    "kind": "approval",
                    "decision_id": decision_id,
                    "reason": reason,
                    "source": {
                        "kind": "user",
                        "surface": source,
                    },
                    "raw_text": raw_command,
                },
            )
            return append_command_reply(
                "approve",
                f"Approved {decision_id}. {reason}",
                approval=approval,
                decision_id=decision_id,
            )

        if command_name == "note":
            note = " ".join(args).strip()
            if not note:
                return {"ok": False, "message": "Note text is required, for example `/note revisit baseline`."}
            payload = self.app.submit_user_message(quest_id, text=note, source="command")
            return {"ok": True, "type": "ack", "message": "Note stored and queued.", **payload}

        if command_name in {"pause", "stop", "resume"}:
            target_quest = args[0].strip() if args else quest_id
            if not target_quest:
                return {"ok": False, "message": f"Usage: `/{command_name} <quest_id>`."}
            control = self.app.control_quest(target_quest, action=command_name, source=source)
            fallback_verb = {"pause": "paused", "stop": "stopped", "resume": "resumed"}[command_name]
            message = str(control.get("message") or f"Quest {target_quest} {fallback_verb}.")
            if target_quest == quest_id:
                return append_command_reply(command_name, message, snapshot=control.get("snapshot"), interrupted=control.get("interrupted"))
            reply = self.app.quest_service.append_message(
                target_quest,
                role="assistant",
                content=message,
                source="command",
            )
            return {
                "ok": True,
                "type": command_name,
                "message": message,
                "message_record": reply,
                "snapshot": control.get("snapshot"),
                "interrupted": control.get("interrupted"),
                "target_quest_id": target_quest,
            }

        return {
            "ok": True,
            "type": "ack",
            "message": f"Command `{raw_command}` is accepted by the skeleton but not fully implemented yet.",
        }

    def run_create(self, quest_id: str, body: dict) -> dict:
        quest_root = self.app.quest_service._quest_root(quest_id)
        config = self.app.config_manager.load_named("config")
        runners = self.app.config_manager.load_runners_config()
        snapshot = self.app.quest_service.snapshot(quest_id)
        runner_name = str(body.get("runner") or snapshot.get("runner") or config.get("default_runner", "codex")).strip().lower()
        runner_cfg = runners.get(runner_name, {})
        if runner_cfg.get("enabled") is False:
            return {
                "ok": False,
                "message": f"Runner `{runner_name}` is disabled in `runners.yaml`.",
            }
        try:
            runner = self.app.get_runner(runner_name)
        except KeyError as exc:
            return {
                "ok": False,
                "message": str(exc),
            }
        raw_reasoning_effort = (
            body.get("model_reasoning_effort")
            if "model_reasoning_effort" in body
            else runner_cfg.get("model_reasoning_effort")
        )
        reasoning_effort = (
            str(raw_reasoning_effort).strip()
            if raw_reasoning_effort is not None and str(raw_reasoning_effort).strip()
            else ("xhigh" if raw_reasoning_effort is None else None)
        )
        request = RunRequest(
            quest_id=quest_id,
            quest_root=quest_root,
            worktree_root=self.app.quest_service.active_workspace_root(quest_root),
            run_id=body.get("run_id") or generate_id("run"),
            skill_id=body.get("skill_id", "decision"),
            message=body.get("message", "").strip(),
            model=body.get("model") or runner_cfg.get("model", "gpt-5.4"),
            approval_policy=runner_cfg.get("approval_policy", "on-request"),
            sandbox_mode=runner_cfg.get("sandbox_mode", "workspace-write"),
            turn_reason=body.get("turn_reason") or "user_message",
            reasoning_effort=reasoning_effort,
        )
        result = runner.run(request)
        if result.output_text:
            self.app.quest_service.append_message(
                quest_id,
                role="assistant",
                content=result.output_text,
                source=runner_name,
                run_id=result.run_id,
                skill_id=request.skill_id,
            )
        return {
            "ok": result.ok,
            "runner": runner_name,
            "run_id": result.run_id,
            "model": result.model,
            "exit_code": result.exit_code,
            "history_root": str(result.history_root),
            "run_root": str(result.run_root),
            "output_text": result.output_text,
            "stderr_text": result.stderr_text,
        }

    def memory(self, query: dict[str, list[str]]) -> list[dict]:
        term = (query.get("q") or [""])[0]
        if not term:
            return self.app.memory_service.list_cards(scope="global")
        return self.app.memory_service.search(term, scope="global")

    def docs(self) -> list[dict]:
        docs_root = self.app.repo_root / "docs"
        if not docs_root.exists():
            return []

        entries: list[dict] = []
        for path in sorted(docs_root.rglob("*.md")):
            if not path.is_file():
                continue
            relative = path.relative_to(docs_root).as_posix()
            title = self._markdown_title(path)
            entries.append(
                {
                    "document_id": relative,
                    "title": title,
                    "kind": "markdown",
                    "writable": False,
                    "path": str(path),
                    "source_scope": "system_docs",
                }
            )
        return entries

    def docs_open(self, body: dict) -> dict:
        docs_root = self.app.repo_root / "docs"
        document_id = str(body.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("`document_id` is required.")

        path = resolve_within(docs_root, document_id)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Unknown docs file `{document_id}`.")

        content = read_text(path)
        return {
            "document_id": document_id,
            "title": self._markdown_title(path),
            "path": str(path),
            "kind": "markdown",
            "scope": "system_docs",
            "writable": False,
            "encoding": "utf-8",
            "source_scope": "system_docs",
            "content": content,
            "revision": f"sha256:{sha256_text(content)}",
            "updated_at": utc_now(),
            "meta": {
                "tags": list(path.relative_to(docs_root).parts[:-1]),
                "source_kind": "repo_docs",
                "renderer_hint": "markdown",
            },
        }

    def docs_asset(self, asset_path: str) -> tuple[int, dict, bytes]:
        docs_root = self.app.repo_root / "docs"
        relative = unquote(str(asset_path or "").strip())
        if not relative:
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
        path = resolve_within(docs_root, relative)
        if not path.exists() or not path.is_file():
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, self._asset_headers(mime_type), path.read_bytes()

    def config_files(self) -> list[dict]:
        return [
            {
                "name": item.name,
                "path": str(item.path),
                "required": item.required,
                "exists": item.exists,
            }
            for item in self.app.config_manager.list_files()
        ]

    def config_show(self, name: str) -> dict:
        content = self.app.config_manager.load_named_text(name, create_optional=True)
        path = self.app.config_manager.path_for(name)
        meta: dict[str, object] = {
            "tags": [name],
            "source_kind": "config_file",
            "renderer_hint": "code",
            "help_markdown": self.app.config_manager.help_markdown(name),
            "system_testable": name in {"config", "runners", "connectors"},
            "structured_config": self.app.config_manager.load_named_normalized(name, create_optional=True),
        }
        return {
            "document_id": name,
            "title": path.name,
            "path": str(path),
            "kind": "code",
            "scope": "config",
            "writable": True,
            "encoding": "utf-8",
            "source_scope": "config",
            "content": content,
            "revision": f"sha256:{sha256_text(content)}",
            "updated_at": utc_now(),
            "meta": meta,
        }

    def config_save(self, name: str, body: dict) -> dict:
        if isinstance(body.get("structured"), dict):
            result = self.app.config_manager.save_named_payload(name, body["structured"])
        else:
            result = self.app.config_manager.save_named_text(name, body.get("content", ""))
        if result.get("ok") and name == "config":
            result["runtime_reload"] = self.app.reload_runtime_config()
        if result.get("ok") and name == "connectors":
            result["runtime_reload"] = self.app.reload_connectors_config()
        if result.get("ok") and name == "runners":
            result["runtime_reload"] = self.app.reload_runners_config()
        return result

    def config_validate(self, body: dict | None = None) -> dict:
        if body and "name" in body and isinstance(body.get("structured"), dict):
            return self.app.config_manager.validate_named_payload(body["name"], body["structured"])
        if body and "name" in body and "content" in body:
            return self.app.config_manager.validate_named_text(body["name"], body["content"])
        return self.app.config_manager.validate_all()

    def config_test(self, body: dict | None = None) -> dict:
        if not body or "name" not in body:
            return {"ok": False, "summary": "Config test requires `name` and `content`."}
        if isinstance(body.get("structured"), dict):
            return self.app.config_manager.test_named_payload(
                body["name"],
                body["structured"],
                live=bool(body.get("live", True)),
                delivery_targets=body.get("delivery_targets"),
            )
        if "content" not in body:
            return {"ok": False, "summary": "Config test requires `name` and `content`."}
        return self.app.config_manager.test_named_text(body["name"], body["content"], live=bool(body.get("live", True)))

    def asset(self, asset_path: str) -> tuple[int, dict, bytes]:
        candidate_roots = [
            self.app.repo_root / "src" / "ui" / "public" / "assets",
            self.app.repo_root / "assets",
        ]
        path = None
        for root in candidate_roots:
            candidate = resolve_within(root, asset_path)
            if candidate.exists() and candidate.is_file():
                path = candidate
                break
        if path is None:
            return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"Not Found"
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, {"Content-Type": mime_type}, path.read_bytes()

    @staticmethod
    def parse_query(path: str) -> dict[str, list[str]]:
        if "?" not in path:
            return {}
        return parse_qs(path.split("?", 1)[1], keep_blank_values=True)


    @staticmethod
    def parse_body(raw: bytes) -> dict:
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _file_change_workspace_root(run_artifact: dict, record: dict) -> Path | None:
        workspace_root = str(run_artifact.get("workspace_root") or record.get("workspace_root") or "").strip()
        if not workspace_root:
            return None
        return Path(workspace_root).expanduser()

    @staticmethod
    def _file_change_path_candidates(raw_path: str, workspace_root: Path | None) -> list[Path]:
        text = str(raw_path or "").strip()
        if not text:
            return []
        raw_candidate = Path(text).expanduser()
        candidates: list[Path] = []
        if raw_candidate.is_absolute():
            candidates.append(raw_candidate)
        elif workspace_root is not None:
            candidates.append(workspace_root / raw_candidate)
        else:
            candidates.append(raw_candidate)
        if workspace_root is not None:
            candidates.append(workspace_root)

        resolved: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            for variant in (candidate, candidate.resolve(strict=False)):
                key = str(variant)
                if key in seen:
                    continue
                seen.add(key)
                resolved.append(variant)
        return resolved

    @staticmethod
    def _git_probe_root(candidate: Path) -> Path:
        if candidate.exists():
            return candidate if candidate.is_dir() else candidate.parent
        for parent in candidate.parents:
            if parent.exists():
                return parent
        return candidate.parent

    def _resolve_git_repo_root_for_file_change(self, raw_path: str, workspace_root: Path | None) -> Path | None:
        for candidate in self._file_change_path_candidates(raw_path, workspace_root):
            probe_root = self._git_probe_root(candidate)
            if not str(probe_root).strip():
                continue
            result = run_command(["git", "rev-parse", "--show-toplevel"], cwd=probe_root, check=False)
            if result.returncode != 0:
                continue
            top_level = result.stdout.strip()
            if top_level:
                return Path(top_level).resolve()
        return None

    def _relative_file_change_path(self, repo_root: Path | None, raw_path: str, workspace_root: Path | None) -> str | None:
        if repo_root is None:
            if Path(str(raw_path or "").strip()).is_absolute():
                return None
            normalized = str(raw_path or "").strip().replace("\\", "/").lstrip("/")
            return normalized or None

        repo_root_resolved = repo_root.resolve()
        for candidate in self._file_change_path_candidates(raw_path, workspace_root):
            try:
                return candidate.relative_to(repo_root_resolved).as_posix()
            except ValueError:
                continue
        if Path(str(raw_path or "").strip()).is_absolute():
            return None
        normalized = str(raw_path or "").strip().replace("\\", "/").lstrip("/")
        return normalized or None

    @staticmethod
    def _display_file_change_path(quest_root: Path, raw_path: str, *, relative_path: str | None = None) -> str:
        quest_root_resolved = quest_root.resolve()
        for candidate in [Path(str(raw_path or "").strip()).expanduser()]:
            for variant in (candidate, candidate.resolve(strict=False)):
                try:
                    relative = variant.relative_to(quest_root_resolved)
                except ValueError:
                    continue
                parts = relative.parts
                if len(parts) >= 3 and parts[0] == ".ds" and parts[1] == "worktrees":
                    branch_root = parts[2]
                    remainder = Path(*parts[3:]).as_posix() if len(parts) > 3 else ""
                    return f"{branch_root}/{remainder}" if remainder else branch_root
                return relative.as_posix()
        if relative_path:
            return relative_path
        text = str(raw_path or "").strip()
        return Path(text).name or text

    @staticmethod
    def _file_change_diff_unavailable(
        *,
        raw_path: str,
        run_id: str | None,
        event_id: str | None,
        message: str,
        ok: bool,
        base: str = "",
        head: str = "",
        branch: str | None = None,
        relative_path: str | None = None,
        display_path: str | None = None,
    ) -> dict:
        normalized_path = relative_path or str(raw_path or "").strip()
        return {
            "ok": ok,
            "available": False,
            "source": "unavailable",
            "run_id": run_id,
            "event_id": event_id,
            "branch": branch,
            "display_path": display_path or normalized_path,
            "base": base,
            "head": head,
            "path": normalized_path,
            "old_path": None,
            "status": "modified",
            "binary": False,
            "added": 0,
            "removed": 0,
            "lines": [],
            "truncated": False,
            "message": message,
        }

    @staticmethod
    def _markdown_title(path: Path) -> str:
        content = read_text(path)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip() or path.stem.replace("_", " ")
        return path.stem.replace("_", " ").replace("-", " ")

    @staticmethod
    def error(message: str, code: int = 400) -> tuple[int, dict]:
        return code, {"ok": False, "message": message}
