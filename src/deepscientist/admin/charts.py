from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import threading
from typing import Any, Callable, Literal

from ..shared import append_jsonl, ensure_dir, read_json, read_jsonl, utc_now, write_json
from .system_info import hardware_stats_day_path


ChartKind = Literal["line", "bar"]
AggregationMode = Literal["avg", "last"]
ChartSource = Literal["fleet", "hardware"]

DEFAULT_SAMPLING_INTERVAL_SECONDS = 60
DEFAULT_STALE_AFTER_SECONDS = 180
FLEET_RAW_RETENTION_DAYS = 14
CHART_CACHE_RETENTION_DAYS = 3


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


def _normalize_range(value: str | None) -> str:
    normalized = str(value or "").strip().lower() or "24h"
    if normalized in {"1h", "6h", "24h", "7d", "30d"}:
        return normalized
    return "24h"


def _range_to_timedelta(value: str) -> timedelta:
    normalized = _normalize_range(value)
    if normalized.endswith("h"):
        return timedelta(hours=max(1, int(normalized[:-1] or "24")))
    return timedelta(days=max(1, int(normalized[:-1] or "7")))


def _default_step_seconds(range_label: str) -> int:
    normalized = _normalize_range(range_label)
    if normalized == "1h":
        return 60
    if normalized == "6h":
        return 300
    if normalized == "24h":
        return 900
    if normalized == "7d":
        return 3600
    return 21600


def _floor_bucket(ts: datetime, *, step_seconds: int) -> datetime:
    step = max(60, int(step_seconds))
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % step)
    return datetime.fromtimestamp(floored, tz=UTC)


def metrics_root(home: Path) -> Path:
    return home / "runtime" / "admin" / "metrics"


def fleet_stats_root(home: Path) -> Path:
    return metrics_root(home) / "snapshots" / "fleet"


def fleet_stats_day_path(home: Path, *, day: str | None = None) -> Path:
    resolved_day = day or utc_now().split("T", 1)[0]
    return fleet_stats_root(home) / f"{resolved_day}.jsonl"


def chart_cache_root(home: Path) -> Path:
    return home / "runtime" / "admin" / "cache" / "charts"


def append_fleet_snapshot(home: Path, sample: dict[str, Any]) -> Path:
    path = fleet_stats_day_path(home)
    append_jsonl(path, sample)
    return path


def _path_signature(paths: list[Path]) -> str:
    parts: list[str] = []
    for path in paths:
        if not path.exists():
            parts.append(f"{path.name}:missing")
            continue
        try:
            stat = path.stat()
        except OSError:
            parts.append(f"{path.name}:error")
            continue
        parts.append(f"{path.name}:{int(stat.st_mtime_ns)}:{int(stat.st_size)}")
    return "|".join(parts)


def _load_jsonl_records(paths: list[Path], *, start_at: datetime | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        for item in read_jsonl(path):
            if not isinstance(item, dict):
                continue
            if start_at is not None:
                recorded_at = _parse_iso(item.get("recorded_at"))
                if recorded_at is None or recorded_at < start_at:
                    continue
            items.append(dict(item))
    items.sort(key=lambda item: str(item.get("recorded_at") or ""))
    return items


def _fleet_day_paths(home: Path, *, start_at: datetime, end_at: datetime) -> list[Path]:
    return [
        fleet_stats_day_path(home, day=day.isoformat())
        for day in _day_range(start_at.date(), end_at.date())
    ]


def _hardware_day_paths(home: Path, *, start_at: datetime, end_at: datetime) -> list[Path]:
    return [
        hardware_stats_day_path(home, day=day.isoformat())
        for day in _day_range(start_at.date(), end_at.date())
    ]


def _dig(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = record
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _latest_recorded_at(records: list[dict[str, Any]]) -> str | None:
    for item in reversed(records):
        recorded_at = str(item.get("recorded_at") or "").strip()
        if recorded_at:
            return recorded_at
    return None


@dataclass(frozen=True)
class LineSeriesSpec:
    series_id: str
    label: str
    color: str
    path: tuple[str, ...]
    aggregation: AggregationMode


@dataclass(frozen=True)
class ChartSpec:
    chart_id: str
    kind: ChartKind
    title: str
    source: ChartSource
    description: str
    default_range: str
    default_step_seconds: int
    surfaces: tuple[str, ...]
    priority: int
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS
    line_series: tuple[LineSeriesSpec, ...] = ()
    bar_counts_path: tuple[str, ...] | None = None


CHART_SPECS: tuple[ChartSpec, ...] = (
    ChartSpec(
        chart_id="system.cpu_memory_disk",
        kind="line",
        title="System CPU / Memory / Disk",
        description="Recent resource utilization from the local hardware monitor.",
        source="hardware",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("stats",),
        priority=10,
        line_series=(
            LineSeriesSpec("cpu_usage_percent", "CPU", "#C47A5A", ("cpu", "usage_percent"), "avg"),
            LineSeriesSpec("memory_usage_percent", "Memory", "#6E9774", ("memory", "usage_percent"), "avg"),
            LineSeriesSpec("root_disk_usage_percent", "Root Disk", "#6E88B7", ("root_disk_usage_percent",), "avg"),
        ),
    ),
    ChartSpec(
        chart_id="runtime.active_quests",
        kind="line",
        title="Active Quests",
        description="Quest activity sampled every minute.",
        source="fleet",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("stats",),
        priority=20,
        line_series=(LineSeriesSpec("active_quests", "Active quests", "#C47A5A", ("runtime", "active_quests"), "last"),),
    ),
    ChartSpec(
        chart_id="runtime.pending_decisions_total",
        kind="line",
        title="Pending Decisions",
        description="Decision backlog sampled every minute.",
        source="fleet",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("summary", "stats"),
        priority=30,
        line_series=(LineSeriesSpec("pending_decisions_total", "Pending decisions", "#B88A4A", ("runtime", "pending_decisions_total"), "last"),),
    ),
    ChartSpec(
        chart_id="runtime.queued_user_messages_total",
        kind="line",
        title="Queued User Messages",
        description="User reply backlog sampled every minute.",
        source="fleet",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("summary", "stats"),
        priority=40,
        line_series=(LineSeriesSpec("queued_user_messages_total", "Queued messages", "#7B86C8", ("runtime", "queued_user_messages_total"), "last"),),
    ),
    ChartSpec(
        chart_id="runtime.running_tasks",
        kind="line",
        title="Running Admin Tasks",
        description="Admin background task pressure over time.",
        source="fleet",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("summary", "stats"),
        priority=50,
        line_series=(LineSeriesSpec("running_tasks", "Running tasks", "#5F9EA0", ("runtime", "running_tasks"), "last"),),
    ),
    ChartSpec(
        chart_id="runtime.degraded_connectors",
        kind="line",
        title="Degraded Connectors",
        description="Connector degradation over time.",
        source="fleet",
        default_range="24h",
        default_step_seconds=900,
        surfaces=("summary", "stats"),
        priority=60,
        line_series=(LineSeriesSpec("degraded_connectors", "Degraded connectors", "#BE6A6A", ("runtime", "degraded_connectors"), "last"),),
    ),
    ChartSpec(
        chart_id="quests.by_status",
        kind="bar",
        title="Quest Status Distribution",
        description="Latest quest status counts.",
        source="fleet",
        default_range="latest",
        default_step_seconds=0,
        surfaces=("summary", "stats"),
        priority=70,
        bar_counts_path=("distributions", "status_counts"),
    ),
    ChartSpec(
        chart_id="quests.by_anchor",
        kind="bar",
        title="Quest Anchor Distribution",
        description="Latest quest anchor counts.",
        source="fleet",
        default_range="latest",
        default_step_seconds=0,
        surfaces=("summary", "stats"),
        priority=80,
        bar_counts_path=("distributions", "anchor_counts"),
    ),
    ChartSpec(
        chart_id="tasks.by_status",
        kind="bar",
        title="Task Status Distribution",
        description="Latest admin task status counts.",
        source="fleet",
        default_range="latest",
        default_step_seconds=0,
        surfaces=("stats",),
        priority=90,
        bar_counts_path=("distributions", "task_status_counts"),
    ),
    ChartSpec(
        chart_id="connectors.by_state",
        kind="bar",
        title="Connector State Distribution",
        description="Latest connector state counts.",
        source="fleet",
        default_range="latest",
        default_step_seconds=0,
        surfaces=("stats",),
        priority=100,
        bar_counts_path=("distributions", "connector_state_counts"),
    ),
)


CHART_SPEC_INDEX = {item.chart_id: item for item in CHART_SPECS}


class AdminMetricsCollector:
    def __init__(
        self,
        home: Path,
        *,
        sampling_interval_seconds: int = DEFAULT_SAMPLING_INTERVAL_SECONDS,
        build_fleet_snapshot: Callable[[], dict[str, Any]],
        sync_tool_metrics: Callable[[], dict[str, Any]] | None = None,
        prune_tool_metrics: Callable[[datetime | None], None] | None = None,
        logger: Any | None = None,
    ) -> None:
        self.home = Path(home)
        self.sampling_interval_seconds = max(30, int(sampling_interval_seconds))
        self._build_fleet_snapshot = build_fleet_snapshot
        self._sync_tool_metrics = sync_tool_metrics
        self._prune_tool_metrics = prune_tool_metrics
        self.logger = logger
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sample_lock = threading.Lock()
        self._last_prune_day: str | None = None

    def sample_now(self, *, persist: bool = True) -> dict[str, Any]:
        with self._sample_lock:
            sample = self._build_fleet_snapshot()
            if persist:
                append_fleet_snapshot(self.home, sample)
                if self._sync_tool_metrics is not None:
                    self._sync_tool_metrics()
                self.prune_if_due()
            return sample

    def prune_if_due(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        day_key = current.date().isoformat()
        if self._last_prune_day == day_key:
            return
        self._last_prune_day = day_key
        self.prune(current=current)

    def prune(self, *, current: datetime | None = None) -> None:
        now = current or datetime.now(UTC)
        raw_cutoff = now.date() - timedelta(days=FLEET_RAW_RETENTION_DAYS)
        cache_cutoff = now - timedelta(days=CHART_CACHE_RETENTION_DAYS)
        for root in [fleet_stats_root(self.home), hardware_stats_day_path(self.home).parent]:
            if not root.exists():
                continue
            for path in root.glob("*.jsonl"):
                stem = path.stem
                try:
                    file_day = date.fromisoformat(stem)
                except ValueError:
                    continue
                if file_day < raw_cutoff:
                    try:
                        path.unlink()
                    except OSError:
                        continue
        if self._prune_tool_metrics is not None:
            self._prune_tool_metrics(now)
        cache_root = chart_cache_root(self.home)
        if cache_root.exists():
            for path in cache_root.glob("*.json"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if datetime.fromtimestamp(stat.st_mtime, tz=UTC) < cache_cutoff:
                    try:
                        path.unlink()
                    except OSError:
                        continue

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _worker() -> None:
            while not self._stop_event.is_set():
                try:
                    self.sample_now(persist=True)
                except Exception as exc:
                    if self.logger is not None:
                        try:
                            self.logger.log("warning", "admin.metrics.sample_failed", error=str(exc))
                        except Exception:
                            pass
                self._stop_event.wait(self.sampling_interval_seconds)

        self._thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="deepscientist-admin-metrics-collector",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()


class AdminChartService:
    def __init__(self, app: Any, admin_service: Any) -> None:
        self.app = app
        self.admin_service = admin_service
        self.home = Path(app.home)

    def catalog(self) -> dict[str, Any]:
        items = [
            {
                "chart_id": spec.chart_id,
                "kind": spec.kind,
                "title": spec.title,
                "description": spec.description,
                "default_range": spec.default_range,
                "default_step_seconds": spec.default_step_seconds,
                "surfaces": list(spec.surfaces),
                "priority": spec.priority,
                "source": spec.source,
            }
            for spec in sorted(CHART_SPECS, key=lambda item: item.priority)
        ]
        items.extend(self.admin_service.tool_metrics_service.catalog_items())
        items.sort(key=lambda item: (int(item.get("priority") or 0), str(item.get("chart_id") or "")))
        return {"ok": True, "generated_at": utc_now(), "items": items}

    def _ensure_seed_data_for_source(self, *, source: ChartSource) -> None:
        now = datetime.now(UTC)
        if source == "fleet":
            paths = _fleet_day_paths(self.home, start_at=now - timedelta(minutes=5), end_at=now)
            if any(path.exists() for path in paths):
                return
            self.admin_service.metrics_collector.sample_now(persist=True)
            return
        paths = _hardware_day_paths(self.home, start_at=now - timedelta(minutes=5), end_at=now)
        if any(path.exists() for path in paths):
            return
        self.admin_service.system_monitor.sample_now(persist=True)

    def _cache_path(self, *, chart_id: str, range_label: str, step_seconds: int) -> Path:
        safe_chart_id = chart_id.replace("/", "_").replace(".", "__")
        return chart_cache_root(self.home) / f"{safe_chart_id}__{range_label}__{step_seconds}.json"

    def _source_paths(self, spec: ChartSpec, *, now: datetime, range_label: str) -> list[Path]:
        if spec.kind == "bar":
            start_at = now - timedelta(days=FLEET_RAW_RETENTION_DAYS)
        else:
            start_at = now - _range_to_timedelta(range_label)
        if spec.source == "fleet":
            return _fleet_day_paths(self.home, start_at=start_at, end_at=now)
        return _hardware_day_paths(self.home, start_at=start_at, end_at=now)

    def _load_records(self, spec: ChartSpec, *, now: datetime, range_label: str) -> list[dict[str, Any]]:
        if spec.kind == "bar":
            start_at = now - timedelta(days=FLEET_RAW_RETENTION_DAYS)
        else:
            start_at = now - _range_to_timedelta(range_label)
        paths = self._source_paths(spec, now=now, range_label=range_label)
        return _load_jsonl_records(paths, start_at=start_at)

    @staticmethod
    def _freshness_payload(*, latest_recorded_at: str | None, stale_after_seconds: int, now: datetime) -> dict[str, Any]:
        parsed = _parse_iso(latest_recorded_at) if latest_recorded_at else None
        age_seconds = int(max((now - parsed).total_seconds(), 0.0)) if parsed is not None else None
        is_stale = parsed is None or age_seconds is None or age_seconds > stale_after_seconds
        return {
            "latest_recorded_at": latest_recorded_at,
            "age_seconds": age_seconds,
            "stale_after_seconds": stale_after_seconds,
            "is_stale": is_stale,
        }

    def _build_line_payload(
        self,
        spec: ChartSpec,
        *,
        now: datetime,
        range_label: str,
        step_seconds: int,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        buckets_by_series: dict[str, dict[str, list[float] | float]] = {}
        for item in records:
            recorded_at = _parse_iso(item.get("recorded_at"))
            if recorded_at is None:
                continue
            bucket = _floor_bucket(recorded_at, step_seconds=step_seconds).isoformat()
            for series_spec in spec.line_series:
                if series_spec.path == ("root_disk_usage_percent",):
                    disks = item.get("disks") if isinstance(item.get("disks"), list) else []
                    value = None
                    for disk in disks:
                        if not isinstance(disk, dict):
                            continue
                        if str(disk.get("mount") or "").strip() == "/":
                            value = _as_number(disk.get("usage_percent"))
                            break
                    if value is None and disks:
                        value = _as_number(((disks[0] or {}) if isinstance(disks[0], dict) else {}).get("usage_percent"))
                else:
                    value = _as_number(_dig(item, series_spec.path))
                if value is None:
                    continue
                series_bucket = buckets_by_series.setdefault(series_spec.series_id, {})
                if series_spec.aggregation == "avg":
                    values = series_bucket.setdefault(bucket, [])
                    if isinstance(values, list):
                        values.append(value)
                else:
                    series_bucket[bucket] = value

        series_payload = []
        for series_spec in spec.line_series:
            bucket_map = buckets_by_series.get(series_spec.series_id, {})
            points = []
            for bucket_key in sorted(bucket_map.keys()):
                value_obj = bucket_map[bucket_key]
                if isinstance(value_obj, list):
                    value = round(sum(value_obj) / len(value_obj), 2) if value_obj else None
                else:
                    value = round(float(value_obj), 2)
                points.append({"ts": bucket_key, "value": value})
            series_payload.append(
                {
                    "series_id": series_spec.series_id,
                    "label": series_spec.label,
                    "color": series_spec.color,
                    "points": points,
                }
            )
        latest_recorded_at = _latest_recorded_at(records)
        return {
            "chart_id": spec.chart_id,
            "kind": spec.kind,
            "title": spec.title,
            "description": spec.description,
            "source": spec.source,
            "range": range_label,
            "step_seconds": step_seconds,
            "generated_at": utc_now(),
            "freshness": self._freshness_payload(latest_recorded_at=latest_recorded_at, stale_after_seconds=spec.stale_after_seconds, now=now),
            "series": series_payload,
        }

    def _build_bar_payload(self, spec: ChartSpec, *, now: datetime, records: list[dict[str, Any]]) -> dict[str, Any]:
        latest = records[-1] if records else None
        counts = _dig(latest, spec.bar_counts_path or ()) if isinstance(latest, dict) else {}
        categories = []
        if isinstance(counts, dict):
            for index, (key, value) in enumerate(sorted(counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))):
                numeric = int(value or 0)
                if numeric <= 0:
                    continue
                categories.append(
                    {
                        "key": str(key),
                        "label": str(key),
                        "value": numeric,
                        "color": ["#C47A5A", "#6E9774", "#6E88B7", "#B88A4A", "#7B86C8", "#5F9EA0", "#BE6A6A", "#7D8A91"][index % 8],
                    }
                )
        latest_recorded_at = _latest_recorded_at(records)
        return {
            "chart_id": spec.chart_id,
            "kind": spec.kind,
            "title": spec.title,
            "description": spec.description,
            "source": spec.source,
            "range": "latest",
            "step_seconds": 0,
            "generated_at": utc_now(),
            "freshness": self._freshness_payload(latest_recorded_at=latest_recorded_at, stale_after_seconds=spec.stale_after_seconds, now=now),
            "categories": categories,
        }

    def _query_one(self, *, chart_id: str, range_label: str | None = None, step_seconds: int | None = None) -> dict[str, Any]:
        if chart_id.startswith("tools.") or chart_id.startswith("quest."):
            return self.admin_service.tool_metrics_service.query_chart(
                chart_id=chart_id,
                range_label=str(range_label or "24h").strip() or "24h",
                step_seconds=int(step_seconds or 0) or _default_step_seconds(str(range_label or "24h").strip() or "24h"),
            )
        spec = CHART_SPEC_INDEX.get(chart_id)
        if spec is None:
            raise FileNotFoundError(f"Unknown chart `{chart_id}`.")
        now = datetime.now(UTC)
        effective_range = _normalize_range(range_label) if spec.kind == "line" else "latest"
        effective_step = max(60, int(step_seconds or spec.default_step_seconds or _default_step_seconds(effective_range))) if spec.kind == "line" else 0
        self._ensure_seed_data_for_source(source=spec.source)
        source_paths = self._source_paths(spec, now=now, range_label=effective_range)
        source_signature = _path_signature(source_paths)
        cache_path = self._cache_path(chart_id=chart_id, range_label=effective_range, step_seconds=effective_step)
        cached = read_json(cache_path, {})
        if (
            isinstance(cached, dict)
            and cached.get("source_signature") == source_signature
            and cached.get("chart", {}).get("chart_id") == chart_id
        ):
            chart_payload = dict(cached.get("chart") or {})
            freshness = chart_payload.get("freshness") if isinstance(chart_payload.get("freshness"), dict) else {}
            latest_recorded_at = str(freshness.get("latest_recorded_at") or "").strip() or None
            chart_payload["generated_at"] = utc_now()
            chart_payload["freshness"] = self._freshness_payload(
                latest_recorded_at=latest_recorded_at,
                stale_after_seconds=spec.stale_after_seconds,
                now=now,
            )
            return chart_payload

        records = self._load_records(spec, now=now, range_label=effective_range)
        if spec.kind == "line":
            chart_payload = self._build_line_payload(spec, now=now, range_label=effective_range, step_seconds=effective_step, records=records)
        else:
            chart_payload = self._build_bar_payload(spec, now=now, records=records)

        write_json(
            cache_path,
            {
                "chart": chart_payload,
                "source_signature": source_signature,
                "generated_at": utc_now(),
            },
        )
        return chart_payload

    def query(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        payloads = []
        for item in items:
            chart_id = str(item.get("chart_id") or "").strip()
            if not chart_id:
                continue
            if chart_id.startswith("tools.") or chart_id.startswith("quest."):
                payloads.append(
                    self.admin_service.tool_metrics_service.query_chart(
                        chart_id=chart_id,
                        range_label=str(item.get("range") or "").strip() or "24h",
                        step_seconds=int(item.get("step_seconds") or 0) or _default_step_seconds(str(item.get("range") or "").strip() or "24h"),
                        quest_id=str(item.get("quest_id") or "").strip() or None,
                        limit=int(item.get("limit") or 0) or None,
                    )
                )
            else:
                payloads.append(
                    self._query_one(
                        chart_id=chart_id,
                        range_label=str(item.get("range") or "").strip() or None,
                        step_seconds=int(item.get("step_seconds") or 0) or None,
                    )
                )
        return {"ok": True, "generated_at": utc_now(), "items": payloads}
