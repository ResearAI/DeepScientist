from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..shared import append_jsonl, read_jsonl, utc_now, utf8_text_subprocess_kwargs, which


def _run(argv: list[str], *, timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            check=False,
            **utf8_text_subprocess_kwargs(),
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _round_gb(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024**3), 2)


def _cpu_model() -> str | None:
    cpuinfo = _read_text("/proc/cpuinfo")
    for line in cpuinfo.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "model name":
            normalized = value.strip()
            if normalized:
                return normalized
    lscpu_json = _run(["lscpu", "--json"])
    if lscpu_json:
        try:
            payload = json.loads(lscpu_json)
        except Exception:
            payload = {}
        for item in payload.get("lscpu", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("field") or "").strip().lower().startswith("model name"):
                normalized = str(item.get("data") or "").strip()
                if normalized:
                    return normalized
    processor = platform.processor().strip()
    return processor or None


def _physical_core_count() -> int | None:
    lscpu_json = _run(["lscpu", "--json"])
    if lscpu_json:
        try:
            payload = json.loads(lscpu_json)
        except Exception:
            payload = {}
        fields = payload.get("lscpu", []) if isinstance(payload, dict) else []
        cores_per_socket = None
        sockets = None
        total_cores = None
        for item in fields:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip().lower()
            data = str(item.get("data") or "").strip()
            if field.startswith("core(s) per socket"):
                cores_per_socket = int(data) if data.isdigit() else cores_per_socket
            elif field.startswith("socket(s)"):
                sockets = int(data) if data.isdigit() else sockets
            elif field.startswith("cpu(s)"):
                total_cores = int(data) if data.isdigit() else total_cores
        if cores_per_socket and sockets:
            return cores_per_socket * sockets
        if total_cores:
            return total_cores
    return None


def _memory_info() -> dict[str, Any]:
    meminfo = _read_text("/proc/meminfo")
    total_kb = None
    available_kb = None
    for line in meminfo.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower()
        parts = value.strip().split()
        if not parts or not parts[0].isdigit():
            continue
        numeric = int(parts[0])
        if normalized_key == "memtotal":
            total_kb = numeric
        elif normalized_key == "memavailable":
            available_kb = numeric
    total_bytes = total_kb * 1024 if total_kb is not None else None
    available_bytes = available_kb * 1024 if available_kb is not None else None
    return {
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "total_gb": _round_gb(total_bytes),
        "available_gb": _round_gb(available_bytes),
    }


def _disk_targets(home: Path) -> list[Path]:
    candidates = [Path("/"), home.expanduser().resolve()]
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _disk_info(home: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for target in _disk_targets(home):
        try:
            usage = shutil.disk_usage(target)
        except Exception:
            continue
        items.append(
            {
                "mount": str(target),
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
                "total_gb": _round_gb(usage.total),
                "free_gb": _round_gb(usage.free),
            }
        )
    return items


def _nvidia_gpus() -> list[dict[str, Any]]:
    if not which("nvidia-smi"):
        return []
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version,uuid",
            "--format=csv,noheader,nounits",
        ],
        timeout=3.0,
    )
    items: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 5:
            continue
        gpu_id, name, memory_total_mb, driver_version, uuid = parts[:5]
        items.append(
            {
                "gpu_id": gpu_id,
                "vendor": "nvidia",
                "name": name,
                "memory_total_mb": int(memory_total_mb) if memory_total_mb.isdigit() else None,
                "memory_total_gb": round(int(memory_total_mb) / 1024, 2) if memory_total_mb.isdigit() else None,
                "driver_version": driver_version or None,
                "uuid": uuid or None,
            }
        )
    return items


def _rocm_gpus() -> list[dict[str, Any]]:
    if not which("rocm-smi"):
        return []
    output = _run(["rocm-smi", "--showproductname", "--showbus", "--showmeminfo", "vram", "--json"], timeout=4.0)
    if not output:
        return []
    try:
        payload = json.loads(output)
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for key, value in payload.items() if isinstance(payload, dict) else []:
        if not isinstance(value, dict):
            continue
        gpu_id = key.split("card", 1)[-1].strip() if "card" in key.lower() else str(len(items))
        vram_total = None
        for item_key, item_value in value.items():
            normalized_key = str(item_key or "").lower()
            if "total" in normalized_key and "vram" in normalized_key:
                text = str(item_value or "").strip().split()[0]
                if text.isdigit():
                    vram_total = int(text)
                    break
        items.append(
            {
                "gpu_id": gpu_id,
                "vendor": "amd",
                "name": str(value.get("Card Series") or value.get("Card model") or key).strip(),
                "memory_total_mb": vram_total,
                "memory_total_gb": round(vram_total / 1024, 2) if isinstance(vram_total, int) else None,
                "driver_version": None,
                "uuid": str(value.get("Unique ID") or "").strip() or None,
                "bus": str(value.get("PCI Bus") or "").strip() or None,
            }
        )
    return items


def _generic_gpu_fallback() -> list[dict[str, Any]]:
    if not which("lspci"):
        return []
    output = _run(["lspci"], timeout=2.0)
    items: list[dict[str, Any]] = []
    for line in output.splitlines():
        lower = line.lower()
        if "vga compatible controller" not in lower and "3d controller" not in lower:
            continue
        _, _, description = line.partition(":")
        name = description.strip() or line.strip()
        vendor = "unknown"
        if "nvidia" in lower:
            vendor = "nvidia"
        elif "amd" in lower or "advanced micro devices" in lower or "radeon" in lower:
            vendor = "amd"
        elif "intel" in lower:
            vendor = "intel"
        items.append(
            {
                "gpu_id": str(len(items)),
                "vendor": vendor,
                "name": name,
                "memory_total_mb": None,
                "memory_total_gb": None,
                "driver_version": None,
                "uuid": None,
            }
        )
    return items


def _gpu_inventory() -> list[dict[str, Any]]:
    nvidia = _nvidia_gpus()
    if nvidia:
        return nvidia
    amd = _rocm_gpus()
    if amd:
        return amd
    return _generic_gpu_fallback()


def collect_system_hardware(home: Path) -> dict[str, Any]:
    logical_cores = os.cpu_count()
    gpus = _gpu_inventory()
    return {
        "generated_at": None,
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "cpu": {
            "model": _cpu_model(),
            "logical_cores": int(logical_cores) if isinstance(logical_cores, int) else None,
            "physical_cores": _physical_core_count(),
        },
        "memory": _memory_info(),
        "disks": _disk_info(home),
        "gpus": gpus,
        "gpu_count": len(gpus),
    }


def _cpu_stat_totals() -> tuple[int, int] | None:
    stat = _read_text("/proc/stat")
    for line in stat.splitlines():
        if not line.startswith("cpu "):
            continue
        parts = [item for item in line.split() if item]
        numbers = [int(item) for item in parts[1:] if item.isdigit()]
        if len(numbers) < 4:
            return None
        idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
        total = sum(numbers)
        return total, idle
    return None


def _cpu_usage_percent(previous: tuple[int, int] | None = None) -> tuple[float | None, tuple[int, int] | None]:
    current = _cpu_stat_totals()
    if current is None:
        return None, previous
    if previous is None:
        time.sleep(0.05)
        refreshed = _cpu_stat_totals()
        if refreshed is None:
            return None, current
        previous = current
        current = refreshed
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None, current
    busy = max(0.0, min(100.0, ((total_delta - idle_delta) / total_delta) * 100.0))
    return round(busy, 2), current


def _load_average() -> dict[str, float | None]:
    try:
        one, five, fifteen = os.getloadavg()
    except Exception:
        return {"one": None, "five": None, "fifteen": None}
    return {"one": round(one, 2), "five": round(five, 2), "fifteen": round(fifteen, 2)}


def _memory_usage_sample() -> dict[str, Any]:
    info = _memory_info()
    total = info.get("total_bytes")
    available = info.get("available_bytes")
    used = int(total - available) if isinstance(total, int) and isinstance(available, int) else None
    usage_percent = None
    if isinstance(total, int) and total > 0 and isinstance(used, int):
        usage_percent = round((used / total) * 100.0, 2)
    return {
        "total_gb": info.get("total_gb"),
        "available_gb": info.get("available_gb"),
        "used_gb": _round_gb(used),
        "usage_percent": usage_percent,
    }


def _disk_usage_sample(home: Path) -> list[dict[str, Any]]:
    items = []
    for disk in _disk_info(home):
        total = disk.get("total_bytes")
        used = disk.get("used_bytes")
        usage_percent = None
        if isinstance(total, int) and total > 0 and isinstance(used, int):
            usage_percent = round((used / total) * 100.0, 2)
        items.append(
            {
                "mount": disk.get("mount"),
                "total_gb": disk.get("total_gb"),
                "used_gb": _round_gb(used),
                "free_gb": disk.get("free_gb"),
                "usage_percent": usage_percent,
            }
        )
    return items


def _nvidia_gpu_runtime() -> list[dict[str, Any]]:
    if not which("nvidia-smi"):
        return []
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,uuid",
            "--format=csv,noheader,nounits",
        ],
        timeout=3.0,
    )
    items: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 8:
            continue
        gpu_id, name, util, memory_used_mb, memory_total_mb, temperature, power_draw, uuid = parts[:8]
        items.append(
            {
                "gpu_id": gpu_id,
                "vendor": "nvidia",
                "name": name,
                "utilization_gpu_percent": float(util) if util.replace(".", "", 1).isdigit() else None,
                "memory_used_mb": int(memory_used_mb) if memory_used_mb.isdigit() else None,
                "memory_used_gb": round(int(memory_used_mb) / 1024, 2) if memory_used_mb.isdigit() else None,
                "memory_total_mb": int(memory_total_mb) if memory_total_mb.isdigit() else None,
                "memory_total_gb": round(int(memory_total_mb) / 1024, 2) if memory_total_mb.isdigit() else None,
                "temperature_c": float(temperature) if temperature.replace(".", "", 1).isdigit() else None,
                "power_draw_w": float(power_draw) if power_draw.replace(".", "", 1).isdigit() else None,
                "uuid": uuid or None,
            }
        )
    return items


def _gpu_runtime_sample() -> list[dict[str, Any]]:
    nvidia = _nvidia_gpu_runtime()
    if nvidia:
        return nvidia
    inventory = _gpu_inventory()
    return [
        {
            "gpu_id": str(item.get("gpu_id") or "").strip(),
            "vendor": item.get("vendor"),
            "name": item.get("name"),
            "utilization_gpu_percent": None,
            "memory_used_mb": None,
            "memory_used_gb": None,
            "memory_total_mb": item.get("memory_total_mb"),
            "memory_total_gb": item.get("memory_total_gb"),
            "temperature_c": None,
            "power_draw_w": None,
            "uuid": item.get("uuid"),
        }
        for item in inventory
        if isinstance(item, dict)
    ]


def collect_system_performance_sample(home: Path, *, previous_cpu_totals: tuple[int, int] | None = None) -> tuple[dict[str, Any], tuple[int, int] | None]:
    cpu_usage_percent, cpu_totals = _cpu_usage_percent(previous_cpu_totals)
    sample = {
        "recorded_at": utc_now(),
        "cpu": {
            "usage_percent": cpu_usage_percent,
            "load_average": _load_average(),
        },
        "memory": _memory_usage_sample(),
        "disks": _disk_usage_sample(home),
        "gpus": _gpu_runtime_sample(),
    }
    return sample, cpu_totals


def hardware_stats_root(home: Path) -> Path:
    return home / "runtime" / "admin" / "hardware"


def hardware_stats_day_path(home: Path, *, day: str | None = None) -> Path:
    resolved_day = day or utc_now().split("T", 1)[0]
    return hardware_stats_root(home) / f"{resolved_day}.jsonl"


def append_hardware_sample(home: Path, sample: dict[str, Any]) -> Path:
    path = hardware_stats_day_path(home)
    append_jsonl(path, sample)
    return path


def _iter_day_range(start_day: date, end_day: date) -> list[date]:
    items: list[date] = []
    cursor = start_day
    while cursor <= end_day:
        items.append(cursor)
        cursor += timedelta(days=1)
    return items


def _parse_recorded_at(value: object) -> datetime | None:
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


def summarize_recent_hardware_samples(home: Path, *, limit: int = 60) -> dict[str, Any]:
    now = datetime.now(UTC)
    window_minutes = max(1, int(limit or 60))
    start_at = now - timedelta(minutes=window_minutes)
    day_paths = [hardware_stats_day_path(home, day=day.isoformat()) for day in _iter_day_range(start_at.date(), now.date())]
    samples: list[dict[str, Any]] = []
    for path in day_paths:
        if not path.exists():
            continue
        for item in read_jsonl(path):
            if not isinstance(item, dict):
                continue
            recorded_at = _parse_recorded_at(item.get("recorded_at"))
            if recorded_at is None or recorded_at < start_at:
                continue
            samples.append(dict(item))
    samples.sort(key=lambda item: str(item.get("recorded_at") or ""))
    path = day_paths[-1] if day_paths else hardware_stats_day_path(home)
    if not samples:
        return {
            "sample_count": 0,
            "window_minutes": window_minutes,
            "latest_sample": None,
            "cpu": {},
            "memory": {},
            "disks": [],
            "gpus": [],
            "log_path": str(path),
        }
    latest = samples[-1]

    def _root_disk_usage(sample: dict[str, Any]) -> float | None:
        disks = sample.get("disks") if isinstance(sample.get("disks"), list) else []
        if not disks:
            return None
        root = next(
            (
                item
                for item in disks
                if isinstance(item, dict) and str(item.get("mount") or "").strip() == "/"
            ),
            None,
        )
        if root is None:
            root = next((item for item in disks if isinstance(item, dict)), None)
        if not isinstance(root, dict):
            return None
        value = root.get("usage_percent")
        return float(value) if isinstance(value, (int, float)) else None

    def numeric_series(extractor):
        values = []
        for sample in samples:
            value = extractor(sample)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    cpu_values = numeric_series(lambda item: ((item.get("cpu") or {}) if isinstance(item.get("cpu"), dict) else {}).get("usage_percent"))
    memory_values = numeric_series(lambda item: ((item.get("memory") or {}) if isinstance(item.get("memory"), dict) else {}).get("usage_percent"))
    root_disk_values = numeric_series(_root_disk_usage)

    disk_latest = latest.get("disks") if isinstance(latest.get("disks"), list) else []
    disk_summary = []
    for item in disk_latest:
        if not isinstance(item, dict):
            continue
        mount = str(item.get("mount") or "").strip()
        values = numeric_series(
            lambda sample, mount=mount: next(
                (
                    entry.get("usage_percent")
                    for entry in (sample.get("disks") or [])
                    if isinstance(entry, dict) and str(entry.get("mount") or "").strip() == mount
                ),
                None,
            )
        )
        disk_summary.append(
            {
                "mount": mount,
                "latest_usage_percent": item.get("usage_percent"),
                "avg_usage_percent": round(sum(values) / len(values), 2) if values else None,
                "max_usage_percent": round(max(values), 2) if values else None,
                "free_gb": item.get("free_gb"),
            }
        )

    latest_gpus = latest.get("gpus") if isinstance(latest.get("gpus"), list) else []
    gpu_summary = []
    for item in latest_gpus:
        if not isinstance(item, dict):
            continue
        gpu_id = str(item.get("gpu_id") or "").strip()
        util_values = numeric_series(
            lambda sample, gpu_id=gpu_id: next(
                (
                    entry.get("utilization_gpu_percent")
                    for entry in (sample.get("gpus") or [])
                    if isinstance(entry, dict) and str(entry.get("gpu_id") or "").strip() == gpu_id
                ),
                None,
            )
        )
        mem_values = numeric_series(
            lambda sample, gpu_id=gpu_id: next(
                (
                    entry.get("memory_used_gb")
                    for entry in (sample.get("gpus") or [])
                    if isinstance(entry, dict) and str(entry.get("gpu_id") or "").strip() == gpu_id
                ),
                None,
            )
        )
        gpu_summary.append(
            {
                "gpu_id": gpu_id,
                "name": item.get("name"),
                "latest_utilization_gpu_percent": item.get("utilization_gpu_percent"),
                "avg_utilization_gpu_percent": round(sum(util_values) / len(util_values), 2) if util_values else None,
                "max_utilization_gpu_percent": round(max(util_values), 2) if util_values else None,
                "latest_memory_used_gb": item.get("memory_used_gb"),
                "max_memory_used_gb": round(max(mem_values), 2) if mem_values else None,
                "memory_total_gb": item.get("memory_total_gb"),
            }
        )

    series = []
    for sample in samples:
        recorded_at = str(sample.get("recorded_at") or "").strip()
        if not recorded_at:
            continue
        cpu = sample.get("cpu") if isinstance(sample.get("cpu"), dict) else {}
        memory = sample.get("memory") if isinstance(sample.get("memory"), dict) else {}
        point = {
            "recorded_at": recorded_at,
            "cpu_usage_percent": cpu.get("usage_percent") if isinstance(cpu.get("usage_percent"), (int, float)) else None,
            "memory_usage_percent": memory.get("usage_percent") if isinstance(memory.get("usage_percent"), (int, float)) else None,
            "root_disk_usage_percent": _root_disk_usage(sample),
        }
        series.append(point)

    return {
        "sample_count": len(samples),
        "window_minutes": window_minutes,
        "latest_sample": latest,
        "cpu": {
            "latest_usage_percent": ((latest.get("cpu") or {}) if isinstance(latest.get("cpu"), dict) else {}).get("usage_percent"),
            "avg_usage_percent": round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else None,
            "max_usage_percent": round(max(cpu_values), 2) if cpu_values else None,
        },
        "memory": {
            "latest_usage_percent": ((latest.get("memory") or {}) if isinstance(latest.get("memory"), dict) else {}).get("usage_percent"),
            "avg_usage_percent": round(sum(memory_values) / len(memory_values), 2) if memory_values else None,
            "max_usage_percent": round(max(memory_values), 2) if memory_values else None,
            "latest_used_gb": ((latest.get("memory") or {}) if isinstance(latest.get("memory"), dict) else {}).get("used_gb"),
            "total_gb": ((latest.get("memory") or {}) if isinstance(latest.get("memory"), dict) else {}).get("total_gb"),
        },
        "root_disk": {
            "latest_usage_percent": _root_disk_usage(latest),
            "avg_usage_percent": round(sum(root_disk_values) / len(root_disk_values), 2) if root_disk_values else None,
            "max_usage_percent": round(max(root_disk_values), 2) if root_disk_values else None,
        },
        "disks": disk_summary,
        "gpus": gpu_summary,
        "series": series,
        "log_path": str(path),
    }


class AdminSystemMonitor:
    def __init__(self, home: Path, *, interval_seconds: int = 60) -> None:
        self.home = Path(home)
        self.interval_seconds = max(10, int(interval_seconds))
        self._previous_cpu_totals: tuple[int, int] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def sample_now(self, *, persist: bool = True) -> dict[str, Any]:
        sample, self._previous_cpu_totals = collect_system_performance_sample(
            self.home,
            previous_cpu_totals=self._previous_cpu_totals,
        )
        if persist:
            append_hardware_sample(self.home, sample)
        return sample

    def latest_summary(self, *, window_minutes: int = 60) -> dict[str, Any]:
        return summarize_recent_hardware_samples(self.home, limit=window_minutes)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _worker() -> None:
            while not self._stop_event.is_set():
                try:
                    self.sample_now(persist=True)
                except Exception:
                    pass
                self._stop_event.wait(self.interval_seconds)

        self._thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="deepscientist-admin-hardware-monitor",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
