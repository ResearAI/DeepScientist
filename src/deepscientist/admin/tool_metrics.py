from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..shared import append_jsonl, ensure_dir, read_json, read_jsonl, utc_now, write_json


TOOL_USAGE_RAW_RETENTION_DAYS = 14


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


def _day_range(start_day: date, end_day: date) -> list[date]:
    items: list[date] = []
    cursor = start_day
    while cursor <= end_day:
        items.append(cursor)
        cursor += timedelta(days=1)
    return items


def _floor_minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def _tool_namespace(record: dict[str, Any]) -> str:
    mcp_server = str(record.get("mcp_server") or "").strip()
    if mcp_server:
        return mcp_server
    tool_name = str(record.get("tool_name") or "").strip()
    if "." in tool_name:
        return tool_name.split(".", 1)[0]
    return tool_name or "tool"


def tool_usage_root(home: Path) -> Path:
    return home / "runtime" / "admin" / "metrics" / "tool_usage"


def tool_usage_minute_root(home: Path) -> Path:
    return tool_usage_root(home) / "minute"


def tool_usage_day_path(home: Path, *, day: str | None = None) -> Path:
    resolved_day = day or utc_now().split("T", 1)[0]
    return tool_usage_minute_root(home) / f"{resolved_day}.jsonl"


def tool_usage_cursor_root(home: Path) -> Path:
    return tool_usage_root(home) / "cursors"


def quest_activity_root(home: Path) -> Path:
    return home / "runtime" / "admin" / "metrics" / "quest_activity"


def quest_activity_minute_root(home: Path) -> Path:
    return quest_activity_root(home) / "minute"


def quest_activity_day_path(home: Path, *, day: str | None = None) -> Path:
    resolved_day = day or utc_now().split("T", 1)[0]
    return quest_activity_minute_root(home) / f"{resolved_day}.jsonl"


class AdminToolMetricsService:
    def __init__(self, home: Path, *, logger: Any | None = None) -> None:
        self.home = Path(home)
        self.logger = logger

    def _quest_events_path(self, quest_id: str) -> Path:
        return self.home / "quests" / quest_id / ".ds" / "events.jsonl"

    def _cursor_path(self, quest_id: str) -> Path:
        return tool_usage_cursor_root(self.home) / f"{quest_id}.json"

    def _load_cursor(self, quest_id: str) -> dict[str, Any]:
        payload = read_json(self._cursor_path(quest_id), {})
        return payload if isinstance(payload, dict) else {}

    def _save_cursor(self, quest_id: str, payload: dict[str, Any]) -> None:
        write_json(self._cursor_path(quest_id), payload)

    def _append_bucket_rows(self, rows: dict[tuple[str, str, str, str, str], dict[str, Any]]) -> None:
        for payload in rows.values():
            append_jsonl(tool_usage_day_path(self.home, day=str(payload["bucket_at"]).split("T", 1)[0]), payload)

    def _append_activity_rows(self, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
        for payload in rows.values():
            append_jsonl(quest_activity_day_path(self.home, day=str(payload["bucket_at"]).split("T", 1)[0]), payload)

    def _normalize_event(self, quest_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(payload.get("type") or "").strip()
        if event_type not in {"runner.tool_call", "runner.tool_result"}:
            return None
        created_at = _parse_iso(payload.get("created_at"))
        if created_at is None:
            return None
        tool_name = str(payload.get("tool_name") or "").strip() or "tool"
        status = str(payload.get("status") or "").strip().lower()
        mcp_server = str(payload.get("mcp_server") or "").strip() or None
        mcp_tool = str(payload.get("mcp_tool") or "").strip() or None
        return {
            "bucket_at": _floor_minute(created_at).isoformat(),
            "quest_id": quest_id,
            "tool_name": tool_name,
            "namespace": _tool_namespace(payload),
            "mcp_server": mcp_server,
            "mcp_tool": mcp_tool,
            "call_count": 1 if event_type == "runner.tool_call" else 0,
            "result_count": 1 if event_type == "runner.tool_result" else 0,
            "error_count": 1 if event_type == "runner.tool_result" and status in {"failed", "error", "cancelled", "timed_out"} else 0,
        }

    def _normalize_activity_event(self, quest_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        created_at = _parse_iso(payload.get("created_at"))
        if created_at is None:
            return None
        event_type = str(payload.get("type") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        return {
            "bucket_at": _floor_minute(created_at).isoformat(),
            "quest_id": quest_id,
            "event_count": 1,
            "tool_call_count": 1 if event_type == "runner.tool_call" else 0,
            "tool_result_count": 1 if event_type == "runner.tool_result" else 0,
            "tool_error_count": 1 if event_type == "runner.tool_result" and status in {"failed", "error", "cancelled", "timed_out"} else 0,
        }

    def catch_up(self, *, quest_ids: list[str] | None = None) -> dict[str, Any]:
        processed_quests = 0
        appended_rows = 0
        appended_activity_rows = 0
        target_ids = {str(item).strip() for item in (quest_ids or []) if str(item).strip()}
        quests_root = self.home / "quests"
        if not quests_root.exists():
            return {"ok": True, "processed_quests": 0, "appended_rows": 0, "appended_activity_rows": 0}

        for quest_root in sorted(quests_root.glob("*/")):
            quest_id = quest_root.name
            if target_ids and quest_id not in target_ids:
                continue
            events_path = self._quest_events_path(quest_id)
            if not events_path.exists():
                continue
            try:
                stat = events_path.stat()
            except OSError:
                continue
            cursor = self._load_cursor(quest_id)
            previous_size = int(cursor.get("size") or 0)
            offset = int(cursor.get("offset") or 0)
            mtime_ns = int(cursor.get("mtime_ns") or 0)
            if previous_size == int(stat.st_size) and mtime_ns == int(stat.st_mtime_ns):
                continue
            if int(stat.st_size) < previous_size or offset > int(stat.st_size):
                offset = 0

            rows: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
            activity_rows: dict[tuple[str, str], dict[str, Any]] = {}
            end_offset = offset
            with events_path.open("r", encoding="utf-8", errors="replace") as handle:
                if offset > 0:
                    handle.seek(offset)
                while True:
                    raw = handle.readline()
                    if not raw:
                        end_offset = handle.tell()
                        break
                    end_offset = handle.tell()
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    activity = self._normalize_activity_event(quest_id, payload)
                    if activity is not None:
                        activity_key = (str(activity["bucket_at"]), str(activity["quest_id"]))
                        current_activity = activity_rows.get(activity_key)
                        if current_activity is None:
                            activity_rows[activity_key] = dict(activity)
                        else:
                            current_activity["event_count"] = int(current_activity.get("event_count") or 0) + int(activity.get("event_count") or 0)
                            current_activity["tool_call_count"] = int(current_activity.get("tool_call_count") or 0) + int(activity.get("tool_call_count") or 0)
                            current_activity["tool_result_count"] = int(current_activity.get("tool_result_count") or 0) + int(activity.get("tool_result_count") or 0)
                            current_activity["tool_error_count"] = int(current_activity.get("tool_error_count") or 0) + int(activity.get("tool_error_count") or 0)
                    normalized = self._normalize_event(quest_id, payload)
                    if normalized is None:
                        continue
                    key = (
                        str(normalized["bucket_at"]),
                        str(normalized["quest_id"]),
                        str(normalized["tool_name"]),
                        str(normalized.get("mcp_server") or ""),
                        str(normalized.get("mcp_tool") or ""),
                    )
                    current = rows.get(key)
                    if current is None:
                        rows[key] = dict(normalized)
                    else:
                        current["call_count"] = int(current.get("call_count") or 0) + int(normalized.get("call_count") or 0)
                        current["result_count"] = int(current.get("result_count") or 0) + int(normalized.get("result_count") or 0)
                        current["error_count"] = int(current.get("error_count") or 0) + int(normalized.get("error_count") or 0)

            if rows:
                self._append_bucket_rows(rows)
                appended_rows += len(rows)
            if activity_rows:
                self._append_activity_rows(activity_rows)
                appended_activity_rows += len(activity_rows)
            self._save_cursor(
                quest_id,
                {
                    "quest_id": quest_id,
                    "events_path": str(events_path),
                    "offset": end_offset,
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "updated_at": utc_now(),
                },
            )
            processed_quests += 1
        return {
            "ok": True,
            "processed_quests": processed_quests,
            "appended_rows": appended_rows,
            "appended_activity_rows": appended_activity_rows,
        }

    def prune(self, *, current: datetime | None = None) -> None:
        now = current or datetime.now(UTC)
        cutoff = now.date() - timedelta(days=TOOL_USAGE_RAW_RETENTION_DAYS)
        for root in [tool_usage_minute_root(self.home), quest_activity_minute_root(self.home)]:
            if not root.exists():
                continue
            for path in root.glob("*.jsonl"):
                try:
                    file_day = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                if file_day < cutoff:
                    try:
                        path.unlink()
                    except OSError:
                        continue

    def _load_rows(self, *, start_at: datetime, end_at: datetime, quest_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for day in _day_range(start_at.date(), end_at.date()):
            path = tool_usage_day_path(self.home, day=day.isoformat())
            if not path.exists():
                continue
            for item in read_jsonl(path):
                if not isinstance(item, dict):
                    continue
                bucket_at = _parse_iso(item.get("bucket_at"))
                if bucket_at is None or bucket_at < start_at or bucket_at > end_at:
                    continue
                if quest_id and str(item.get("quest_id") or "").strip() != quest_id:
                    continue
                rows.append(dict(item))
        rows.sort(key=lambda item: str(item.get("bucket_at") or ""))
        return rows

    def _load_activity_rows(self, *, start_at: datetime, end_at: datetime, quest_id: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for day in _day_range(start_at.date(), end_at.date()):
            path = quest_activity_day_path(self.home, day=day.isoformat())
            if not path.exists():
                continue
            for item in read_jsonl(path):
                if not isinstance(item, dict):
                    continue
                bucket_at = _parse_iso(item.get("bucket_at"))
                if bucket_at is None or bucket_at < start_at or bucket_at > end_at:
                    continue
                if quest_id and str(item.get("quest_id") or "").strip() != quest_id:
                    continue
                rows.append(dict(item))
        rows.sort(key=lambda item: str(item.get("bucket_at") or ""))
        return rows

    def catalog_items(self) -> list[dict[str, Any]]:
        return [
            {
                "chart_id": "tools.calls_total",
                "kind": "line",
                "title": "Tool Calls",
                "description": "Tool invocation volume over time.",
                "default_range": "24h",
                "default_step_seconds": 900,
                "surfaces": ["stats"],
                "priority": 110,
                "source": "tool_usage",
                "supports_filters": {"quest_id": True},
            },
            {
                "chart_id": "tools.by_namespace",
                "kind": "bar",
                "title": "Tool Namespace Mix",
                "description": "Calls grouped by namespace such as artifact, memory, bash_exec, or native tools.",
                "default_range": "24h",
                "default_step_seconds": 0,
                "surfaces": ["stats"],
                "priority": 120,
                "source": "tool_usage",
                "supports_filters": {"quest_id": True, "limit": True},
            },
            {
                "chart_id": "tools.by_tool",
                "kind": "bar",
                "title": "Top Tools",
                "description": "Most frequently used tools in the selected time window.",
                "default_range": "24h",
                "default_step_seconds": 0,
                "surfaces": ["stats"],
                "priority": 130,
                "source": "tool_usage",
                "supports_filters": {"quest_id": True, "limit": True},
            },
            {
                "chart_id": "tools.top_quests_by_calls",
                "kind": "bar",
                "title": "Top Quests By Tool Calls",
                "description": "Quests with the highest tool activity in the selected time window.",
                "default_range": "24h",
                "default_step_seconds": 0,
                "surfaces": ["stats"],
                "priority": 140,
                "source": "tool_usage",
                "supports_filters": {"limit": True},
            },
            {
                "chart_id": "quest.activity.hourly_7d",
                "kind": "line",
                "title": "Weekly Activity",
                "description": "Recent 7 day activity grouped into hourly buckets.",
                "default_range": "7d",
                "default_step_seconds": 3600,
                "surfaces": ["settings"],
                "priority": 210,
                "source": "quest_activity",
                "supports_filters": {"quest_id": True},
                "render_hint": "time_bar",
            },
            {
                "chart_id": "quest.activity.calls_total",
                "kind": "line",
                "title": "Tool Calls Trend",
                "description": "Tool calls over time for the selected quest.",
                "default_range": "24h",
                "default_step_seconds": 900,
                "surfaces": ["settings"],
                "priority": 220,
                "source": "quest_activity",
                "supports_filters": {"quest_id": True},
            },
            {
                "chart_id": "quest.activity.errors_total",
                "kind": "line",
                "title": "Tool Errors Trend",
                "description": "Tool errors over time for the selected quest.",
                "default_range": "24h",
                "default_step_seconds": 900,
                "surfaces": ["settings"],
                "priority": 230,
                "source": "quest_activity",
                "supports_filters": {"quest_id": True},
            },
            {
                "chart_id": "quest.tools.by_namespace",
                "kind": "bar",
                "title": "Tool Namespace Mix",
                "description": "Tool calls grouped by namespace for the selected quest.",
                "default_range": "24h",
                "default_step_seconds": 0,
                "surfaces": ["settings"],
                "priority": 240,
                "source": "tool_usage",
                "supports_filters": {"quest_id": True, "limit": True},
            },
            {
                "chart_id": "quest.tools.by_tool",
                "kind": "bar",
                "title": "Top Tools",
                "description": "Most frequently used tools for the selected quest.",
                "default_range": "24h",
                "default_step_seconds": 0,
                "surfaces": ["settings"],
                "priority": 250,
                "source": "tool_usage",
                "supports_filters": {"quest_id": True, "limit": True},
            },
        ]

    def query_chart(
        self,
        *,
        chart_id: str,
        range_label: str,
        step_seconds: int,
        quest_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        self.catch_up(quest_ids=[quest_id] if quest_id else None)
        now = datetime.now(UTC)
        normalized_range = str(range_label or "24h").strip().lower() or "24h"
        if normalized_range.endswith("h"):
            start_at = now - timedelta(hours=max(1, int(normalized_range[:-1] or "24")))
        elif normalized_range.endswith("d"):
            start_at = now - timedelta(days=max(1, int(normalized_range[:-1] or "7")))
        else:
            start_at = now - timedelta(hours=24)
        rows = self._load_rows(start_at=start_at, end_at=now, quest_id=quest_id)
        effective_limit = max(1, min(int(limit or 8), 20))

        if chart_id == "tools.calls_total":
            bucket_totals: dict[str, int] = {}
            step = max(60, int(step_seconds or 900))
            for item in rows:
                bucket_at = _parse_iso(item.get("bucket_at"))
                if bucket_at is None:
                    continue
                bucket_key = bucket_at.replace(second=0, microsecond=0)
                epoch = int(bucket_key.timestamp())
                bucket_key = datetime.fromtimestamp(epoch - (epoch % step), tz=UTC)
                iso = bucket_key.isoformat()
                bucket_totals[iso] = int(bucket_totals.get(iso) or 0) + int(item.get("call_count") or 0)
            points = [{"ts": key, "value": bucket_totals[key]} for key in sorted(bucket_totals.keys())]
            latest_recorded_at = str(rows[-1].get("bucket_at") or "").strip() if rows else None
            return {
                "chart_id": chart_id,
                "kind": "line",
                "title": "Tool Calls" if not quest_id else f"Tool Calls · {quest_id}",
                "description": "Tool invocation volume over time.",
                "source": "tool_usage",
                "range": normalized_range,
                "step_seconds": step,
                "generated_at": utc_now(),
                "freshness": {
                    "latest_recorded_at": latest_recorded_at,
                    "age_seconds": int(max((now - _parse_iso(latest_recorded_at)).total_seconds(), 0.0)) if latest_recorded_at and _parse_iso(latest_recorded_at) else None,
                    "stale_after_seconds": 300,
                    "is_stale": not latest_recorded_at or (now - (_parse_iso(latest_recorded_at) or now)).total_seconds() > 300,
                },
                "series": [
                    {
                        "series_id": "call_count",
                        "label": "Tool calls",
                        "color": "#B88A4A",
                        "points": points,
                    }
                ],
                "filters": {"quest_id": quest_id},
            }

        if chart_id in {"quest.activity.hourly_7d", "quest.activity.calls_total", "quest.activity.errors_total"}:
            activity_rows = self._load_activity_rows(start_at=start_at, end_at=now, quest_id=quest_id)
            bucket_totals: dict[str, int] = {}
            step = max(60, int(step_seconds or 900))
            metric_key = "tool_call_count"
            if chart_id == "quest.activity.errors_total":
                metric_key = "tool_error_count"
            if chart_id == "quest.activity.hourly_7d":
                metric_key = "event_count"
            for item in activity_rows:
                bucket_at = _parse_iso(item.get("bucket_at"))
                if bucket_at is None:
                    continue
                floored = bucket_at.replace(second=0, microsecond=0)
                epoch = int(floored.timestamp())
                floored = datetime.fromtimestamp(epoch - (epoch % step), tz=UTC)
                iso = floored.isoformat()
                bucket_totals[iso] = int(bucket_totals.get(iso) or 0) + int(item.get(metric_key) or 0)
            latest_recorded_at = str(activity_rows[-1].get("bucket_at") or "").strip() if activity_rows else None
            title_lookup = {
                "quest.activity.hourly_7d": "Weekly Activity",
                "quest.activity.calls_total": "Tool Calls Trend",
                "quest.activity.errors_total": "Tool Errors Trend",
            }
            label_lookup = {
                "quest.activity.hourly_7d": "Events",
                "quest.activity.calls_total": "Tool calls",
                "quest.activity.errors_total": "Tool errors",
            }
            color_lookup = {
                "quest.activity.hourly_7d": "#6E88B7",
                "quest.activity.calls_total": "#B88A4A",
                "quest.activity.errors_total": "#BE6A6A",
            }
            description_lookup = {
                "quest.activity.hourly_7d": "Recent 7 day activity grouped into hourly buckets.",
                "quest.activity.calls_total": "Tool calls over time for the selected quest.",
                "quest.activity.errors_total": "Tool errors over time for the selected quest.",
            }
            return {
                "chart_id": chart_id,
                "kind": "line",
                "title": title_lookup[chart_id],
                "description": description_lookup[chart_id],
                "source": "quest_activity",
                "range": normalized_range,
                "step_seconds": step,
                "generated_at": utc_now(),
                "freshness": {
                    "latest_recorded_at": latest_recorded_at,
                    "age_seconds": int(max((now - _parse_iso(latest_recorded_at)).total_seconds(), 0.0)) if latest_recorded_at and _parse_iso(latest_recorded_at) else None,
                    "stale_after_seconds": 300,
                    "is_stale": not latest_recorded_at or (now - (_parse_iso(latest_recorded_at) or now)).total_seconds() > 300,
                },
                "render_hint": "time_bar" if chart_id == "quest.activity.hourly_7d" else None,
                "series": [
                    {
                        "series_id": metric_key,
                        "label": label_lookup[chart_id],
                        "color": color_lookup[chart_id],
                        "points": [{"ts": key, "value": bucket_totals[key]} for key in sorted(bucket_totals.keys())],
                    }
                ],
                "filters": {"quest_id": quest_id},
            }

        grouped: dict[str, int] = {}
        for item in rows:
            if chart_id == "tools.by_namespace":
                group_key = str(item.get("namespace") or "tool").strip() or "tool"
            elif chart_id == "quest.tools.by_namespace":
                group_key = str(item.get("namespace") or "tool").strip() or "tool"
            elif chart_id == "tools.by_tool":
                group_key = str(item.get("tool_name") or "tool").strip() or "tool"
            elif chart_id == "quest.tools.by_tool":
                group_key = str(item.get("tool_name") or "tool").strip() or "tool"
            elif chart_id == "tools.top_quests_by_calls":
                group_key = str(item.get("quest_id") or "quest").strip() or "quest"
            else:
                raise FileNotFoundError(f"Unknown tool chart `{chart_id}`.")
            grouped[group_key] = int(grouped.get(group_key) or 0) + int(item.get("call_count") or 0)

        ordered = sorted(grouped.items(), key=lambda item: (-item[1], item[0]))[:effective_limit]
        latest_recorded_at = str(rows[-1].get("bucket_at") or "").strip() if rows else None
        palette = ["#C47A5A", "#6E9774", "#6E88B7", "#B88A4A", "#7B86C8", "#5F9EA0", "#BE6A6A", "#7D8A91"]
        title_map = {
            "tools.by_namespace": "Tool Namespace Mix",
            "quest.tools.by_namespace": "Tool Namespace Mix",
            "tools.by_tool": "Top Tools",
            "quest.tools.by_tool": "Top Tools",
            "tools.top_quests_by_calls": "Top Quests By Tool Calls",
        }
        description_map = {
            "tools.by_namespace": "Calls grouped by namespace such as artifact, memory, bash_exec, or native tools.",
            "quest.tools.by_namespace": "Tool calls grouped by namespace for the selected quest.",
            "tools.by_tool": "Most frequently used tools in the selected time window.",
            "quest.tools.by_tool": "Most frequently used tools for the selected quest.",
            "tools.top_quests_by_calls": "Quests with the highest tool activity in the selected time window.",
        }
        return {
            "chart_id": chart_id,
            "kind": "bar",
            "title": title_map[chart_id],
            "description": description_map[chart_id],
            "source": "tool_usage",
            "range": normalized_range,
            "step_seconds": 0,
            "generated_at": utc_now(),
            "freshness": {
                "latest_recorded_at": latest_recorded_at,
                "age_seconds": int(max((now - _parse_iso(latest_recorded_at)).total_seconds(), 0.0)) if latest_recorded_at and _parse_iso(latest_recorded_at) else None,
                "stale_after_seconds": 300,
                "is_stale": not latest_recorded_at or (now - (_parse_iso(latest_recorded_at) or now)).total_seconds() > 300,
            },
            "categories": [
                {
                    "key": key,
                    "label": key,
                    "value": value,
                    "color": palette[index % len(palette)],
                }
                for index, (key, value) in enumerate(ordered)
            ],
            "filters": {"quest_id": quest_id, "limit": effective_limit},
        }
