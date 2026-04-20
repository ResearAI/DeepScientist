from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import time
from pathlib import Path
from typing import Any
from urllib.request import Request
import zipfile

from .prompt_builder import BenchStorePromptBuilder
from ..config import ConfigManager
from ..network import urlopen_with_proxy as urlopen
from ..runners.metadata import get_runner_metadata
from ..shared import ensure_dir, read_json, read_yaml, resolve_within, slugify, utc_now, write_json


_ENTRY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESOURCE_FIELDS: tuple[tuple[str, str], ...] = (
    ("cpu_cores", "CPU"),
    ("ram_gb", "RAM"),
    ("disk_gb", "Disk"),
    ("gpu_count", "GPU count"),
    ("gpu_vram_gb", "GPU VRAM"),
)
_COST_BAND_RANK = {
    "very_low": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "very_high": 4,
}
_DIFFICULTY_RANK = {
    "easy": 0,
    "medium": 1,
    "hard": 2,
    "expert": 3,
}


def _time_band_upper_hours(value: str | None) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    plus_match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([mhd])\s*\+\s*$", text)
    if plus_match:
        upper = float(plus_match.group(1))
        unit = plus_match.group(2)
        if unit == "m":
            return upper / 60.0
        if unit == "d":
            return upper * 24.0
        return upper
    if text.endswith("m") and text[:-1].strip().isdigit():
        return int(text[:-1].strip()) / 60.0
    if text.endswith("h") and text[:-1].strip().isdigit():
        return float(text[:-1].strip())
    if text.endswith("d") and text[:-1].strip().isdigit():
        return float(text[:-1].strip()) * 24.0
    band_match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*([mh]|d)\s*$", text)
    if band_match:
        upper = float(band_match.group(2))
        unit = band_match.group(3)
        if unit == "m":
            return upper / 60.0
        if unit == "d":
            return upper * 24.0
        return upper
    return None


def _normalize_catalog_locale(value: str | None) -> str:
    normalized = str(value or "en").strip().lower()
    return "zh" if normalized.startswith("zh") else "en"


def _resource_confidence(resources: dict[str, Any]) -> str:
    minimum = resources.get("minimum") if isinstance(resources.get("minimum"), dict) else {}
    recommended = resources.get("recommended") if isinstance(resources.get("recommended"), dict) else {}
    if minimum and recommended:
        return "full"
    if minimum or recommended:
        return "partial"
    return "none"


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Expected boolean, got {value!r}.")


def _sanitize_catalog_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_sanitize_catalog_value(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized[str(key)] = _sanitize_catalog_value(item)
        return normalized
    return str(value)


def _collect_search_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, (str, int, float)):
        normalized = str(value).strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_collect_search_values(item))
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for key, item in value.items():
            key_text = str(key).strip()
            if key_text:
                items.append(key_text)
            items.extend(_collect_search_values(item))
        return items
    normalized = str(value).strip()
    return [normalized] if normalized else []


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Expected number, got {value!r}.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Expected number, got {value!r}.") from exc
    raise ValueError(f"Expected number, got {value!r}.")


def _normalize_string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"`{field_name}` must be a list of strings.")
    items: list[str] = []
    for raw in value:
        normalized = _optional_str(raw)
        if normalized:
            items.append(normalized)
    return items


def _normalize_resource_spec(value: Any, *, field_name: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"`{field_name}` must be an object.")
    normalized: dict[str, float] = {}
    for key, _label in _RESOURCE_FIELDS:
        number = _optional_number(value.get(key))
        if number is not None:
            normalized[key] = number
    return normalized


def _normalize_environment_spec(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "python": None,
            "cuda": None,
            "pytorch": None,
            "flash_attn": None,
            "key_packages": [],
            "notes": [],
        }
    if not isinstance(value, dict):
        raise ValueError("`environment` must be an object.")
    return {
        "python": _optional_str(value.get("python")),
        "cuda": _optional_str(value.get("cuda")),
        "pytorch": _optional_str(value.get("pytorch")),
        "flash_attn": _optional_str(value.get("flash_attn")),
        "key_packages": _normalize_string_list(value.get("key_packages"), field_name="environment.key_packages"),
        "notes": _normalize_string_list(value.get("notes"), field_name="environment.notes"),
    }


def _normalize_dataset_sources(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("`dataset_download.sources` must be a list.")
    sources: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if isinstance(raw, dict):
            sources.append(
                {
                    "kind": _optional_str(raw.get("kind")),
                    "url": _optional_str(raw.get("url")),
                    "access": _optional_str(raw.get("access")),
                    "note": _optional_str(raw.get("note")),
                }
            )
            continue
        normalized = _optional_str(raw)
        if normalized:
            sources.append(
                {
                    "kind": None,
                    "url": normalized,
                    "access": None,
                    "note": None,
                }
            )
            continue
        raise ValueError(f"`dataset_download.sources[{index}]` must be an object or string.")
    return sources


def _normalize_dataset_download_spec(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "primary_method": None,
            "sources": [],
            "notes": [],
        }
    if not isinstance(value, dict):
        raise ValueError("`dataset_download` must be an object.")
    return {
        "primary_method": _optional_str(value.get("primary_method")),
        "sources": _normalize_dataset_sources(value.get("sources")),
        "notes": _normalize_string_list(value.get("notes"), field_name="dataset_download.notes"),
    }


def _normalize_credential_requirements_spec(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "mode": None,
            "items": [],
            "notes": [],
        }
    if not isinstance(value, dict):
        raise ValueError("`credential_requirements` must be an object.")
    return {
        "mode": _optional_str(value.get("mode")),
        "items": _normalize_string_list(value.get("items"), field_name="credential_requirements.items"),
        "notes": _normalize_string_list(value.get("notes"), field_name="credential_requirements.notes"),
    }


def _normalize_launch_profiles(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("`launch_profiles` must be a list.")
    profiles: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"`launch_profiles[{index}]` must be an object.")
        profile = {
            "id": _optional_str(raw.get("id")),
            "label": _optional_str(raw.get("label")),
            "description": _optional_str(raw.get("description")),
        }
        if profile["id"] or profile["label"] or profile["description"]:
            profiles.append(profile)
    return profiles


def _device_summary_from_profile(profile: dict[str, Any]) -> str:
    cpu = profile.get("cpu_cores")
    ram = profile.get("ram_gb")
    disk = profile.get("disk_gb")
    gpu_count = profile.get("gpu_count")
    gpu_vram = profile.get("gpu_vram_gb")
    return (
        f"CPU {cpu if cpu is not None else '?'} cores | "
        f"RAM {ram if ram is not None else '?'}GB | "
        f"Disk {disk if disk is not None else '?'}GB free | "
        f"GPU {gpu_count if gpu_count is not None else '?'} | "
        f"VRAM {gpu_vram if gpu_vram is not None else '?'}GB"
    )


class BenchStoreService:
    def _default_runner_label(self) -> str:
        config = ConfigManager(self.home).load_named_normalized("config")
        runner_name = str(config.get("default_runner") or "codex").strip().lower() or "codex"
        try:
            return get_runner_metadata(runner_name).label
        except KeyError:
            return runner_name.capitalize()

    def __init__(self, home: Path, *, repo_root: Path) -> None:
        self.home = Path(home)
        self.repo_root = Path(repo_root)
        self.workspace_root = self.repo_root.parent
        self.catalog_root = self.repo_root / "AISB" / "catalog"
        self.prompt_builder = BenchStorePromptBuilder(self.repo_root)

    @property
    def runtime_root(self) -> Path:
        return ensure_dir(self.home / "runtime" / "benchstore")

    @property
    def downloads_root(self) -> Path:
        return ensure_dir(self.runtime_root / "downloads")

    @property
    def install_records_root(self) -> Path:
        return ensure_dir(self.runtime_root / "installs")

    @property
    def install_root(self) -> Path:
        return ensure_dir(self.home / "AISB" / "installs")

    def list_entries(self, *, hardware_payload: dict[str, Any] | None = None, locale: str = "en") -> dict[str, Any]:
        catalog = self._scan_catalog(hardware_payload=hardware_payload, locale=locale)
        return {
            "ok": True,
            "catalog_root": str(self.catalog_root),
            "device_profile": catalog["device_profile"],
            "device_capacity": catalog["device_capacity"],
            "device_summary": catalog["device_summary"],
            "invalid_entries": catalog["invalid_entries"],
            "filter_options": catalog["filter_options"],
            "shelves": catalog["shelves"],
            "items": catalog["items"],
            "total": len(catalog["items"]),
        }

    def get_entry(self, entry_id: str, *, hardware_payload: dict[str, Any] | None = None, locale: str = "en") -> dict[str, Any]:
        normalized_id = self._normalize_identifier(entry_id, fallback="")
        if not normalized_id:
            raise FileNotFoundError("Benchmark id is required.")
        catalog = self._scan_catalog(hardware_payload=hardware_payload, locale=locale)
        entry_path = self._find_entry_path(normalized_id, locale=locale)
        raw_entry = self._load_entry_file(entry_path, include_raw_payload=True)
        for item in catalog["items"]:
            if str(item.get("id") or "") == normalized_id:
                detail = dict(item)
                install_state = self.install_state(normalized_id)
                detail["install_state"] = install_state
                detail["raw_payload"] = raw_entry.get("raw_payload")
                detail["setup_prompt_preview"] = self.prompt_builder.build_setup_prompt(
                    entry=detail,
                    hardware_payload=hardware_payload,
                    benchmark_local_path=str(install_state.get("local_path") or ""),
                    locale=locale,
                )
                return {
                    "ok": True,
                    "device_profile": catalog["device_profile"],
                    "device_summary": catalog["device_summary"],
                    "entry": detail,
                }
        raise FileNotFoundError(f"Unknown BenchStore entry `{normalized_id}`.")

    def _scan_catalog(self, *, hardware_payload: dict[str, Any] | None = None, locale: str = "en") -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        invalid_entries: list[dict[str, str]] = []
        by_id: dict[str, dict[str, Any]] = {}
        device_profile = self._device_profile(hardware_payload)
        device_capacity = self._device_capacity_profile(device_profile)
        device_summary = (
            str(hardware_payload.get("prompt_hardware_summary") or "").strip()
            if isinstance(hardware_payload, dict)
            else ""
        ) or _device_summary_from_profile(device_profile)

        if self.catalog_root.exists():
            for path in self._catalog_entry_paths(locale=locale):
                try:
                    entry = self._load_entry_file(path)
                except ValueError as exc:
                    invalid_entries.append(
                        {
                            "source_file": str(path.relative_to(self.repo_root)),
                            "message": str(exc),
                        }
                    )
                    continue
                if entry["id"] in by_id:
                    invalid_entries.append(
                        {
                            "source_file": str(path.relative_to(self.repo_root)),
                            "message": f"Duplicate benchmark id `{entry['id']}`.",
                        }
                    )
                    continue
                if hardware_payload is not None:
                    entry["compatibility"] = self._compatibility(entry=entry, device_profile=device_profile, device_summary=device_summary)
                    entry["recommendation"] = self._recommendation_profile(
                        entry=entry,
                        device_profile=device_profile,
                        device_capacity=device_capacity,
                        compatibility=entry["compatibility"],
                    )
                entry["install_state"] = self.install_state(entry["id"])
                by_id[entry["id"]] = entry
                items.append(entry)

        items.sort(key=self._entry_sort_key)
        filter_options = self._filter_options(items)
        shelves = self._shelves(items)
        return {
            "items": items,
            "invalid_entries": invalid_entries,
            "device_profile": device_profile,
            "device_capacity": device_capacity,
            "device_summary": device_summary,
            "filter_options": filter_options,
            "shelves": shelves,
        }

    def _catalog_entry_paths(self, *, locale: str = "en") -> list[Path]:
        normalized_locale = _normalize_catalog_locale(locale)
        base_paths = sorted(
            path
            for path in self.catalog_root.rglob("*.yaml")
            if not path.name.endswith(".zh.yaml")
        )
        resolved: list[Path] = []
        for path in base_paths:
            if normalized_locale == "zh":
                zh_path = path.with_name(f"{path.stem}.zh.yaml")
                if zh_path.exists():
                    resolved.append(zh_path)
                    continue
            resolved.append(path)
        return resolved

    def _load_entry_file(self, path: Path, *, include_raw_payload: bool = False) -> dict[str, Any]:
        payload = read_yaml(path, {})
        if not isinstance(payload, dict):
            raise ValueError("BenchStore entry must be a YAML object.")

        name = _optional_str(payload.get("name"))
        if not name:
            raise ValueError("BenchStore entry requires non-empty `name`.")

        entry_id = self._normalize_identifier(payload.get("id"), fallback=path.stem)
        if not entry_id:
            raise ValueError("BenchStore entry id could not be derived.")

        paper_raw = payload.get("paper") if isinstance(payload.get("paper"), dict) else {}
        download_raw = payload.get("download") if isinstance(payload.get("download"), dict) else {}
        dataset_download_raw = payload.get("dataset_download") if isinstance(payload.get("dataset_download"), dict) else payload.get("dataset_download")
        credential_requirements_raw = payload.get("credential_requirements") if isinstance(payload.get("credential_requirements"), dict) else payload.get("credential_requirements")
        resources_raw = payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
        environment_raw = payload.get("environment") if isinstance(payload.get("environment"), dict) else payload.get("environment")
        commercial_raw = payload.get("commercial") if isinstance(payload.get("commercial"), dict) else {}
        display_raw = payload.get("display") if isinstance(payload.get("display"), dict) else {}
        image_path = _optional_str(payload.get("image_path"))

        entry = {
            "schema_version": int(_optional_number(payload.get("schema_version")) or 1),
            "id": entry_id,
            "name": name,
            "version": _optional_str(payload.get("version")),
            "one_line": _optional_str(payload.get("one_line")),
            "task_description": _optional_str(payload.get("task_description")),
            "capability_tags": _normalize_string_list(payload.get("capability_tags"), field_name="capability_tags"),
            "aisb_direction": _optional_str(payload.get("aisb_direction")),
            "track_fit": _normalize_string_list(payload.get("track_fit"), field_name="track_fit"),
            "task_mode": _optional_str(payload.get("task_mode")),
            "requires_execution": _optional_bool(payload.get("requires_execution")),
            "requires_paper": _optional_bool(payload.get("requires_paper")),
            "integrity_level": _optional_str(payload.get("integrity_level")),
            "snapshot_status": _optional_str(payload.get("snapshot_status")),
            "support_level": _optional_str(payload.get("support_level")),
            "primary_outputs": _normalize_string_list(payload.get("primary_outputs"), field_name="primary_outputs"),
            "launch_profiles": _normalize_launch_profiles(payload.get("launch_profiles")),
            "cost_band": _optional_str(payload.get("cost_band")),
            "time_band": _optional_str(payload.get("time_band")),
            "difficulty": _optional_str(payload.get("difficulty")),
            "data_access": _optional_str(payload.get("data_access")),
            "risk_flags": _normalize_string_list(payload.get("risk_flags"), field_name="risk_flags"),
            "risk_notes": _normalize_string_list(payload.get("risk_notes"), field_name="risk_notes"),
            "recommended_when": _optional_str(payload.get("recommended_when")),
            "not_recommended_when": _optional_str(payload.get("not_recommended_when")),
            "paper": {
                "title": _optional_str(paper_raw.get("title")),
                "venue": _optional_str(paper_raw.get("venue")),
                "year": int(_optional_number(paper_raw.get("year"))) if _optional_number(paper_raw.get("year")) is not None else None,
                "url": _optional_str(paper_raw.get("url")),
            },
            "download": {
                "url": _optional_str(download_raw.get("url")),
                "archive_type": _optional_str(download_raw.get("archive_type")),
                "local_dir_name": _optional_str(download_raw.get("local_dir_name")),
                "sha256": _optional_str(download_raw.get("sha256")),
                "size_bytes": int(_optional_number(download_raw.get("size_bytes"))) if _optional_number(download_raw.get("size_bytes")) is not None else None,
                "provider": _optional_str(download_raw.get("provider")),
                "repo": _optional_str(download_raw.get("repo")),
                "tag": _optional_str(download_raw.get("tag")),
                "asset_name": _optional_str(download_raw.get("asset_name")),
            },
            "dataset_download": _normalize_dataset_download_spec(dataset_download_raw),
            "credential_requirements": _normalize_credential_requirements_spec(credential_requirements_raw),
            "resources": {
                "minimum": _normalize_resource_spec(resources_raw.get("minimum"), field_name="resources.minimum"),
                "recommended": _normalize_resource_spec(resources_raw.get("recommended"), field_name="resources.recommended"),
            },
            "environment": _normalize_environment_spec(environment_raw),
            "commercial": {
                "annual_fee": commercial_raw.get("annual_fee"),
            },
            "display": {
                "palette_seed": _optional_str(display_raw.get("palette_seed")),
                "art_style": _optional_str(display_raw.get("art_style")),
                "accent_priority": _optional_str(display_raw.get("accent_priority")),
            },
            "image_path": image_path,
            "image_url": f"/api/benchstore/entries/{entry_id}/image" if image_path else None,
            "source_file": str(path.relative_to(self.repo_root)),
        }
        if include_raw_payload:
            entry["raw_payload"] = _sanitize_catalog_value(payload)
        entry["search_text"] = self._search_text(entry, raw_payload=payload)
        return entry

    def install_state(self, entry_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_identifier(entry_id, fallback="")
        if not normalized_id:
            return {"status": "not_installed"}
        payload = read_json(self.install_record_path(normalized_id), default=None)
        if not isinstance(payload, dict):
            return {"status": "not_installed"}
        local_path = str(payload.get("local_path") or "").strip()
        if local_path and not Path(local_path).exists():
            return {
                **payload,
                "status": "missing",
            }
        return payload

    def install_record_path(self, entry_id: str) -> Path:
        normalized_id = self._normalize_identifier(entry_id, fallback="")
        return self.install_records_root / f"{normalized_id}.json"

    def entry_install_dir(self, entry: dict[str, Any]) -> Path:
        download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
        preferred_name = _optional_str(download.get("local_dir_name"))
        base_name = preferred_name or self._normalize_identifier(entry.get("id"), fallback=str(entry.get("name") or "bench"))
        return self.install_root / base_name

    @staticmethod
    def _local_reference_paths(local_root: Path | None) -> dict[str, Any]:
        if local_root is None or not local_root.exists():
            return {
                "benchmark_root": None,
                "latex_markdown_path": None,
                "dataset_paths": [],
            }
        latex_path: Path | None = None
        direct_latex = local_root / "latex.md"
        if direct_latex.exists() and direct_latex.is_file():
            latex_path = direct_latex
        else:
            for candidate in sorted(local_root.rglob("latex.md")):
                if candidate.is_file():
                    latex_path = candidate
                    break
        dataset_paths: list[str] = []
        seen_paths: set[str] = set()
        for relative in ("dataset", "datasets", "data", "bench_data", "corpus", "inputs"):
            candidate = local_root / relative
            if not candidate.exists():
                continue
            normalized = str(candidate)
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            dataset_paths.append(normalized)
        return {
            "benchmark_root": str(local_root),
            "latex_markdown_path": str(latex_path) if latex_path is not None else None,
            "dataset_paths": dataset_paths,
        }

    def infer_archive_type(self, entry: dict[str, Any]) -> str:
        download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
        explicit = str(download.get("archive_type") or "").strip().lower()
        if explicit:
            return explicit
        url = str(download.get("url") or "").strip().lower()
        if url.endswith(".tar.gz") or url.endswith(".tgz"):
            return "tar.gz"
        if url.endswith(".tar"):
            return "tar"
        return "zip"

    def write_install_record(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        write_json(self.install_record_path(entry_id), payload)
        return payload

    def run_install_task(
        self,
        *,
        entry_id: str,
        reporter: Any,
        task_id: str,
    ) -> dict[str, Any]:
        entry = self._find_entry(entry_id)
        download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
        url = str(download.get("url") or "").strip()
        if not url:
            raise ValueError(f"BenchStore entry `{entry_id}` does not define `download.url`.")

        archive_type = self.infer_archive_type(entry)
        expected_sha256 = str(download.get("sha256") or "").strip().lower() or None
        expected_size_bytes = int(download.get("size_bytes")) if download.get("size_bytes") is not None else None
        install_dir = self.entry_install_dir(entry)
        temp_extract_root = self.install_root / f".extract-{install_dir.name}-{task_id}"
        archive_suffix = ".zip" if archive_type == "zip" else ".tar.gz" if archive_type == "tar.gz" else ".tar"
        archive_path = self.downloads_root / f"{task_id}{archive_suffix}"
        initial_metadata = {
            "entry_id": entry["id"],
            "entry_name": entry["name"],
            "download_url": url,
            "archive_type": archive_type,
            "install_dir": str(install_dir),
            "bytes_downloaded": 0,
            "bytes_total": None,
            "speed_bytes_per_sec": None,
            "eta_seconds": None,
            "expected_sha256": expected_sha256,
            "expected_size_bytes": expected_size_bytes,
        }
        reporter.start(total=None, current_step="download", message=f"Downloading `{entry['name']}`.")
        reporter.progress(current_step="download", message=f"Downloading `{entry['name']}`.", metadata=initial_metadata)

        self.write_install_record(
            entry["id"],
            {
                "entry_id": entry["id"],
                "status": "installing",
                "task_id": task_id,
                "local_path": str(install_dir),
                "download_url": url,
                "archive_type": archive_type,
                "updated_at": utc_now(),
            },
        )

        bytes_downloaded = 0
        bytes_total: int | None = None
        sha256 = hashlib.sha256()
        request = Request(url, headers={"User-Agent": "DeepScientist-BenchStore/1.0"})
        try:
            with urlopen(request, timeout=30.0) as response:
                raw_length = response.headers.get("Content-Length")
                if raw_length and raw_length.isdigit():
                    bytes_total = int(raw_length)
                ensure_dir(archive_path.parent)
                with archive_path.open("wb") as handle:
                    started_at = time.monotonic()
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        handle.write(chunk)
                        sha256.update(chunk)
                        bytes_downloaded += len(chunk)
                        elapsed = max(time.monotonic() - started_at, 0.001)
                        speed = bytes_downloaded / elapsed
                        eta = ((bytes_total - bytes_downloaded) / speed) if bytes_total and speed > 0 else None
                        reporter.progress(
                            current=bytes_downloaded,
                            total=bytes_total,
                            current_step="download",
                            message=f"Downloading `{entry['name']}`.",
                            metadata={
                                **initial_metadata,
                                "bytes_downloaded": bytes_downloaded,
                                "bytes_total": bytes_total,
                                "speed_bytes_per_sec": round(speed, 2),
                                "eta_seconds": round(eta, 2) if eta is not None else None,
                            },
                        )

            if temp_extract_root.exists():
                shutil.rmtree(temp_extract_root)
            ensure_dir(temp_extract_root)
            actual_sha256 = sha256.hexdigest()
            if expected_size_bytes is not None and bytes_downloaded != expected_size_bytes:
                raise ValueError(f"Downloaded archive size mismatch for `{entry['id']}`: expected {expected_size_bytes} bytes, got {bytes_downloaded} bytes.")
            reporter.progress(
                current=bytes_total or bytes_downloaded,
                total=bytes_total or bytes_downloaded or None,
                current_step="verify",
                message=f"Verifying SHA-256 for `{entry['name']}`.",
                metadata={
                    **initial_metadata,
                    "bytes_downloaded": bytes_downloaded,
                    "bytes_total": bytes_total,
                    "archive_path": str(archive_path),
                    "archive_sha256": actual_sha256,
                    "expected_sha256": expected_sha256,
                },
            )
            if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
                raise ValueError(f"SHA-256 mismatch for `{entry['id']}`: expected {expected_sha256}, got {actual_sha256}.")
            reporter.progress(
                current=bytes_total or bytes_downloaded,
                total=bytes_total or bytes_downloaded or None,
                current_step="extract",
                message=f"Extracting `{entry['name']}`.",
                metadata={
                    **initial_metadata,
                    "bytes_downloaded": bytes_downloaded,
                    "bytes_total": bytes_total,
                    "archive_path": str(archive_path),
                },
            )
            self._extract_archive(archive_path=archive_path, archive_type=archive_type, extract_root=temp_extract_root)
            install_source = self._resolved_install_source(temp_extract_root)
            if install_dir.exists():
                shutil.rmtree(install_dir)
            ensure_dir(install_dir.parent)
            install_source.replace(install_dir)
            if temp_extract_root.exists() and temp_extract_root != install_dir:
                shutil.rmtree(temp_extract_root, ignore_errors=True)

            record = self.write_install_record(
                entry["id"],
                {
                    "entry_id": entry["id"],
                    "entry_name": entry["name"],
                    "status": "installed",
                    "task_id": task_id,
                    "local_path": str(install_dir),
                    "download_url": url,
                    "archive_type": archive_type,
                    "archive_path": str(archive_path),
                    "archive_sha256": actual_sha256,
                    "expected_sha256": expected_sha256,
                    "bytes_downloaded": bytes_downloaded,
                    "bytes_total": bytes_total,
                    "installed_at": utc_now(),
                    "updated_at": utc_now(),
                },
            )
            reporter.complete(
                message=f"Installed `{entry['name']}`.",
                result_path=str(self.install_record_path(entry["id"])),
                data={"install_record": record},
            )
            return record
        except Exception:
            self.write_install_record(
                entry["id"],
                {
                    "entry_id": entry["id"],
                    "entry_name": entry["name"],
                    "status": "failed",
                    "task_id": task_id,
                    "local_path": str(install_dir),
                    "download_url": url,
                    "archive_type": archive_type,
                    "updated_at": utc_now(),
                },
            )
            raise
        finally:
            if temp_extract_root.exists():
                shutil.rmtree(temp_extract_root, ignore_errors=True)

    def _find_entry(self, entry_id: str, *, locale: str = "en") -> dict[str, Any]:
        normalized_id = self._normalize_identifier(entry_id, fallback="")
        if not normalized_id:
            raise FileNotFoundError("Benchmark id is required.")
        path = self._find_entry_path(normalized_id, locale=locale)
        return self._load_entry_file(path, include_raw_payload=True)

    def _find_entry_path(self, entry_id: str, *, locale: str = "en") -> Path:
        normalized_id = self._normalize_identifier(entry_id, fallback="")
        if not normalized_id:
            raise FileNotFoundError("Benchmark id is required.")
        for path in self._catalog_entry_paths(locale=locale):
            try:
                entry = self._load_entry_file(path)
            except ValueError:
                continue
            if str(entry.get("id") or "") == normalized_id:
                return path
        raise FileNotFoundError(f"Unknown BenchStore entry `{normalized_id}`.")

    def entry_image_asset_path(self, entry_id: str, *, locale: str = "en") -> Path:
        path = self._find_entry_path(entry_id, locale=locale)
        entry = self._load_entry_file(path)
        image_path = _optional_str(entry.get("image_path"))
        if not image_path:
            raise FileNotFoundError(f"BenchStore entry `{entry_id}` does not define `image_path`.")
        resolved = self._resolve_entry_asset_path(path, image_path)
        if resolved is None or not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"BenchStore image asset for `{entry_id}` was not found.")
        return resolved

    def build_setup_packet(
        self,
        *,
        entry_id: str,
        hardware_payload: dict[str, Any] | None = None,
        locale: str = "zh",
    ) -> dict[str, Any]:
        is_zh = str(locale or "").strip().lower().startswith("zh")
        entry = self._find_entry(entry_id, locale=locale)
        install_state = self.install_state(entry["id"])
        device_profile = self._device_profile(hardware_payload)
        device_summary = (
            str(hardware_payload.get("prompt_hardware_summary") or "").strip()
            if isinstance(hardware_payload, dict)
            else ""
        ) or _device_summary_from_profile(device_profile)
        compatibility = self._compatibility(entry=entry, device_profile=device_profile, device_summary=device_summary)
        local_path = str(install_state.get("local_path") or "").strip() or None
        if bool(entry.get("requires_execution")) and install_state.get("status") != "installed":
            raise ValueError("This benchmark must be installed locally before launch.")
        local_refs = self._local_reference_paths(Path(local_path) if local_path else None)
        local_dataset_paths = [str(item).strip() for item in (local_refs.get("dataset_paths") or []) if str(item).strip()]
        latex_markdown_path = str(local_refs.get("latex_markdown_path") or "").strip() or None

        paper = entry.get("paper") if isinstance(entry.get("paper"), dict) else {}
        dataset_download = entry.get("dataset_download") if isinstance(entry.get("dataset_download"), dict) else {}
        credential_requirements = entry.get("credential_requirements") if isinstance(entry.get("credential_requirements"), dict) else {}
        project_title = f"{entry['name']} 全自动研究" if is_zh else f"{entry['name']} Autonomous Research"
        one_line = str(entry.get("one_line") or "").strip()
        task_description = str(entry.get("task_description") or "").strip()
        venue = str(paper.get("venue") or "").strip()
        year = paper.get("year")
        requires_paper = bool(entry.get("requires_paper")) if entry.get("requires_paper") is not None else True
        recommendation_tier = str(compatibility.get("recommendation_tier") or "").strip() or "unknown"
        unknown_text = "未知" if is_zh else "unknown"
        not_available_text = "不可用" if is_zh else "not available"
        none_text = "无" if is_zh else "none"
        unspecified_text = "未说明" if is_zh else "unspecified"
        localized_device_fit = (
            {
                "recommended": "推荐配置",
                "minimum": "满足最低配置",
                "unsupported": "低于最低配置",
                "unknown": "未知",
            }.get(recommendation_tier, recommendation_tier)
            if is_zh
            else recommendation_tier
        )

        benchmark_goal = task_description or one_line or (
            f"忠实运行 benchmark `{entry['name']}`，并在当前证据下产出最强、最合理的全自动结果。"
            if is_zh
            else f"Run the benchmark `{entry['name']}` faithfully and produce the strongest justified autonomous result."
        )
        fit_lines = compatibility.get("recommended_reasons") or compatibility.get("minimum_reasons") or []
        constraints = [
            (
                f"- 基准本地路径: {local_path or not_available_text}"
                if is_zh
                else f"- benchmark_local_path: {local_path or not_available_text}"
            ),
            (
                f"- 设备摘要: {device_summary}"
                if is_zh
                else f"- device_summary: {device_summary}"
            ),
            (
                f"- 设备适配: {localized_device_fit or unknown_text}"
                if is_zh
                else f"- device_fit: {localized_device_fit or unknown_text}"
            ),
            (
                "- 设备边界规则: 不要围绕当前本机有效设备边界之外的算力做计划。"
                if is_zh
                else "- device_boundary_rule: do not plan around compute outside the current effective local device boundary."
            ),
        ]
        if fit_lines:
            constraints.append("- 设备兼容性说明:" if is_zh else "- compatibility_notes:")
            constraints.extend([f"  - {item}" for item in fit_lines[:6]])
        if local_dataset_paths:
            constraints.append("- 本地数据路径:" if is_zh else "- local_dataset_paths:")
            constraints.extend([f"  - {item}" for item in local_dataset_paths[:8]])
        if latex_markdown_path:
            constraints.append(
                f"- LaTeX Markdown 路径: {latex_markdown_path}"
                if is_zh
                else f"- latex_markdown_path: {latex_markdown_path}"
            )
        credential_mode = str(credential_requirements.get("mode") or "").strip()
        credential_items = [str(item).strip() for item in (credential_requirements.get("items") or []) if str(item).strip()]
        if credential_mode or credential_items:
            constraints.append(
                (
                    f"- 凭证要求: 模式={credential_mode or unspecified_text}；项目={', '.join(credential_items) or none_text}"
                    if is_zh
                    else f"- credential_requirements: mode={credential_mode or unspecified_text} items={', '.join(credential_items) or none_text}"
                )
            )
        resources = entry.get("resources") if isinstance(entry.get("resources"), dict) else {}
        minimum_resources = resources.get("minimum") if isinstance(resources.get("minimum"), dict) else {}
        recommended_resources = resources.get("recommended") if isinstance(resources.get("recommended"), dict) else {}
        if minimum_resources:
            constraints.append(
                f"- 最低资源需求: {json.dumps(minimum_resources, ensure_ascii=False)}"
                if is_zh
                else f"- minimum_resources: {json.dumps(minimum_resources, ensure_ascii=False)}"
            )
        if recommended_resources:
            constraints.append(
                f"- 推荐资源需求: {json.dumps(recommended_resources, ensure_ascii=False)}"
                if is_zh
                else f"- recommended_resources: {json.dumps(recommended_resources, ensure_ascii=False)}"
            )
        if recommendation_tier == "unsupported":
            constraints.append(
                "- 启动提醒: 当前设备低于 benchmark 的最低目标，但仍允许启动。"
                if is_zh
                else "- launch_warning: current device is below the benchmark minimum target, but launch remains allowed."
            )
            constraints.append(
                "- 启动提醒规则: 如果本地算力成为瓶颈，应在 benchmark 边界内保守降级，而不是假设额外硬件。"
                if is_zh
                else "- launch_warning_rule: if local compute becomes the bottleneck, stay within the benchmark scope and degrade gracefully instead of expanding hardware assumptions."
            )
        if venue:
            constraints.append(f"- 论文场地: {venue}" if is_zh else f"- paper_venue: {venue}")
        if year:
            constraints.append(f"- 论文年份: {year}" if is_zh else f"- paper_year: {year}")
        if requires_paper:
            constraints.append(
                "- 交付规则: 除非用户后续主动收窄范围，否则论文级交付仍然在 scope 内。"
                if is_zh
                else "- delivery_rule: paper-facing output remains in scope unless the user later narrows scope."
            )
        else:
            constraints.append(
                "- 交付规则: 当前以 benchmark 结果优先，不默认进入论文打包。"
                if is_zh
                else "- delivery_rule: optimize for the strongest justified benchmark result rather than paper-first packaging."
            )

        objectives = (
            [
                "1. 建立一个与 benchmark 保持一致的可信起点。",
                "2. 在当前设备范围内，生成一版可直接进入全自动模式的启动项。",
                "3. 启动后优先保持 benchmark faithful，而不是无边界扩展任务。",
            ]
            if is_zh
            else [
                "1. Establish a credible starting point that stays faithful to the benchmark.",
                "2. Prepare a launch-ready autonomous start form within the current device boundary.",
                "3. After launch, keep the work benchmark-faithful instead of expanding scope without limits.",
            ]
        )
        if requires_paper:
            objectives.append("4. 保持论文级交付仍然在 scope 内。" if is_zh else "4. Keep paper-facing delivery in scope.")
        else:
            objectives.append(
                "4. 当前以结果优先，不默认进入论文写作。"
                if is_zh
                else "4. Optimize for benchmark results first without defaulting into paper writing."
            )
        if recommendation_tier == "unsupported":
            objectives.append(
                "5. 允许直接启动，但要先识别当前设备不足会影响哪些环节，并优先选择在本机可落地的 faithful 路径。"
                if is_zh
                else "5. Launch is still allowed, but first identify which steps are limited by the current device and prefer a faithful path that can actually run locally."
            )
        if credential_items:
            objectives.append(
                "6. 启动前确认可用的 API Key / 资源凭证，并根据可用资源收窄执行路线。"
                if is_zh
                else "6. Confirm available API keys / resource credentials before launch and narrow the execution path accordingly."
            )

        baseline_url_lines: list[str] = []
        download_url = str(entry.get("download", {}).get("url") or "").strip() if isinstance(entry.get("download"), dict) else ""
        if download_url:
            baseline_url_lines.append(download_url)
        if local_path:
            baseline_url_lines.append(local_path)
        baseline_url_lines.extend(local_dataset_paths)

        paper_url_lines: list[str] = []
        paper_url = str(paper.get("url") or "").strip()
        if paper_url:
            paper_url_lines.append(paper_url)
        if latex_markdown_path:
            paper_url_lines.append(latex_markdown_path)

        suggested_form = {
            "title": project_title,
            "goal": benchmark_goal,
            "baseline_id": "",
            "baseline_variant_id": "",
            "baseline_source_mode": "auto",
            "execution_start_mode": "execute_immediately",
            "baseline_acceptance_target": "comparison_ready",
            "baseline_urls": "\n".join(baseline_url_lines),
            "paper_urls": "\n".join(paper_url_lines),
            "runtime_constraints": "\n".join(constraints),
            "objectives": "\n".join(objectives),
            "need_research_paper": requires_paper,
            "research_intensity": "balanced",
            "decision_policy": "autonomous",
            "launch_mode": "standard",
            "standard_profile": "canonical_research_graph",
            "custom_profile": "freeform",
            "review_followup_policy": "audit_only",
            "baseline_execution_policy": "auto",
            "manuscript_edit_mode": "none",
            "entry_state_summary": "\n".join(
                [
                    item
                    for item in [
                        (
                            f"基准本地路径: {local_path}"
                            if is_zh and local_path
                            else f"benchmark_local_path: {local_path}"
                            if local_path
                            else ""
                        ),
                        (
                            f"本地数据路径: {', '.join(local_dataset_paths)}"
                            if is_zh and local_dataset_paths
                            else f"local_dataset_paths: {', '.join(local_dataset_paths)}"
                            if local_dataset_paths
                            else ""
                        ),
                        (
                            f"LaTeX Markdown 路径: {latex_markdown_path}"
                            if is_zh and latex_markdown_path
                            else f"latex_markdown_path: {latex_markdown_path}"
                            if latex_markdown_path
                            else ""
                        ),
                    ]
                    if item
                ]
            ),
            "review_summary": "",
            "review_materials": "",
            "custom_brief": (
                (
                    f"基准来源: {entry['name']} ({entry['id']})。"
                    f"本地路径: {local_path or unknown_text}。"
                    f"设备适配: {localized_device_fit or unknown_text}。"
                    f"LaTeX 路径: {latex_markdown_path or none_text}。"
                    f"是否需要用户确认凭证/资源: {', '.join(credential_items) if credential_items else '可能仅剩少量运行时 / API 细节'}。"
                )
                if is_zh
                else (
                    f"Benchmark source: {entry['name']} ({entry['id']}). "
                    f"Local path: {local_path or unknown_text}. "
                    f"Device fit: {localized_device_fit or unknown_text}. "
                    f"Latex path: {latex_markdown_path or none_text}. "
                    f"Need user confirmation for credentials/resources: {', '.join(credential_items) if credential_items else 'maybe runtime/API specifics only'}."
                )
            ),
            "user_language": "zh" if is_zh else "en",
        }

        startup_instruction = "\n".join(
            [
                "BenchStore 全自动启动" if is_zh else "BenchStore Autonomous Launch",
                f"- 基准 ID: {entry['id']}" if is_zh else f"- benchmark_id: {entry['id']}",
                f"- 基准名称: {entry['name']}" if is_zh else f"- benchmark_name: {entry['name']}",
                (
                    f"- 基准本地路径: {local_path or unknown_text}"
                    if is_zh
                    else f"- benchmark_local_path: {local_path or unknown_text}"
                ),
                (
                    f"- 设备适配: {localized_device_fit or unknown_text}"
                    if is_zh
                    else f"- device_fit: {localized_device_fit or unknown_text}"
                ),
                "",
                "核心 benchmark 目标" if is_zh else "Primary Benchmark Goal",
                benchmark_goal,
                "",
                "运行约束" if is_zh else "Operational Constraints",
                "\n".join(constraints),
                "",
                "Setup Agent 指引" if is_zh else "Setup Agent Guidance",
                self.prompt_builder.build_setup_prompt(
                    entry=entry,
                    hardware_payload=hardware_payload,
                    benchmark_local_path=local_path,
                    locale=locale,
                ),
            ]
        ).strip()

        accent_color = "clay" if compatibility.get("recommended_ok") else "mist"
        launch_payload = {
            "title": project_title,
            "goal": startup_instruction,
            "initial_message": startup_instruction,
            "startup_contract": {
                "schema_version": 1,
                "workspace_mode": "autonomous",
                "launch_mode": "custom",
                "custom_profile": "freeform",
                "decision_policy": "autonomous",
                "need_research_paper": requires_paper,
                "project_display": {
                    "template": "experiment",
                    "accent_color": accent_color,
                    "background_style": "cloud",
                },
                "benchstore_context": {
                    "schema_version": 1,
                    "entry_id": entry.get("id"),
                    "entry_name": entry.get("name"),
                    "one_line": entry.get("one_line"),
                    "task_description": entry.get("task_description"),
                    "paper": paper,
                    "capability_tags": entry.get("capability_tags") or [],
                    "track_fit": entry.get("track_fit") or [],
                    "task_mode": entry.get("task_mode"),
                    "requires_execution": entry.get("requires_execution"),
                    "requires_paper": entry.get("requires_paper"),
                    "snapshot_status": entry.get("snapshot_status"),
                    "support_level": entry.get("support_level"),
                    "primary_outputs": entry.get("primary_outputs") or [],
                    "launch_profiles": entry.get("launch_profiles") or [],
                    "resources": entry.get("resources") or {},
                    "environment": entry.get("environment") or {},
                    "image_path": entry.get("image_path"),
                    "image_url": entry.get("image_url"),
                    "recommended_when": entry.get("recommended_when"),
                    "not_recommended_when": entry.get("not_recommended_when"),
                    "download": entry.get("download") or {},
                    "dataset_download": dataset_download,
                    "credential_requirements": credential_requirements,
                    "risk_flags": entry.get("risk_flags") or [],
                    "risk_notes": entry.get("risk_notes") or [],
                    "integrity_level": entry.get("integrity_level"),
                    "version": entry.get("version"),
                    "commercial": entry.get("commercial") or {},
                    "display": entry.get("display") or {},
                    "compatibility": compatibility,
                    "benchmark_local_path": local_path,
                    "local_dataset_paths": local_dataset_paths,
                    "latex_markdown_path": latex_markdown_path,
                    "setup_agent_label": f"BenchStore Setup Agent · {self._default_runner_label()}",
                    "catalog_source_file": entry.get("source_file"),
                    "raw_payload": entry.get("raw_payload") or {},
                },
            },
        }
        return {
            "entry_id": entry["id"],
            "assistant_label": f"BenchStore Setup Agent · {self._default_runner_label()}",
            "project_title": project_title,
            "benchmark_local_path": local_path,
            "local_dataset_paths": local_dataset_paths,
            "latex_markdown_path": latex_markdown_path,
            "device_summary": device_summary,
            "device_fit": compatibility.get("recommendation_tier"),
            "requires_paper": requires_paper,
            "benchmark_goal": benchmark_goal,
            "constraints": constraints,
            "suggested_form": suggested_form,
            "startup_instruction": startup_instruction,
            "launch_payload": launch_payload,
        }

    def _extract_archive(self, *, archive_path: Path, archive_type: str, extract_root: Path) -> None:
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    member_name = str(member.filename or "").replace("\\", "/").lstrip("/")
                    if not member_name:
                        continue
                    resolve_within(extract_root, member_name)
                    archive.extract(member, path=extract_root)
            return
        if archive_type in {"tar.gz", "tar"}:
            mode = "r:gz" if archive_type == "tar.gz" else "r:"
            with tarfile.open(archive_path, mode) as archive:
                for member in archive.getmembers():
                    member_name = str(member.name or "").replace("\\", "/").lstrip("/")
                    if not member_name:
                        continue
                    resolve_within(extract_root, member_name)
                archive.extractall(path=extract_root)
            return
        raise ValueError(f"Unsupported archive type `{archive_type}`.")

    @staticmethod
    def _resolved_install_source(extract_root: Path) -> Path:
        children = [
            item
            for item in extract_root.iterdir()
            if item.name not in {"__MACOSX"} and not item.name.startswith(".")
        ]
        directories = [item for item in children if item.is_dir()]
        files = [item for item in children if item.is_file()]
        if len(directories) == 1 and not files:
            return directories[0]
        return extract_root

    def _normalize_identifier(self, value: Any, *, fallback: str) -> str:
        candidate = _optional_str(value) or _optional_str(fallback) or slugify(fallback or "bench")
        normalized = str(candidate).strip()
        if not normalized:
            return ""
        if _ENTRY_ID_PATTERN.match(normalized):
            return normalized
        fallback_id = slugify(normalized, default="bench").replace("-", "_")
        return fallback_id

    @staticmethod
    def _search_text(entry: dict[str, Any], *, raw_payload: dict[str, Any] | None = None) -> str:
        paper = entry.get("paper") if isinstance(entry.get("paper"), dict) else {}
        environment = entry.get("environment") if isinstance(entry.get("environment"), dict) else {}
        dataset_download = entry.get("dataset_download") if isinstance(entry.get("dataset_download"), dict) else {}
        credential_requirements = entry.get("credential_requirements") if isinstance(entry.get("credential_requirements"), dict) else {}
        parts = [
            entry.get("id"),
            entry.get("name"),
            entry.get("one_line"),
            entry.get("task_description"),
            entry.get("aisb_direction"),
            entry.get("task_mode"),
            entry.get("difficulty"),
            entry.get("time_band"),
            entry.get("cost_band"),
            entry.get("data_access"),
            entry.get("integrity_level"),
            entry.get("snapshot_status"),
            entry.get("support_level"),
            entry.get("recommended_when"),
            entry.get("not_recommended_when"),
            paper.get("title"),
            paper.get("venue"),
            paper.get("url"),
            environment.get("python"),
            environment.get("cuda"),
            environment.get("pytorch"),
            environment.get("flash_attn"),
            dataset_download.get("primary_method"),
            credential_requirements.get("mode"),
        ]
        parts.extend(entry.get("capability_tags") or [])
        parts.extend(entry.get("track_fit") or [])
        parts.extend(entry.get("primary_outputs") or [])
        for profile in entry.get("launch_profiles") or []:
            if isinstance(profile, dict):
                parts.extend([profile.get("id"), profile.get("label"), profile.get("description")])
        parts.extend(entry.get("risk_flags") or [])
        parts.extend(entry.get("risk_notes") or [])
        parts.extend(environment.get("key_packages") or [])
        parts.extend(environment.get("notes") or [])
        parts.extend(dataset_download.get("notes") or [])
        parts.extend(credential_requirements.get("items") or [])
        parts.extend(credential_requirements.get("notes") or [])
        for source in dataset_download.get("sources") or []:
            if not isinstance(source, dict):
                continue
            parts.extend([source.get("kind"), source.get("url"), source.get("access"), source.get("note")])
        if isinstance(raw_payload, dict):
            parts.extend(_collect_search_values(raw_payload))
        return " ".join(str(item).strip().lower() for item in parts if str(item or "").strip())

    @staticmethod
    def _has_risk_markers(entry: dict[str, Any]) -> bool:
        risk_flags = entry.get("risk_flags") if isinstance(entry.get("risk_flags"), list) else []
        risk_notes = entry.get("risk_notes") if isinstance(entry.get("risk_notes"), list) else []
        return bool(risk_flags or risk_notes)

    def _resolve_entry_asset_path(self, catalog_path: Path, asset_path: str) -> Path | None:
        candidate = Path(asset_path)
        resolved = candidate.resolve() if candidate.is_absolute() else (catalog_path.parent / candidate).resolve()
        try:
            resolved.relative_to(self.workspace_root.resolve())
        except ValueError:
            return None
        return resolved

    @staticmethod
    def _entry_sort_key(entry: dict[str, Any]) -> tuple[int, int, float, float, str]:
        compatibility = entry.get("compatibility") if isinstance(entry.get("compatibility"), dict) else {}
        recommendation = entry.get("recommendation") if isinstance(entry.get("recommendation"), dict) else {}
        recommended_ok = 1 if compatibility.get("recommended_ok") else 0
        minimum_ok = 1 if compatibility.get("minimum_ok") else 0
        has_risk_markers = 1 if (entry.get("risk_flags") or entry.get("risk_notes")) else 0
        score = float(recommendation.get("score") or compatibility.get("score") or 0.0)
        affinity = float(recommendation.get("affinity_score") or 0.0)
        name = str(entry.get("name") or "").lower()
        return (has_risk_markers, -recommended_ok, -minimum_ok, -score, -affinity, name)

    @staticmethod
    def _device_profile(hardware_payload: dict[str, Any] | None) -> dict[str, Any]:
        system = hardware_payload.get("system") if isinstance(hardware_payload, dict) and isinstance(hardware_payload.get("system"), dict) else {}
        preferences = hardware_payload.get("preferences") if isinstance(hardware_payload, dict) and isinstance(hardware_payload.get("preferences"), dict) else {}
        cpu = system.get("cpu") if isinstance(system.get("cpu"), dict) else {}
        memory = system.get("memory") if isinstance(system.get("memory"), dict) else {}
        disks = system.get("disks") if isinstance(system.get("disks"), list) else []
        gpus = [item for item in (system.get("gpus") or []) if isinstance(item, dict)] if isinstance(system, dict) else []
        effective_gpu_ids = [str(item).strip() for item in (preferences.get("effective_gpu_ids") or []) if str(item).strip()]
        selection_mode = str(preferences.get("gpu_selection_mode") or "all").strip().lower() if isinstance(preferences, dict) else "all"
        if selection_mode == "selected":
            effective_gpus = [gpu for gpu in gpus if str(gpu.get("gpu_id") or "").strip() in set(effective_gpu_ids)]
        else:
            effective_gpus = gpus
        disk_free_gb = None
        if disks:
            first_disk = disks[0] if isinstance(disks[0], dict) else {}
            raw_disk = _optional_number(first_disk.get("free_gb"))
            disk_free_gb = raw_disk
        gpu_vram_gb = None
        if effective_gpus:
            gpu_vram_values = [_optional_number(item.get("memory_total_gb")) for item in effective_gpus]
            gpu_vram_values = [item for item in gpu_vram_values if item is not None]
            gpu_vram_gb = max(gpu_vram_values) if gpu_vram_values else None
        return {
            "cpu_cores": _optional_number(cpu.get("logical_cores")),
            "ram_gb": _optional_number(memory.get("total_gb")),
            "disk_gb": disk_free_gb,
            "gpu_count": float(len(effective_gpus)),
            "gpu_vram_gb": gpu_vram_gb,
        }

    @staticmethod
    def _device_capacity_profile(device_profile: dict[str, Any]) -> dict[str, Any]:
        cpu = float(device_profile.get("cpu_cores") or 0.0)
        ram = float(device_profile.get("ram_gb") or 0.0)
        disk = float(device_profile.get("disk_gb") or 0.0)
        gpu_count = float(device_profile.get("gpu_count") or 0.0)
        gpu_vram = float(device_profile.get("gpu_vram_gb") or 0.0)
        score = (
            min(cpu / 16.0, 1.6) * 0.20
            + min(ram / 32.0, 1.8) * 0.24
            + min(disk / 120.0, 1.5) * 0.10
            + min(gpu_count / 1.0, 2.0) * 0.18
            + min(gpu_vram / 16.0, 2.0) * 0.28
        )
        if gpu_count <= 0 and gpu_vram <= 0:
            capacity_class = "low"
        elif score < 0.90:
            capacity_class = "low"
        elif score < 1.45:
            capacity_class = "medium"
        else:
            capacity_class = "high"
        return {
            "score": round(score * 100.0, 2),
            "capacity_class": capacity_class,
        }

    def _compatibility(self, *, entry: dict[str, Any], device_profile: dict[str, Any], device_summary: str) -> dict[str, Any]:
        resources = entry.get("resources") if isinstance(entry.get("resources"), dict) else {}
        minimum = resources.get("minimum") if isinstance(resources.get("minimum"), dict) else {}
        recommended = resources.get("recommended") if isinstance(resources.get("recommended"), dict) else {}
        minimum_eval = self._evaluate_requirement(minimum, device_profile)
        recommended_eval = self._evaluate_requirement(recommended, device_profile)
        score = round((recommended_eval["coverage"] * 70.0) + (minimum_eval["coverage"] * 30.0), 2)
        if recommended_eval["ok"]:
            recommendation_tier = "recommended"
        elif minimum_eval["ok"]:
            recommendation_tier = "minimum"
        else:
            recommendation_tier = "unsupported"
        return {
            "minimum_ok": minimum_eval["ok"],
            "recommended_ok": recommended_eval["ok"],
            "minimum_reasons": minimum_eval["reasons"],
            "recommended_reasons": recommended_eval["reasons"],
            "score": score,
            "recommendation_tier": recommendation_tier,
            "device_summary": device_summary,
            "resource_confidence": _resource_confidence(resources),
        }

    def _recommendation_profile(
        self,
        *,
        entry: dict[str, Any],
        device_profile: dict[str, Any],
        device_capacity: dict[str, Any],
        compatibility: dict[str, Any],
    ) -> dict[str, Any]:
        capacity_class = str(device_capacity.get("capacity_class") or "medium")
        score = float(compatibility.get("score") or 0.0)
        reasons: list[str] = []
        affinity = 0.0

        if compatibility.get("recommended_ok"):
            score += 32.0
            reasons.append("Meets the recommended hardware target.")
        elif compatibility.get("minimum_ok"):
            score += 14.0
            reasons.append("Meets the minimum hardware target.")
        else:
            score -= 35.0
            reasons.append("Current device is below the benchmark minimum target.")

        install_status = str((entry.get("install_state") or {}).get("status") or "").strip().lower()
        has_risk_markers = self._has_risk_markers(entry)
        if install_status == "installed":
            score += 12.0
            affinity += 12.0
            reasons.append("Already installed locally.")

        cost_rank = _COST_BAND_RANK.get(str(entry.get("cost_band") or "").strip().lower())
        difficulty_rank = _DIFFICULTY_RANK.get(str(entry.get("difficulty") or "").strip().lower())
        time_upper_hours = _time_band_upper_hours(str(entry.get("time_band") or "").strip())
        requires_execution = bool(entry.get("requires_execution")) if entry.get("requires_execution") is not None else False
        requires_paper = bool(entry.get("requires_paper")) if entry.get("requires_paper") is not None else False

        if capacity_class == "low":
            if cost_rank is not None:
                delta = {0: 10.0, 1: 8.0, 2: 2.0, 3: -6.0, 4: -10.0}.get(cost_rank, 0.0)
                score += delta
                affinity += delta
            if difficulty_rank is not None:
                delta = {0: 10.0, 1: 4.0, 2: -5.0, 3: -9.0}.get(difficulty_rank, 0.0)
                score += delta
                affinity += delta
            if time_upper_hours is not None:
                delta = 8.0 if time_upper_hours <= 2.0 else 3.0 if time_upper_hours <= 6.0 else -5.0
                score += delta
                affinity += delta
            if not requires_execution:
                score += 4.0
                affinity += 4.0
            if requires_paper:
                score -= 2.0
                affinity -= 2.0
        elif capacity_class == "medium":
            if cost_rank is not None:
                delta = {0: 4.0, 1: 5.0, 2: 3.0, 3: -2.0, 4: -6.0}.get(cost_rank, 0.0)
                score += delta
                affinity += delta
            if difficulty_rank is not None:
                delta = {0: 3.0, 1: 5.0, 2: 1.0, 3: -4.0}.get(difficulty_rank, 0.0)
                score += delta
                affinity += delta
            if time_upper_hours is not None:
                delta = 5.0 if time_upper_hours <= 4.0 else 2.0 if time_upper_hours <= 12.0 else -3.0
                score += delta
                affinity += delta
        else:
            if cost_rank is not None:
                delta = {0: 1.0, 1: 2.0, 2: 4.0, 3: 5.0, 4: 2.0}.get(cost_rank, 0.0)
                score += delta
                affinity += delta
            if difficulty_rank is not None:
                delta = {0: 1.0, 1: 3.0, 2: 5.0, 3: 5.0}.get(difficulty_rank, 0.0)
                score += delta
                affinity += delta
            if time_upper_hours is not None:
                delta = 1.0 if time_upper_hours <= 2.0 else 3.0 if time_upper_hours <= 12.0 else 5.0
                score += delta
                affinity += delta
            if requires_execution:
                score += 2.0
                affinity += 2.0

        snapshot_status = str(entry.get("snapshot_status") or "").strip().lower()
        support_level = str(entry.get("support_level") or "").strip().lower()
        snapshot_delta = {
            "runnable": 10.0,
            "runnable_not_verified": 5.0,
            "partial": -6.0,
            "restore_needed": -18.0,
            "external_eval_required": -12.0,
            "data_only": -20.0,
        }.get(snapshot_status, 0.0)
        support_delta = {
            "turnkey": 8.0,
            "advanced": 3.0,
            "recovery": -12.0,
        }.get(support_level, 0.0)
        score += snapshot_delta + support_delta
        affinity += max(snapshot_delta, 0.0) + max(support_delta, 0.0)
        if snapshot_status == "runnable":
            reasons.append("Current snapshot is marked runnable.")
        elif snapshot_status == "partial":
            reasons.append("Current snapshot is only partially runnable.")
        elif snapshot_status == "restore_needed":
            reasons.append("Current snapshot still needs restoration before dependable execution.")
        elif snapshot_status == "external_eval_required":
            reasons.append("Current snapshot still depends on an external evaluation route.")
        elif snapshot_status == "data_only":
            reasons.append("Current snapshot is data-only and not directly executable yet.")
        if support_level == "turnkey":
            reasons.append("This benchmark is packaged as a turnkey route.")
        elif support_level == "recovery":
            reasons.append("This benchmark is still in recovery mode rather than ready-to-run mode.")

        confidence = str(compatibility.get("resource_confidence") or "none").strip().lower() or "none"
        if confidence == "full":
            score += 6.0
        elif confidence == "partial":
            score += 3.0
        else:
            score -= 2.0
            reasons.append("Structured hardware requirements are incomplete, so recommendation confidence is lower.")

        if capacity_class == "low" and compatibility.get("recommended_ok"):
            reasons.append("This benchmark is one of the stronger fits for a modest local machine.")
        elif compatibility.get("recommended_ok"):
            reasons.append("This benchmark is a strong match for the current machine.")
        elif compatibility.get("minimum_ok"):
            reasons.append("This benchmark should run, but the safer choice may be a lighter option.")

        shelf_bucket = "needs_stronger_device"
        if has_risk_markers:
            score -= 40.0
            affinity -= 20.0
            reasons.append("Risk-marked benchmarks are excluded from BenchStore recommendations.")
            shelf_bucket = "risk_flagged"
        elif install_status == "installed" and compatibility.get("minimum_ok"):
            shelf_bucket = "installed"
        elif compatibility.get("recommended_ok"):
            shelf_bucket = "best_match"
        elif compatibility.get("minimum_ok"):
            shelf_bucket = "runnable"

        return {
            "score": round(max(0.0, min(140.0, score)), 2),
            "affinity_score": round(affinity, 2),
            "capacity_class": capacity_class,
            "shelf_bucket": shelf_bucket,
            "reasons": reasons[:5],
            "cost_rank": cost_rank,
            "difficulty_rank": difficulty_rank,
            "time_upper_hours": time_upper_hours,
        }

    @staticmethod
    def _filter_options(items: list[dict[str, Any]]) -> dict[str, list[str]]:
        def collect(key: str) -> list[str]:
            values = sorted(
                {
                    str(item.get(key) or "").strip()
                    for item in items
                    if str(item.get(key) or "").strip()
                }
            )
            return values

        track_fit_values = sorted(
            {
                str(value).strip()
                for item in items
                for value in (item.get("track_fit") or [])
                if str(value).strip()
            }
        )
        return {
            "aisb_direction": collect("aisb_direction"),
            "task_mode": collect("task_mode"),
            "cost_band": collect("cost_band"),
            "difficulty": collect("difficulty"),
            "data_access": collect("data_access"),
            "track_fit": track_fit_values,
            "requires_execution": sorted(
                {
                    "true" if bool(item.get("requires_execution")) else "false"
                    for item in items
                    if item.get("requires_execution") is not None
                }
            ),
            "requires_paper": sorted(
                {
                    "true" if bool(item.get("requires_paper")) else "false"
                    for item in items
                    if item.get("requires_paper") is not None
                }
            ),
        }

    @staticmethod
    def _shelves(items: list[dict[str, Any]]) -> dict[str, list[str]]:
        def ids_for(bucket: str, *, limit: int = 8) -> list[str]:
            return [str(item.get("id") or "") for item in items if str(((item.get("recommendation") or {}).get("shelf_bucket") or "")).strip() == bucket][:limit]

        return {
            "best_match_ids": ids_for("best_match"),
            "runnable_ids": ids_for("runnable"),
            "installed_ids": ids_for("installed"),
            "needs_stronger_device_ids": ids_for("needs_stronger_device"),
        }

    @staticmethod
    def _evaluate_requirement(requirement: dict[str, Any], device_profile: dict[str, Any]) -> dict[str, Any]:
        if not requirement:
            return {
                "ok": True,
                "coverage": 1.0,
                "reasons": ["No structured requirement was provided."],
            }
        reasons: list[str] = []
        considered = 0
        passed = 0
        for field_name, label in _RESOURCE_FIELDS:
            required = _optional_number(requirement.get(field_name))
            if required is None:
                continue
            considered += 1
            available = _optional_number(device_profile.get(field_name))
            if available is None:
                reasons.append(f"{label}: unavailable on this machine summary, need {required:g}.")
                continue
            if available >= required:
                passed += 1
                reasons.append(f"{label}: {available:g} available, need {required:g}.")
                continue
            reasons.append(f"{label}: {available:g} available, need {required:g}.")
        if considered == 0:
            return {
                "ok": True,
                "coverage": 1.0,
                "reasons": ["No structured requirement was provided."],
            }
        return {
            "ok": passed == considered,
            "coverage": passed / considered,
            "reasons": reasons,
        }
