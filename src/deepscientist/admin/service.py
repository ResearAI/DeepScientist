from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any
from urllib.parse import urlencode

from .. import __version__ as DEEPSCIENTIST_VERSION
from ..diagnostics import diagnose_runner_failure
from ..doctor import _read_runtime_failure_record
from ..runtime_tools import RuntimeToolService
from ..shared import ensure_dir, read_json, read_jsonl_tail, read_text, sha256_text, utc_now, utf8_text_subprocess_kwargs, which, write_json
from .charts import AdminChartService, AdminMetricsCollector
from .logs import AdminLogService
from .system_info import AdminSystemMonitor, collect_system_hardware
from .tool_metrics import AdminToolMetricsService


_FAILURE_LOOKBACK = timedelta(days=7)
_ISSUE_REPOSITORY = "ResearAI/DeepScientist"
_MAX_ISSUE_SOURCE_MARKDOWN_BYTES = 512 * 1024
_MAX_FALLBACK_URL_LENGTH = 7500


class AdminService:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.home = Path(app.home)
        self.log_service = AdminLogService(self.home)
        self.system_monitor = AdminSystemMonitor(self.home)
        self.tool_metrics_service = AdminToolMetricsService(self.home, logger=getattr(app, "logger", None))
        self.chart_service = AdminChartService(app, self)
        self.metrics_collector = AdminMetricsCollector(
            self.home,
            build_fleet_snapshot=self.fleet_snapshot,
            sync_tool_metrics=self.tool_metrics_service.catch_up,
            prune_tool_metrics=lambda current=None: self.tool_metrics_service.prune(current=current),
            logger=getattr(app, "logger", None),
        )

    def overview(self) -> dict[str, Any]:
        quests = self.app.quest_service.list_quests()
        connectors = self.app.list_connector_statuses()
        quest_insights = self._quest_insights(quests)
        connector_health = self._connector_health_summary(connectors)
        tasks = self.app.admin_task_service.list_tasks(limit=50)
        task_health = self._task_health_summary(tasks)
        active_quests = [
            item
            for item in quests
            if str(item.get("runtime_status") or item.get("status") or "").strip().lower() in {"running", "active"}
            or str(item.get("active_run_id") or "").strip()
        ]
        pending_decisions = sum(int((item.get("counts") or {}).get("pending_decision_count") or 0) for item in quests)
        queued_messages = sum(int((item.get("counts") or {}).get("pending_user_message_count") or 0) for item in quests)
        running_bash = sum(int((item.get("counts") or {}).get("bash_running_count") or 0) for item in quests)
        failures = self.failure_records(limit=200)
        latest_failure = failures[0] if failures else None
        hardware_summary = self.system_hardware(refresh=False)
        return {
            "ok": True,
            "generated_at": utc_now(),
            "daemon": self.app.handlers.health(),
            "cli_health": self.app.handlers.cli_health(),
            "system_update": self.app.admin_task_service.cached_result("system_update.json"),
            "doctor": self.app.admin_task_service.cached_result("doctor.json"),
            "totals": {
                "quests_total": len(quests),
                "quests_active": len(active_quests),
                "pending_decisions_total": pending_decisions,
                "queued_user_messages_total": queued_messages,
                "running_bash_total": running_bash,
                "connectors_total": len(connectors),
                "connectors_enabled": sum(1 for item in connectors if bool(item.get("enabled"))),
                "connectors_degraded": int(connector_health.get("degraded_total") or 0),
                "open_repairs": sum(1 for item in self.app.admin_repair_service.list_repairs(limit=200) if str(item.get("status") or "") == "open"),
                "tasks_running": int(task_health.get("running_total") or 0),
                "tasks_failed": int(task_health.get("failed_total") or 0),
                "runtime_failures_last_7d": len(failures),
                "quests_updated_last_24h": int(
                    ((quest_insights.get("recent_activity") or {}) if isinstance(quest_insights.get("recent_activity"), dict) else {}).get("updated_last_24h")
                    or 0
                ),
            },
            "latest_failure": latest_failure,
            "latest_failure_scanned": True,
            "system_hardware": hardware_summary,
            "quest_insights": quest_insights,
            "connector_health": connector_health,
            "task_health": task_health,
            "quests": quests[:12],
            "connectors": connectors[:12],
            "tasks": tasks[:12],
        }

    def fleet_snapshot(self) -> dict[str, Any]:
        quests = self.app.quest_service.list_quests()
        connectors = self.app.list_connector_statuses()
        tasks = self.app.admin_task_service.list_tasks(limit=200)
        quest_insights = self._quest_insights(quests)
        connector_health = self._connector_health_summary(connectors)
        task_health = self._task_health_summary(tasks)
        return {
            "recorded_at": utc_now(),
            "sampling_version": 1,
            "runtime": {
                "quests_total": len(quests),
                "active_quests": sum(
                    1
                    for item in quests
                    if self._normalize_label(item.get("runtime_status") or item.get("status")) in {"running", "active"}
                    or str(item.get("active_run_id") or "").strip()
                ),
                "pending_decisions_total": sum(int((item.get("counts") or {}).get("pending_decision_count") or 0) for item in quests),
                "queued_user_messages_total": sum(int((item.get("counts") or {}).get("pending_user_message_count") or 0) for item in quests),
                "running_bash_total": sum(int((item.get("counts") or {}).get("bash_running_count") or 0) for item in quests),
                "running_tasks": int(task_health.get("running_total") or 0),
                "failed_tasks": int(task_health.get("failed_total") or 0),
                "degraded_connectors": int(connector_health.get("degraded_total") or 0),
            },
            "distributions": {
                "status_counts": quest_insights.get("status_counts") or {},
                "anchor_counts": quest_insights.get("anchor_counts") or {},
                "workspace_mode_counts": quest_insights.get("workspace_mode_counts") or {},
                "runner_counts": quest_insights.get("runner_counts") or {},
                "task_status_counts": task_health.get("status_counts") or {},
                "task_kind_counts": task_health.get("kind_counts") or {},
                "connector_state_counts": connector_health.get("state_counts") or {},
            },
        }

    def quests(self, *, limit: int = 100) -> dict[str, Any]:
        items = self.app.quest_service.list_quests()[: max(1, limit)]
        return {
            "ok": True,
            "items": items,
            "total": len(self.app.quest_service.list_quests()),
        }

    def quest_summary(self, quest_id: str) -> dict[str, Any]:
        snapshot = self.app.quest_service.snapshot(quest_id)
        return {
            "ok": True,
            "snapshot": snapshot,
            "workflow_preview": self.app.quest_service.workflow(quest_id),
            "recent_failures": [item for item in self.failure_records(limit=200) if str(item.get("quest_id") or "") == quest_id][:10],
        }

    def runtime_sessions(self, *, limit: int = 200) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        per_quest_limit = max(5, min(50, max(1, limit)))
        for quest in self.app.quest_service.list_quests():
            quest_id = str(quest.get("quest_id") or "").strip()
            if not quest_id:
                continue
            quest_root = self.app.quest_service._quest_root(quest_id)
            for session in self.app.bash_exec_service.list_sessions(quest_root, limit=per_quest_limit):
                items.append(
                    {
                        "quest_id": quest_id,
                        "quest_title": quest.get("title"),
                        **dict(session),
                    }
                )
        items.sort(
            key=lambda item: (
                str(item.get("updated_at") or item.get("started_at") or ""),
                str(item.get("quest_id") or ""),
            ),
            reverse=True,
        )
        return {
            "ok": True,
            "items": items[: max(1, limit)],
            "total": len(items),
        }

    def log_sources(self) -> dict[str, Any]:
        return {"ok": True, "items": self.log_service.list_sources()}

    def log_tail(self, source: str, *, line_count: int = 200) -> dict[str, Any]:
        return {"ok": True, **self.log_service.tail(source, line_count=line_count)}

    @staticmethod
    def _parse_iso(value: object) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        candidate = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _normalize_label(value: object, *, default: str = "unknown") -> str:
        normalized = str(value or "").strip().lower()
        return normalized or default

    @staticmethod
    def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
        return {key: counter[key] for key, _value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))}

    def _quest_focus_item(self, quest: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(UTC)
        counts = quest.get("counts") if isinstance(quest.get("counts"), dict) else {}
        updated_at = self._parse_iso(quest.get("updated_at"))
        age_hours = round(max((current - updated_at).total_seconds(), 0.0) / 3600.0, 1) if updated_at is not None else None
        return {
            "quest_id": str(quest.get("quest_id") or "").strip(),
            "title": str(quest.get("title") or quest.get("quest_id") or "").strip() or None,
            "runtime_status": str(quest.get("runtime_status") or quest.get("status") or "").strip() or None,
            "active_anchor": str(quest.get("active_anchor") or "").strip() or None,
            "workspace_mode": str(quest.get("workspace_mode") or "").strip() or None,
            "runner": str(quest.get("runner") or "").strip() or None,
            "updated_at": updated_at.isoformat() if updated_at is not None else (str(quest.get("updated_at") or "").strip() or None),
            "pending_decisions": int(counts.get("pending_decision_count") or 0),
            "pending_user_messages": int(counts.get("pending_user_message_count") or 0),
            "running_bash": int(counts.get("bash_running_count") or 0),
            "status_line": str(((quest.get("summary") or {}) if isinstance(quest.get("summary"), dict) else {}).get("status_line") or "").strip() or None,
            "age_hours": age_hours,
        }

    def _quest_insights(self, quests: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(UTC)
        status_counts = Counter(self._normalize_label(item.get("runtime_status") or item.get("status")) for item in quests)
        anchor_counts = Counter(self._normalize_label(item.get("active_anchor")) for item in quests)
        workspace_mode_counts = Counter(self._normalize_label(item.get("workspace_mode"), default="quest") for item in quests)
        runner_counts = Counter(self._normalize_label(item.get("runner"), default="codex") for item in quests)

        decision_backlog_buckets: Counter[str] = Counter()
        message_backlog_buckets: Counter[str] = Counter()
        updated_last_24h = 0
        updated_last_7d = 0
        created_last_7d = 0
        stale_over_7d = 0
        updated_by_day: Counter[str] = Counter()
        created_by_day: Counter[str] = Counter()

        focus_items = [self._quest_focus_item(item, now=now) for item in quests]
        for quest in quests:
            counts = quest.get("counts") if isinstance(quest.get("counts"), dict) else {}
            pending_decisions = int(counts.get("pending_decision_count") or 0)
            pending_messages = int(counts.get("pending_user_message_count") or 0)
            updated_at = self._parse_iso(quest.get("updated_at"))
            created_at = self._parse_iso(quest.get("created_at"))

            if pending_decisions <= 0:
                decision_backlog_buckets["none"] += 1
            elif pending_decisions == 1:
                decision_backlog_buckets["one"] += 1
            elif pending_decisions <= 3:
                decision_backlog_buckets["two_to_three"] += 1
            else:
                decision_backlog_buckets["four_plus"] += 1

            if pending_messages <= 0:
                message_backlog_buckets["none"] += 1
            elif pending_messages == 1:
                message_backlog_buckets["one"] += 1
            elif pending_messages <= 3:
                message_backlog_buckets["two_to_three"] += 1
            else:
                message_backlog_buckets["four_plus"] += 1

            if updated_at is not None:
                updated_by_day[updated_at.date().isoformat()] += 1
                if updated_at >= now - timedelta(hours=24):
                    updated_last_24h += 1
                if updated_at >= now - timedelta(days=7):
                    updated_last_7d += 1
                else:
                    stale_over_7d += 1
            if created_at is not None:
                created_by_day[created_at.date().isoformat()] += 1
                if created_at >= now - timedelta(days=7):
                    created_last_7d += 1

        def _updated_rank(item: dict[str, Any]) -> str:
            return str(item.get("updated_at") or "")

        active_watchlist = [
            item
            for item in focus_items
            if self._normalize_label(item.get("runtime_status")) in {"running", "active"}
            or int(item.get("running_bash") or 0) > 0
        ]
        active_watchlist.sort(
            key=lambda item: (
                int(item.get("running_bash") or 0),
                int(item.get("pending_decisions") or 0),
                float(item.get("age_hours") or 0.0),
                _updated_rank(item),
            ),
            reverse=True,
        )

        top_pending_decisions = [item for item in focus_items if int(item.get("pending_decisions") or 0) > 0]
        top_pending_decisions.sort(
            key=lambda item: (int(item.get("pending_decisions") or 0), int(item.get("pending_user_messages") or 0), _updated_rank(item)),
            reverse=True,
        )

        top_waiting_messages = [item for item in focus_items if int(item.get("pending_user_messages") or 0) > 0]
        top_waiting_messages.sort(
            key=lambda item: (int(item.get("pending_user_messages") or 0), int(item.get("pending_decisions") or 0), _updated_rank(item)),
            reverse=True,
        )

        recently_updated = sorted(focus_items, key=_updated_rank, reverse=True)

        activity_timeline_7d = []
        for offset in range(6, -1, -1):
            day = (now - timedelta(days=offset)).date()
            day_key = day.isoformat()
            activity_timeline_7d.append(
                {
                    "date": day_key,
                    "label": day.strftime("%m-%d"),
                    "quests_created": int(created_by_day.get(day_key) or 0),
                    "quests_updated": int(updated_by_day.get(day_key) or 0),
                }
            )

        return {
            "status_counts": self._sorted_counter(status_counts),
            "anchor_counts": self._sorted_counter(anchor_counts),
            "workspace_mode_counts": self._sorted_counter(workspace_mode_counts),
            "runner_counts": self._sorted_counter(runner_counts),
            "recent_activity": {
                "updated_last_24h": updated_last_24h,
                "updated_last_7d": updated_last_7d,
                "created_last_7d": created_last_7d,
                "stale_over_7d": stale_over_7d,
            },
            "decision_backlog_buckets": {
                "none": int(decision_backlog_buckets.get("none") or 0),
                "one": int(decision_backlog_buckets.get("one") or 0),
                "two_to_three": int(decision_backlog_buckets.get("two_to_three") or 0),
                "four_plus": int(decision_backlog_buckets.get("four_plus") or 0),
            },
            "message_backlog_buckets": {
                "none": int(message_backlog_buckets.get("none") or 0),
                "one": int(message_backlog_buckets.get("one") or 0),
                "two_to_three": int(message_backlog_buckets.get("two_to_three") or 0),
                "four_plus": int(message_backlog_buckets.get("four_plus") or 0),
            },
            "activity_timeline_7d": activity_timeline_7d,
            "top_pending_decisions": top_pending_decisions[:6],
            "top_waiting_messages": top_waiting_messages[:6],
            "recently_updated": recently_updated[:6],
            "active_watchlist": active_watchlist[:6],
        }

    def _connector_health_summary(self, connectors: list[dict[str, Any]]) -> dict[str, Any]:
        state_counts = Counter()
        degraded_items: list[dict[str, Any]] = []
        for item in connectors:
            state = self._normalize_label(item.get("connection_state"), default="unknown")
            if state == "unknown":
                state = "enabled" if bool(item.get("enabled")) else "disabled"
            state_counts[state] += 1
            if str(item.get("last_error") or "").strip() or state in {"error", "offline", "degraded"}:
                degraded_items.append(
                    {
                        "name": item.get("name"),
                        "connection_state": state,
                        "enabled": bool(item.get("enabled")),
                        "last_error": item.get("last_error"),
                    }
                )
        return {
            "state_counts": self._sorted_counter(state_counts),
            "degraded_total": len(degraded_items),
            "degraded_items": degraded_items[:8],
        }

    def _task_health_summary(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts = Counter(self._normalize_label(item.get("status")) for item in tasks)
        kind_counts = Counter(self._normalize_label(item.get("kind"), default="unknown") for item in tasks)
        active_items = [
            item
            for item in tasks
            if self._normalize_label(item.get("status")) in {"queued", "running", "active"}
        ]
        failed_items = [
            item
            for item in tasks
            if self._normalize_label(item.get("status")) in {"failed", "error"}
        ]
        return {
            "total": len(tasks),
            "status_counts": self._sorted_counter(status_counts),
            "kind_counts": self._sorted_counter(kind_counts),
            "queued_total": sum(1 for item in tasks if self._normalize_label(item.get("status")) == "queued"),
            "running_total": sum(1 for item in tasks if self._normalize_label(item.get("status")) in {"running", "active"}),
            "failed_total": len(failed_items),
            "active_items": active_items[:8],
            "failed_items": failed_items[:8],
        }

    def _latest_failure_candidate(self, *, cutoff: datetime) -> dict[str, Any] | None:
        quests_root = self.home / "quests"
        if not quests_root.exists():
            return None
        event_files: list[tuple[float, Path, Path]] = []
        for quest_root in quests_root.glob("*/"):
            event_path = quest_root / ".ds" / "events.jsonl"
            if not event_path.exists():
                continue
            try:
                mtime = event_path.stat().st_mtime
            except OSError:
                continue
            event_files.append((mtime, quest_root, event_path))

        best: dict[str, Any] | None = None
        for mtime, quest_root, event_path in sorted(event_files, key=lambda item: item[0], reverse=True):
            if best is not None and mtime <= float(best.get("_created_at_ts") or 0.0):
                break
            for event in reversed(read_jsonl_tail(event_path, 120)):
                event_type = str(event.get("type") or "").strip()
                if event_type not in {"runner.turn_error", "runner.turn_retry_exhausted", "quest.runtime_auto_resume_suppressed"}:
                    continue
                created_at = self._parse_iso(event.get("created_at"))
                if created_at is None or created_at < cutoff:
                    continue
                candidate = {
                    "quest_id": quest_root.name,
                    "event_type": event_type,
                    "run_id": str(event.get("run_id") or "").strip() or None,
                    "created_at": created_at.isoformat(),
                    "summary": str(event.get("summary") or "").strip(),
                    "_quest_root": str(quest_root),
                    "_created_at_ts": created_at.timestamp(),
                }
                if best is None or float(candidate["_created_at_ts"]) > float(best.get("_created_at_ts") or 0.0):
                    best = candidate
                break
        return best

    def failure_records(self, *, limit: int = 100) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC) - _FAILURE_LOOKBACK
        candidates: list[dict[str, Any]] = []
        quests_root = self.home / "quests"
        if not quests_root.exists():
            return candidates

        if limit == 1:
            latest_candidate = self._latest_failure_candidate(cutoff=cutoff)
            if latest_candidate is not None:
                candidates = [latest_candidate]
        else:
            tail_limit = 120 if limit <= 20 else 400
            for quest_root in sorted(quests_root.glob("*/")):
                quest_id = quest_root.name
                for event in reversed(read_jsonl_tail(quest_root / ".ds" / "events.jsonl", tail_limit)):
                    event_type = str(event.get("type") or "").strip()
                    if event_type not in {"runner.turn_error", "runner.turn_retry_exhausted", "quest.runtime_auto_resume_suppressed"}:
                        continue
                    created_at = self._parse_iso(event.get("created_at"))
                    if created_at is None or created_at < cutoff:
                        continue
                    candidates.append(
                        {
                            "quest_id": quest_id,
                            "event_type": event_type,
                            "run_id": str(event.get("run_id") or "").strip() or None,
                            "created_at": created_at.isoformat(),
                            "summary": str(event.get("summary") or "").strip(),
                            "_quest_root": str(quest_root),
                        }
                    )
                    break
            candidates.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
            latest = _read_runtime_failure_record(self.home)
            if latest and all(
                str(item.get("quest_id") or "") != str(latest.get("quest_id") or "")
                or str(item.get("run_id") or "") != str(latest.get("run_id") or "")
                for item in candidates
            ):
                candidates.insert(0, latest)

        selected = candidates[: max(1, limit)]
        items: list[dict[str, Any]] = []
        for item in selected:
            if "diagnosis" in item:
                items.append(item)
                continue
            quest_root_value = str(item.get("_quest_root") or "").strip()
            quest_root = Path(quest_root_value) if quest_root_value else None
            run_id = str(item.get("run_id") or "").strip() or None
            stderr_text = ""
            output_text = ""
            if quest_root and run_id:
                run_root = quest_root / ".ds" / "runs" / run_id
                result_payload = read_json(run_root / "result.json", {})
                if isinstance(result_payload, dict):
                    stderr_text = str(result_payload.get("stderr_text") or "").strip()
                    output_text = str(result_payload.get("output_text") or "").strip()
                if not stderr_text:
                    stderr_text = read_text(run_root / "stderr.txt", "")
            diagnosis = diagnose_runner_failure(
                runner_name="codex",
                summary=str(item.get("summary") or ""),
                stderr_text=stderr_text,
                output_text=output_text,
            )
            items.append(
                {
                    "quest_id": item.get("quest_id"),
                    "event_type": item.get("event_type"),
                    "run_id": run_id,
                    "created_at": item.get("created_at"),
                    "summary": item.get("summary"),
                    "diagnosis": diagnosis.__dict__ if diagnosis is not None else None,
                    "stderr_excerpt": stderr_text[:800] if stderr_text else None,
                    "output_excerpt": output_text[:800] if output_text else None,
                }
            )
        return items

    def failures(self, *, limit: int = 100) -> dict[str, Any]:
        return {"ok": True, "items": self.failure_records(limit=limit)}

    def error_console(self, *, limit: int = 100) -> dict[str, Any]:
        connectors = self.app.list_connector_statuses()
        degraded_connectors = [
            {
                "name": item.get("name"),
                "connection_state": item.get("connection_state"),
                "last_error": item.get("last_error"),
            }
            for item in connectors
            if str(item.get("last_error") or "").strip()
            or str(item.get("connection_state") or "").strip().lower() in {"error", "offline", "degraded"}
        ]
        daemon_errors = [
            item
            for item in reversed(read_jsonl_tail(self.home / "logs" / "daemon.jsonl", max(50, limit * 2)))
            if str(item.get("level") or "").strip().lower() in {"error", "warning"}
        ][: max(1, limit)]
        failed_tasks = [
            item
            for item in self.app.admin_task_service.list_tasks(limit=max(50, limit * 2))
            if str(item.get("status") or "").strip().lower() == "failed"
        ][: max(1, limit)]
        failures = self.failure_records(limit=limit)
        return {
            "ok": True,
            "generated_at": utc_now(),
            "totals": {
                "degraded_connectors": len(degraded_connectors),
                "runtime_failures": len(failures),
                "daemon_errors": len(daemon_errors),
                "failed_tasks": len(failed_tasks),
            },
            "degraded_connectors": degraded_connectors,
            "runtime_failures": failures,
            "daemon_errors": daemon_errors,
            "failed_tasks": failed_tasks,
        }

    def runtime_tools(self) -> dict[str, Any]:
        return {"ok": True, "items": RuntimeToolService(self.home).all_statuses()}

    @property
    def system_hardware_cache_path(self) -> Path:
        return self.home / "runtime" / "admin" / "cache" / "system_hardware.json"

    def _hardware_preferences(self) -> dict[str, Any]:
        config = self.app.config_manager.load_runtime_config()
        hardware = config.get("hardware") if isinstance(config.get("hardware"), dict) else {}
        selection_mode = str(hardware.get("gpu_selection_mode") or "all").strip().lower() or "all"
        if selection_mode not in {"all", "selected"}:
            selection_mode = "all"
        selected_gpu_ids = []
        for item in hardware.get("selected_gpu_ids") or []:
            normalized = str(item or "").strip()
            if normalized and normalized not in selected_gpu_ids:
                selected_gpu_ids.append(normalized)
        return {
            "gpu_selection_mode": selection_mode,
            "selected_gpu_ids": selected_gpu_ids,
            "include_system_hardware_in_prompt": bool(hardware.get("include_system_hardware_in_prompt", True)),
        }

    def _memory_preferences(self) -> dict[str, Any]:
        config = self.app.config_manager.load_runtime_config()
        memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        return {
            "read_visibility_mode": self.app.memory_service.normalize_read_visibility_mode(
                memory.get("read_visibility_mode")
            ),
        }

    @staticmethod
    def _effective_gpu_ids(*, gpus: list[dict[str, Any]], selection_mode: str, selected_gpu_ids: list[str]) -> list[str]:
        available_ids = [str(item.get("gpu_id") or "").strip() for item in gpus if str(item.get("gpu_id") or "").strip()]
        if selection_mode != "selected":
            return available_ids
        return [item for item in selected_gpu_ids if item in available_ids]

    @staticmethod
    def _prompt_hardware_summary(*, system_payload: dict[str, Any], preferences: dict[str, Any]) -> str:
        cpu = system_payload.get("cpu") if isinstance(system_payload.get("cpu"), dict) else {}
        memory = system_payload.get("memory") if isinstance(system_payload.get("memory"), dict) else {}
        disks = system_payload.get("disks") if isinstance(system_payload.get("disks"), list) else []
        gpus = system_payload.get("gpus") if isinstance(system_payload.get("gpus"), list) else []
        effective_gpu_ids = preferences.get("effective_gpu_ids") if isinstance(preferences.get("effective_gpu_ids"), list) else []
        cpu_text = str(cpu.get("model") or "unknown cpu").strip()
        core_text = str(cpu.get("logical_cores") or "unknown").strip()
        memory_text = str(memory.get("total_gb") or "unknown").strip()
        disk_text = "unknown"
        if disks and isinstance(disks[0], dict):
            disk_text = f"{disks[0].get('free_gb') or 'unknown'}GB free on {disks[0].get('mount') or '/'}"
        if gpus:
            gpu_parts = []
            for item in gpus[:8]:
                gpu_id = str(item.get("gpu_id") or "").strip()
                name = str(item.get("name") or "GPU").strip()
                memory_total = item.get("memory_total_gb")
                gpu_parts.append(f"{gpu_id}:{name}{f' {memory_total}GB' if memory_total is not None else ''}")
            gpu_summary = "; ".join(gpu_parts)
        else:
            gpu_summary = "no GPU detected"
        selected = ",".join(effective_gpu_ids) if effective_gpu_ids else ("none" if preferences.get("gpu_selection_mode") == "selected" else "all")
        return f"CPU: {cpu_text} ({core_text} logical cores) | Memory: {memory_text}GB | Disk: {disk_text} | GPUs: {gpu_summary} | Selected GPUs: {selected}"

    def system_hardware(self, *, refresh: bool = True) -> dict[str, Any]:
        system_payload = collect_system_hardware(self.home)
        system_payload["generated_at"] = utc_now()
        preferences = self._hardware_preferences()
        memory_preferences = self._memory_preferences()
        gpus = [dict(item) for item in (system_payload.get("gpus") or []) if isinstance(item, dict)]
        effective_gpu_ids = self._effective_gpu_ids(
            gpus=gpus,
            selection_mode=str(preferences.get("gpu_selection_mode") or "all"),
            selected_gpu_ids=list(preferences.get("selected_gpu_ids") or []),
        )
        available_gpu_ids = [str(item.get("gpu_id") or "").strip() for item in gpus if str(item.get("gpu_id") or "").strip()]
        preferences = {
            **preferences,
            "available_gpu_ids": available_gpu_ids,
            "available_gpu_count": len(available_gpu_ids),
            "effective_gpu_ids": effective_gpu_ids,
            "cuda_visible_devices": ",".join(effective_gpu_ids) if effective_gpu_ids else None,
        }
        prompt_summary = self._prompt_hardware_summary(system_payload=system_payload, preferences=preferences)
        for item in gpus:
            item["selected"] = str(item.get("gpu_id") or "").strip() in effective_gpu_ids
        if refresh:
            latest_sample = self.system_monitor.sample_now(persist=True)
            recent_stats = self.system_monitor.latest_summary(window_minutes=60)
        else:
            recent_stats = self.system_monitor.latest_summary(window_minutes=60)
            latest_sample = recent_stats.get("latest_sample")
            if latest_sample is None:
                latest_sample = self.system_monitor.sample_now(persist=True)
                recent_stats = self.system_monitor.latest_summary(window_minutes=60)
        payload = {
            "ok": True,
            "generated_at": system_payload.get("generated_at"),
            "system": system_payload,
            "preferences": preferences,
            "memory_preferences": memory_preferences,
            "prompt_hardware_summary": prompt_summary,
            "latest_sample": latest_sample,
            "recent_stats": recent_stats,
        }
        write_json(self.system_hardware_cache_path, payload)
        return payload

    def update_system_hardware_preferences(
        self,
        *,
        gpu_selection_mode: str | None = None,
        selected_gpu_ids: list[str] | None = None,
        include_system_hardware_in_prompt: bool | None = None,
        memory_read_visibility_mode: str | None = None,
    ) -> dict[str, Any]:
        config = self.app.config_manager.load_runtime_config()
        hardware = config.get("hardware") if isinstance(config.get("hardware"), dict) else {}
        memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        if gpu_selection_mode is not None:
            normalized_mode = str(gpu_selection_mode or "all").strip().lower() or "all"
            hardware["gpu_selection_mode"] = normalized_mode if normalized_mode in {"all", "selected"} else "all"
        if selected_gpu_ids is not None:
            deduped: list[str] = []
            for item in selected_gpu_ids:
                normalized = str(item or "").strip()
                if normalized and normalized not in deduped:
                    deduped.append(normalized)
            hardware["selected_gpu_ids"] = deduped
        if include_system_hardware_in_prompt is not None:
            hardware["include_system_hardware_in_prompt"] = bool(include_system_hardware_in_prompt)
        if memory_read_visibility_mode is not None:
            memory["read_visibility_mode"] = self.app.memory_service.normalize_read_visibility_mode(
                memory_read_visibility_mode
            )
        config["hardware"] = hardware
        config["memory"] = memory
        save_result = self.app.config_manager.save_named_payload("config", config)
        runtime_reload = self.app.reload_runtime_config()
        payload = self.system_hardware()
        payload["save_result"] = save_result
        payload["runtime_reload"] = runtime_reload
        return payload

    def audit(self, *, limit: int = 200) -> dict[str, Any]:
        audit_path = self.home / "logs" / "admin" / "audit.jsonl"
        return {
            "ok": True,
            "items": list(reversed(read_jsonl_tail(audit_path, max(1, limit)))),
        }

    def write_audit(self, *, action: str, source: str = "admin-ui", **payload: Any) -> dict[str, Any]:
        from ..shared import append_jsonl, ensure_dir

        record = {
            "action": str(action or "").strip(),
            "source": str(source or "").strip() or "admin-ui",
            "created_at": utc_now(),
            "payload": payload,
        }
        audit_path = ensure_dir(self.home / "logs" / "admin") / "audit.jsonl"
        append_jsonl(audit_path, record)
        return record

    def stats_summary(self) -> dict[str, Any]:
        quests = self.app.quest_service.list_quests()
        connectors = self.app.list_connector_statuses()
        connector_health = self._connector_health_summary(connectors)
        tasks = self.app.admin_task_service.list_tasks(limit=200)
        task_health = self._task_health_summary(tasks)
        quest_insights = self._quest_insights(quests)
        failures = self.failure_records(limit=500)
        failure_type_counts = Counter(self._normalize_label(item.get("event_type")) for item in failures)
        return {
            "ok": True,
            "generated_at": utc_now(),
            "totals": {
                "quests": len(quests),
                "active_quests": sum(
                    1
                    for item in quests
                    if self._normalize_label(item.get("runtime_status") or item.get("status")) in {"running", "active"}
                    or str(item.get("active_run_id") or "").strip()
                ),
                "pending_decisions_total": sum(int((item.get("counts") or {}).get("pending_decision_count") or 0) for item in quests),
                "queued_user_messages_total": sum(int((item.get("counts") or {}).get("pending_user_message_count") or 0) for item in quests),
                "running_bash_total": sum(int((item.get("counts") or {}).get("bash_running_count") or 0) for item in quests),
                "failures_last_7d": len(failures),
                "repairs_total": len(self.app.admin_repair_service.list_repairs(limit=500)),
                "degraded_connectors": int(connector_health.get("degraded_total") or 0),
                "running_tasks": int(task_health.get("running_total") or 0),
                "failed_tasks": int(task_health.get("failed_total") or 0),
            },
            "status_counts": quest_insights.get("status_counts"),
            "anchor_counts": quest_insights.get("anchor_counts"),
            "workspace_mode_counts": quest_insights.get("workspace_mode_counts"),
            "runner_counts": quest_insights.get("runner_counts"),
            "connector_state_counts": connector_health.get("state_counts"),
            "task_status_counts": task_health.get("status_counts"),
            "task_kind_counts": task_health.get("kind_counts"),
            "failure_type_counts": self._sorted_counter(failure_type_counts),
            "decision_backlog_buckets": quest_insights.get("decision_backlog_buckets"),
            "message_backlog_buckets": quest_insights.get("message_backlog_buckets"),
            "recent_activity": quest_insights.get("recent_activity"),
            "activity_timeline_7d": quest_insights.get("activity_timeline_7d"),
            "top_pending_decisions": quest_insights.get("top_pending_decisions"),
            "top_waiting_messages": quest_insights.get("top_waiting_messages"),
            "recently_updated": quest_insights.get("recently_updated"),
            "active_watchlist": quest_insights.get("active_watchlist"),
        }

    def chart_catalog(self) -> dict[str, Any]:
        return self.chart_service.catalog()

    def chart_query(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.chart_service.query(items)

    def search(self, query: str, *, limit: int = 100) -> dict[str, Any]:
        term = str(query or "").strip().lower()
        if not term:
            return {"ok": True, "items": []}
        items: list[dict[str, Any]] = []
        for quest in self.app.quest_service.list_quests():
            quest_id = str(quest.get("quest_id") or "").strip()
            title = str(quest.get("title") or "").strip()
            summary_line = str(((quest.get("summary") or {}) if isinstance(quest.get("summary"), dict) else {}).get("status_line") or "").strip()
            haystacks = [quest_id, title, summary_line]
            if any(term in value.lower() for value in haystacks if value):
                items.append(
                    {
                        "kind": "quest",
                        "quest_id": quest_id,
                        "title": title,
                        "summary": summary_line,
                    }
                )
            quest_root = self.home / "quests" / quest_id
            for event in reversed(read_jsonl_tail(quest_root / ".ds" / "events.jsonl", 120)):
                summary = str(event.get("summary") or event.get("message") or "").strip()
                if summary and term in summary.lower():
                    items.append(
                        {
                            "kind": "event",
                            "quest_id": quest_id,
                            "event_type": str(event.get("type") or ""),
                            "summary": summary,
                            "created_at": event.get("created_at"),
                        }
                    )
                    break
        return {"ok": True, "items": items[: max(1, limit)]}

    @staticmethod
    def _origin_repo_url(repo_root: Path) -> str:
        fallback = "https://github.com/ResearAI/DeepScientist"
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(repo_root),
                capture_output=True,
                timeout=2,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except Exception:
            return fallback
        if result.returncode != 0:
            return fallback
        raw = (result.stdout or result.stderr or "").strip()
        if raw.startswith("git@github.com:"):
            path = raw[len("git@github.com:") :]
            if path.endswith(".git"):
                path = path[:-4]
            return f"https://github.com/{path}"
        if raw.startswith("https://github.com/") or raw.startswith("http://github.com/"):
            return raw[:-4] if raw.endswith(".git") else raw
        return fallback

    @staticmethod
    def _node_version() -> str | None:
        node = which("node")
        if not node:
            return None
        try:
            result = subprocess.run(
                [node, "--version"],
                capture_output=True,
                timeout=2,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return (result.stdout or result.stderr or "").strip() or None

    @staticmethod
    def _dedupe_issue_lines(lines: list[str], *, limit: int = 10) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in lines:
            text = str(item or "").strip()
            if not text:
                continue
            normalized = text.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(text)
            if len(deduped) >= max(1, limit):
                break
        return deduped

    @classmethod
    def _recommended_issue_actions(
        cls,
        *,
        degraded_connectors: list[dict[str, Any]],
        runtime_failures: list[dict[str, Any]],
        doctor_cache: dict[str, Any] | None,
    ) -> list[str]:
        suggestions: list[str] = []

        for item in runtime_failures[:4]:
            diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
            for guidance in diagnosis.get("guidance") or []:
                text = str(guidance or "").strip()
                if text:
                    suggestions.append(text)

        for item in degraded_connectors[:4]:
            name = str(item.get("name") or "connector").strip() or "connector"
            state = str(item.get("connection_state") or "degraded").strip() or "degraded"
            last_error = str(item.get("last_error") or "").strip()
            if last_error:
                suggestions.append(
                    f"Reconnect or reconfigure `{name}`. Current state is `{state}` and the latest reported error is `{last_error[:180]}`."
                )
            else:
                suggestions.append(f"Reconnect or reconfigure `{name}` because its current state is `{state}`.")

        report = doctor_cache.get("report") if isinstance(doctor_cache, dict) and isinstance(doctor_cache.get("report"), dict) else None
        if isinstance(report, dict):
            for item in (report.get("checks") or [])[:8]:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "").strip().lower()
                if status in {"ok", "pass", "healthy", "success"}:
                    continue
                check_id = str(item.get("id") or "doctor-check").strip() or "doctor-check"
                summary = str(item.get("summary") or "").strip()
                if summary:
                    suggestions.append(f"Review doctor check `{check_id}`: {summary}")

        if not suggestions:
            suggestions.append("Review the attached runtime evidence and compare it with the expected behavior before retrying.")
            suggestions.append("If this is reproducible, add exact reproduction steps and expected/actual behavior before submitting.")

        return cls._dedupe_issue_lines(suggestions, limit=10)

    @staticmethod
    def _hardware_issue_snapshot(hardware_payload: dict[str, Any] | None) -> list[str]:
        if not isinstance(hardware_payload, dict):
            return ["- Hardware summary unavailable."]
        prompt_summary = str(hardware_payload.get("prompt_hardware_summary") or "").strip()
        system_payload = hardware_payload.get("system") if isinstance(hardware_payload.get("system"), dict) else {}
        host = system_payload.get("host") if isinstance(system_payload.get("host"), dict) else {}
        cpu = system_payload.get("cpu") if isinstance(system_payload.get("cpu"), dict) else {}
        memory = system_payload.get("memory") if isinstance(system_payload.get("memory"), dict) else {}
        gpus = system_payload.get("gpus") if isinstance(system_payload.get("gpus"), list) else []
        lines: list[str] = []
        hostname = str(host.get("hostname") or "").strip()
        platform_text = str(host.get("platform") or "").strip()
        if hostname or platform_text:
            lines.append(f"- Host: `{hostname or 'unknown'}` platform=`{platform_text or 'unknown'}`")
        if prompt_summary:
            lines.append(f"- Summary: {prompt_summary}")
        cpu_model = str(cpu.get("model") or "").strip()
        logical_cores = cpu.get("logical_cores")
        if cpu_model or logical_cores is not None:
            lines.append(f"- CPU: `{cpu_model or 'unknown cpu'}` logical_cores=`{logical_cores if logical_cores is not None else 'unknown'}`")
        total_memory_gb = memory.get("total_gb")
        available_memory_gb = memory.get("available_gb")
        if total_memory_gb is not None or available_memory_gb is not None:
            lines.append(f"- Memory: total_gb=`{total_memory_gb if total_memory_gb is not None else 'unknown'}` available_gb=`{available_memory_gb if available_memory_gb is not None else 'unknown'}`")
        if gpus:
            gpu_descriptions = []
            for item in gpus[:6]:
                if not isinstance(item, dict):
                    continue
                gpu_id = str(item.get("gpu_id") or "").strip()
                name = str(item.get("name") or "GPU").strip()
                memory_total_gb = item.get("memory_total_gb")
                gpu_descriptions.append(f"{gpu_id or '?'}:{name}{f' {memory_total_gb}GB' if memory_total_gb is not None else ''}")
            if gpu_descriptions:
                lines.append(f"- GPUs: {'; '.join(gpu_descriptions)}")
        if not lines:
            return ["- Hardware summary unavailable."]
        return lines

    def issue_draft(
        self,
        *,
        summary: str | None = None,
        user_notes: str | None = None,
        include_doctor: bool = True,
        include_logs: bool = True,
    ) -> dict[str, Any]:
        error_console = self.error_console(limit=10)
        doctor_cache = self.app.admin_task_service.cached_result("doctor.json") if include_doctor else None
        health = self.app.handlers.health()
        cli_health = self.app.handlers.cli_health()
        repo_url = self._origin_repo_url(self.app.repo_root)
        issue_url_base = f"{repo_url}/issues/new"
        degraded_connectors = error_console.get("degraded_connectors") or []
        runtime_failures = error_console.get("runtime_failures") or []
        daemon_errors = error_console.get("daemon_errors") or []
        failed_tasks = error_console.get("failed_tasks") or []
        hardware = self.system_hardware(refresh=False)
        title = str(summary or "").strip()
        if not title:
            if runtime_failures:
                title = f"Admin report: {str((runtime_failures[0] or {}).get('summary') or 'runtime failure').strip()[:90]}"
            elif degraded_connectors:
                title = f"Admin report: connector degradation in {str((degraded_connectors[0] or {}).get('name') or 'connector')}"
            elif failed_tasks:
                title = f"Admin report: failed admin task `{str((failed_tasks[0] or {}).get('kind') or 'task')}`"
            else:
                title = "Admin report: runtime issue investigation"

        recommended_actions = self._recommended_issue_actions(
            degraded_connectors=degraded_connectors,
            runtime_failures=runtime_failures,
            doctor_cache=doctor_cache if isinstance(doctor_cache, dict) else None,
        )

        lines = [
            "# Summary",
            "",
            title,
            "",
            "## Operator Notes",
            "",
            str(user_notes or "").strip() or "_Add any extra observations here before submitting._",
            "",
            "## Detected Problems",
            "",
        ]
        if runtime_failures:
            for item in runtime_failures[:5]:
                diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
                diagnosis_problem = str(diagnosis.get("problem") or "").strip()
                diagnosis_code = str(diagnosis.get("code") or "").strip()
                diagnosis_suffix = f" diagnosis=`{diagnosis_code}` {diagnosis_problem}" if diagnosis_problem or diagnosis_code else ""
                lines.append(
                    f"- Runtime failure: quest=`{item.get('quest_id')}` run=`{item.get('run_id')}` type=`{item.get('event_type')}` summary={item.get('summary')}{diagnosis_suffix}"
                )
        else:
            lines.append("- No runtime failure records were detected in the recent window.")
        if degraded_connectors:
            for item in degraded_connectors[:5]:
                lines.append(
                    f"- Connector issue: `{item.get('name')}` state=`{item.get('connection_state')}` error=`{item.get('last_error')}`"
                )
        else:
            lines.append("- No degraded connectors were detected.")
        if failed_tasks:
            for item in failed_tasks[:5]:
                lines.append(
                    f"- Failed admin task: kind=`{item.get('kind')}` task_id=`{item.get('task_id')}` error=`{item.get('error')}`"
                )
        else:
            lines.append("- No failed admin tasks were detected.")
        lines.extend(
            [
                "",
                "## Recommended Fixes / Workarounds",
                "",
            ]
        )
        for item in recommended_actions:
            lines.append(f"- {item}")
        lines.extend(
            [
                "",
                "## Environment",
                "",
            ]
        )
        lines.extend(
            self._hardware_issue_snapshot(hardware)
        )
        lines.extend(
            [
                "",
                f"- DeepScientist version: `{DEEPSCIENTIST_VERSION}`",
                f"- Platform: `{platform.platform()}`",
                f"- Python: `{sys.version.split()[0]}`",
                f"- Node: `{self._node_version() or 'unavailable'}`",
                f"- Repo: `{repo_url}`",
                f"- Home: `{self.home}`",
                "",
                "## Runtime Health",
                "",
                f"- Daemon status: `{health.get('status')}`",
                f"- Daemon id: `{health.get('daemon_id')}`",
                f"- Browser auth enabled: `{health.get('auth_enabled')}`",
                f"- CLI checks: `{cli_health.get('checks')}`",
                "",
                "## Recent Runtime Failures",
                "",
            ]
        )
        if runtime_failures:
            for item in runtime_failures[:5]:
                lines.append(
                    f"- quest=`{item.get('quest_id')}` run=`{item.get('run_id')}` type=`{item.get('event_type')}` summary={item.get('summary')}"
                )
        else:
            lines.append("- None detected.")
        lines.extend(["", "## Failed Admin Tasks", ""])
        if failed_tasks:
            for item in failed_tasks[:5]:
                lines.append(
                    f"- kind=`{item.get('kind')}` task_id=`{item.get('task_id')}` error=`{item.get('error')}`"
                )
        else:
            lines.append("- None detected.")
        if include_logs:
            lines.extend(["", "## Daemon Error Excerpts", ""])
            if daemon_errors:
                for item in daemon_errors[:8]:
                    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                    message = str(payload.get("message") or item.get("event") or "").strip()
                    lines.append(f"- level=`{item.get('level')}` event=`{item.get('event')}` message={message[:240]}")
            else:
                lines.append("- None captured in recent daemon tail.")
        if include_doctor:
            lines.extend(["", "## Cached Doctor Summary", ""])
            report = doctor_cache.get("report") if isinstance(doctor_cache, dict) and isinstance(doctor_cache.get("report"), dict) else None
            if isinstance(report, dict):
                lines.append(f"- ok: `{report.get('ok')}`")
                for item in (report.get("checks") or [])[:12]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(
                        f"- `{item.get('id')}` status=`{item.get('status')}` summary={item.get('summary')}"
                    )
            else:
                lines.append("- No cached doctor report available.")
        body_markdown = "\n".join(lines).strip() + "\n"
        return {
            "ok": True,
            "title": title,
            "body_markdown": body_markdown,
            "issue_url_base": issue_url_base,
            "repo_url": repo_url,
            "generated_at": utc_now(),
            "context": {
                "error_console": error_console,
                "doctor_cached": doctor_cache,
            },
        }

    @staticmethod
    def _github_issue_url_base(repository: str = _ISSUE_REPOSITORY) -> str:
        return f"https://github.com/{repository}/issues/new"

    @classmethod
    def _github_issue_fallback_url(cls, *, title: str, body_markdown: str, repository: str = _ISSUE_REPOSITORY) -> tuple[str, bool]:
        base = cls._github_issue_url_base(repository)
        body = body_markdown
        url = f"{base}?{urlencode({'title': title, 'body': body})}"
        if len(url) <= _MAX_FALLBACK_URL_LENGTH:
            return url, False
        truncated_body = (
            body[:4800].rstrip()
            + "\n\n<!-- Fallback URL body truncated. Use the local body_path returned by the API for the full Markdown body. -->\n"
        )
        return f"{base}?{urlencode({'title': title, 'body': truncated_body})}", True

    def _read_issue_source_markdown(self, source_markdown_path: str | None) -> tuple[str | None, str | None]:
        normalized = str(source_markdown_path or "").strip()
        if not normalized:
            return None, None
        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            candidate = self.home / candidate
        candidate = candidate.resolve()
        home_resolved = self.home.resolve()
        if candidate != home_resolved and home_resolved not in candidate.parents:
            raise ValueError("`source_markdown_path` must stay under the DeepScientist home directory.")
        if candidate.suffix.lower() not in {".md", ".markdown"}:
            raise ValueError("`source_markdown_path` must point to a Markdown file.")
        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Markdown source does not exist: {candidate}")
        if candidate.stat().st_size > _MAX_ISSUE_SOURCE_MARKDOWN_BYTES:
            raise ValueError("Markdown source is too large for direct issue submission.")
        return candidate.read_text(encoding="utf-8"), str(candidate)

    def _detected_system_settings_markdown(self) -> str:
        hardware = self.system_hardware(refresh=False)
        system_payload = hardware.get("system") if isinstance(hardware.get("system"), dict) else {}
        preferences = hardware.get("preferences") if isinstance(hardware.get("preferences"), dict) else {}
        memory_preferences = hardware.get("memory_preferences") if isinstance(hardware.get("memory_preferences"), dict) else {}
        host = system_payload.get("host") if isinstance(system_payload.get("host"), dict) else {}
        cpu = system_payload.get("cpu") if isinstance(system_payload.get("cpu"), dict) else {}
        memory = system_payload.get("memory") if isinstance(system_payload.get("memory"), dict) else {}
        lines = [
            "## Detected System Settings",
            "",
            f"- DeepScientist version: `{DEEPSCIENTIST_VERSION}`",
            f"- Repository: `{_ISSUE_REPOSITORY}`",
            f"- Repo root: `{self.app.repo_root}`",
            f"- Home: `{self.home}`",
            f"- Platform: `{platform.platform()}`",
            f"- Python: `{sys.version.split()[0]}`",
            f"- Node: `{self._node_version() or 'unavailable'}`",
            f"- Hostname: `{host.get('hostname') or 'unknown'}`",
            f"- CPU: `{cpu.get('model') or 'unknown'}` logical_cores=`{cpu.get('logical_cores', 'unknown')}`",
            f"- Memory: total_gb=`{memory.get('total_gb', 'unknown')}` available_gb=`{memory.get('available_gb', 'unknown')}`",
            f"- GPU selection mode: `{preferences.get('gpu_selection_mode') or 'all'}`",
            f"- Effective GPU ids: `{','.join(str(item) for item in preferences.get('effective_gpu_ids') or []) or 'none'}`",
            f"- CUDA_VISIBLE_DEVICES policy: `{preferences.get('cuda_visible_devices') or 'unset'}`",
            f"- Include hardware in prompt: `{preferences.get('include_system_hardware_in_prompt')}`",
            f"- Memory read visibility: `{memory_preferences.get('read_visibility_mode') or 'independent'}`",
            "",
        ]
        return "\n".join(lines)

    def _issue_body_with_detected_settings(self, body_markdown: str, *, include_system_settings: bool) -> str:
        body = str(body_markdown or "").strip()
        if include_system_settings and "## Detected System Settings" not in body:
            body = f"{body}\n\n{self._detected_system_settings_markdown().strip()}".strip()
        return body + "\n"

    def issue_create(
        self,
        *,
        title: str | None = None,
        body_markdown: str | None = None,
        source_markdown_path: str | None = None,
        source_markdown: str | None = None,
        include_system_settings: bool = True,
    ) -> dict[str, Any]:
        normalized_title = str(title or "").strip() or "Admin report: runtime issue investigation"
        if "\n" in normalized_title:
            normalized_title = normalized_title.splitlines()[0].strip()
        normalized_title = normalized_title[:180] or "Admin report: runtime issue investigation"

        path_markdown, resolved_source_path = self._read_issue_source_markdown(source_markdown_path)
        body_source = str(source_markdown or "").strip() or str(body_markdown or "").strip() or str(path_markdown or "").strip()
        if not body_source:
            draft = self.issue_draft(summary=normalized_title, include_doctor=True, include_logs=True)
            body_source = str(draft.get("body_markdown") or "").strip()
        final_body = self._issue_body_with_detected_settings(body_source, include_system_settings=include_system_settings)

        issue_dir = ensure_dir(self.home / "runtime" / "admin" / "issues")
        body_hash = sha256_text(f"{normalized_title}\n{final_body}")[:12]
        body_path = issue_dir / f"issue-{body_hash}.md"
        body_path.write_text(final_body, encoding="utf-8")

        fallback_url, fallback_url_truncated = self._github_issue_fallback_url(
            title=normalized_title,
            body_markdown=final_body,
            repository=_ISSUE_REPOSITORY,
        )
        gh = which("gh")
        if not gh:
            payload = {
                "ok": False,
                "created": False,
                "message": "`gh` CLI is not available. Open the fallback URL or install/authenticate GitHub CLI.",
                "title": normalized_title,
                "body_markdown": final_body,
                "body_path": str(body_path),
                "source_markdown_path": resolved_source_path,
                "repository": _ISSUE_REPOSITORY,
                "issue_url": None,
                "issue_url_base": self._github_issue_url_base(_ISSUE_REPOSITORY),
                "fallback_url": fallback_url,
                "fallback_url_truncated": fallback_url_truncated,
                "generated_at": utc_now(),
            }
            self.write_audit(action="issue.create", created=False, repository=_ISSUE_REPOSITORY, reason="gh_missing", body_path=str(body_path))
            return payload

        try:
            result = subprocess.run(
                [gh, "issue", "create", "--repo", _ISSUE_REPOSITORY, "--title", normalized_title, "--body-file", str(body_path)],
                cwd=str(self.app.repo_root),
                capture_output=True,
                timeout=60,
                check=False,
                **utf8_text_subprocess_kwargs(),
            )
        except Exception as exc:
            result = None
            error_message = str(exc)
        else:
            error_message = (result.stderr or result.stdout or "").strip()

        if result is not None and result.returncode == 0:
            issue_url = (result.stdout or result.stderr or "").strip().splitlines()[-1].strip()
            payload = {
                "ok": True,
                "created": True,
                "message": "GitHub issue created.",
                "title": normalized_title,
                "body_markdown": final_body,
                "body_path": str(body_path),
                "source_markdown_path": resolved_source_path,
                "repository": _ISSUE_REPOSITORY,
                "issue_url": issue_url,
                "issue_url_base": self._github_issue_url_base(_ISSUE_REPOSITORY),
                "fallback_url": fallback_url,
                "fallback_url_truncated": fallback_url_truncated,
                "generated_at": utc_now(),
            }
            self.write_audit(action="issue.create", created=True, repository=_ISSUE_REPOSITORY, issue_url=issue_url, body_path=str(body_path))
            return payload

        payload = {
            "ok": False,
            "created": False,
            "message": error_message or "`gh issue create` failed.",
            "title": normalized_title,
            "body_markdown": final_body,
            "body_path": str(body_path),
            "source_markdown_path": resolved_source_path,
            "repository": _ISSUE_REPOSITORY,
            "issue_url": None,
            "issue_url_base": self._github_issue_url_base(_ISSUE_REPOSITORY),
            "fallback_url": fallback_url,
            "fallback_url_truncated": fallback_url_truncated,
            "generated_at": utc_now(),
        }
        self.write_audit(action="issue.create", created=False, repository=_ISSUE_REPOSITORY, reason="gh_failed", message=payload["message"], body_path=str(body_path))
        return payload

    def built_in_controllers(self) -> list[dict[str, Any]]:
        state = self._controller_state()
        entries = state.get("controllers") if isinstance(state, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        catalog = [
            ("stale_running_quest_guard", "Detect quests stuck in running state without fresh tool activity."),
            ("repeated_runner_error_guard", "Detect quests repeatedly hitting runner turn failures."),
            ("connector_degraded_guard", "Detect connectors with last_error or unhealthy connection state."),
        ]
        items: list[dict[str, Any]] = []
        for controller_id, description in catalog:
            current = dict(entries.get(controller_id) or {}) if isinstance(entries.get(controller_id), dict) else {}
            items.append(
                {
                    "controller_id": controller_id,
                    "description": description,
                    "enabled": bool(current.get("enabled")),
                    "last_run_at": current.get("last_run_at"),
                    "last_result": current.get("last_result"),
                }
            )
        return items

    def controllers(self) -> dict[str, Any]:
        return {"ok": True, "items": self.built_in_controllers()}

    def _controller_state_path(self) -> Path:
        return self.home / "runtime" / "admin" / "controllers.json"

    def _controller_state(self) -> dict[str, Any]:
        payload = read_json(self._controller_state_path(), default={})
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("controllers", {})
        return payload

    def _write_controller_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..shared import write_json

        write_json(self._controller_state_path(), payload)
        return payload

    def controller_toggle(self, controller_id: str, *, enabled: bool) -> dict[str, Any]:
        payload = self._controller_state()
        controllers = payload.setdefault("controllers", {})
        current = dict(controllers.get(controller_id) or {}) if isinstance(controllers.get(controller_id), dict) else {}
        current["enabled"] = bool(enabled)
        current["updated_at"] = utc_now()
        controllers[controller_id] = current
        self._write_controller_state(payload)
        return next(item for item in self.built_in_controllers() if item["controller_id"] == controller_id)

    def controller_run(self, controller_id: str) -> dict[str, Any]:
        handlers = {
            "stale_running_quest_guard": self._run_stale_running_quest_guard,
            "repeated_runner_error_guard": self._run_repeated_runner_error_guard,
            "connector_degraded_guard": self._run_connector_degraded_guard,
        }
        if controller_id not in handlers:
            raise FileNotFoundError(f"Unknown controller `{controller_id}`.")
        result = handlers[controller_id]()
        payload = self._controller_state()
        controllers = payload.setdefault("controllers", {})
        current = dict(controllers.get(controller_id) or {}) if isinstance(controllers.get(controller_id), dict) else {}
        current["last_run_at"] = utc_now()
        current["last_result"] = result
        controllers[controller_id] = current
        self._write_controller_state(payload)
        return result

    def _run_stale_running_quest_guard(self) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        threshold = datetime.now(UTC) - timedelta(minutes=30)
        for item in self.app.quest_service.list_quests():
            runtime_status = str(item.get("runtime_status") or item.get("status") or "").strip().lower()
            active_run = str(item.get("active_run_id") or "").strip()
            if runtime_status not in {"running", "active"} and not active_run:
                continue
            last_tool_activity = self._parse_iso(item.get("last_tool_activity_at"))
            if last_tool_activity is None or last_tool_activity <= threshold:
                hits.append(
                    {
                        "quest_id": item.get("quest_id"),
                        "title": item.get("title"),
                        "runtime_status": runtime_status,
                        "active_run_id": active_run or None,
                        "last_tool_activity_at": item.get("last_tool_activity_at"),
                    }
                )
        return {
            "status": "warning" if hits else "ok",
            "hit_count": len(hits),
            "hits": hits,
        }

    def _run_repeated_runner_error_guard(self) -> dict[str, Any]:
        grouped = Counter()
        details: dict[str, list[dict[str, Any]]] = {}
        for item in self.failure_records(limit=500):
            grouped[str(item.get("quest_id") or "")] += 1
            details.setdefault(str(item.get("quest_id") or ""), []).append(item)
        hits = [
            {
                "quest_id": quest_id,
                "failure_count": count,
                "latest_failure": (details.get(quest_id) or [None])[0],
            }
            for quest_id, count in grouped.items()
            if quest_id and count >= 2
        ]
        return {
            "status": "warning" if hits else "ok",
            "hit_count": len(hits),
            "hits": hits,
        }

    def _run_connector_degraded_guard(self) -> dict[str, Any]:
        hits: list[dict[str, Any]] = []
        for item in self.app.list_connector_statuses():
            if not bool(item.get("enabled")):
                continue
            connection_state = str(item.get("connection_state") or "").strip().lower()
            last_error = str(item.get("last_error") or "").strip()
            if last_error or connection_state in {"error", "degraded", "offline"}:
                hits.append(
                    {
                        "name": item.get("name"),
                        "connection_state": item.get("connection_state"),
                        "last_error": item.get("last_error"),
                    }
                )
        return {
            "status": "warning" if hits else "ok",
            "hit_count": len(hits),
            "hits": hits,
        }
