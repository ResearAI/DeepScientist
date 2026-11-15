from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tracemalloc

from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl, write_json


def _snapshot_retention_sample() -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="ds-cache-regression-") as temporary:
        root = Path(temporary)
        os_home = root / "os-home"
        os_home.mkdir()
        os.environ["HOME"] = str(os_home)
        home = root / "DeepScientist"
        ensure_home_layout(home)
        ConfigManager(home).ensure_files()
        service = QuestService(home)
        created = service.create("historical artifact retention")
        quest_id = created["quest_id"]
        quest_root = Path(created["quest_root"])
        artifact = {
            "id": "progress-fixed-history",
            "kind": "progress",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "summary": "One logical record in multiple historical workspaces.",
            "details": {"notes": "x" * (256 * 1024)},
        }
        write_json(quest_root / "artifacts" / "progress" / "fixed.json", artifact)
        initial = service.snapshot(quest_id)
        assert initial["artifact_count"] == 1
        del initial, created
        gc.collect()

        tracemalloc.start()
        try:
            for index in range(32):
                workspace = quest_root / ".ds" / "worktrees" / f"history-{index:02}"
                write_json(workspace / "artifacts" / "progress" / "fixed.json", artifact)
            snapshot = service.snapshot(quest_id)
            artifact_count = snapshot["artifact_count"]
            selected_id = snapshot["recent_artifacts"][0]["payload"]["id"]
            assert selected_id == "progress-fixed-history"
            del snapshot
            gc.collect()
            retained_bytes, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return {
            "artifact_count": artifact_count,
            "historical_copies": 32,
            "retained_bytes": retained_bytes,
            "peak_bytes": peak_bytes,
        }


def test_snapshot_does_not_retain_every_historical_artifact_copy() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "PYTHONPATH": str(project_root / "src"),
        "DEEPSCIENTIST_REPO_ROOT": str(project_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).resolve())],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env=environment,
    )
    sample = json.loads(result.stdout)
    assert sample["artifact_count"] == 1
    # The public snapshot still represents one record, not 32 retained copies.
    # Allow projection and workspace metadata without tying the test to a cache layout.
    assert sample["retained_bytes"] < 2 * 1024 * 1024, sample


def _reader_fixture(home: Path) -> tuple[QuestService, Path]:
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    service = QuestService(home)
    quest = service.create("cached reader ownership")
    return service, Path(quest["quest_root"])


def test_history_returns_owned_nested_records(temp_home: Path) -> None:
    service, quest_root = _reader_fixture(temp_home)
    append_jsonl(quest_root / ".ds" / "conversations" / "main.jsonl", {
        "role": "user", "content": "original", "details": {"tags": ["original"]},
    })
    returned = service.history(quest_root.name)
    returned[-1]["content"] = "changed by caller"
    returned[-1]["details"]["tags"].append("changed by caller")

    reread = service.history(quest_root.name)
    assert reread[-1]["content"] == "original"
    assert reread[-1]["details"]["tags"] == ["original"]


def test_event_windows_return_owned_nested_records(temp_home: Path) -> None:
    service, quest_root = _reader_fixture(temp_home)
    append_jsonl(quest_root / ".ds" / "events.jsonl", {
        "event_id": "evt-owned", "type": "fixture", "details": {"tags": ["original"]},
    })
    returned = service.events(quest_root.name, tail=True, limit=1)
    returned["events"][0]["details"]["tags"].append("changed by caller")

    reread = service.events(quest_root.name, tail=True, limit=1)
    assert reread["events"][0]["event_id"] == "evt-owned"
    assert reread["events"][0]["details"]["tags"] == ["original"]


def test_tail_cache_entry_returns_owned_nested_records(temp_home: Path) -> None:
    service, quest_root = _reader_fixture(temp_home)
    events_path = quest_root / ".ds" / "events.jsonl"
    append_jsonl(events_path, {
        "event_id": "evt-owned", "type": "fixture", "details": {"tags": ["original"]},
    })
    service.events(quest_root.name, tail=True, limit=1)
    returned = service.jsonl_tail_cache_entry(events_path)
    assert returned is not None
    returned["records"][0][1]["details"]["tags"].append("changed by caller")

    reread = service.events(quest_root.name, tail=True, limit=1)
    assert reread["events"][0]["details"]["tags"] == ["original"]


if __name__ == "__main__":
    print(json.dumps(_snapshot_retention_sample(), sort_keys=True))
