from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from deepscientist.runtime_storage import dedupe_worktree_files, slim_quest_jsonl


def _jsonl_line(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def test_slim_quest_jsonl_rewrites_oversized_lines_and_keeps_backup(temp_home: Path) -> None:
    quest_root = temp_home / "quests" / "q-storage"
    events_path = quest_root / ".ds" / "events.jsonl"
    log_path = quest_root / ".ds" / "bash_exec" / "bash-001" / "log.jsonl"
    events_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    small_event = _jsonl_line({"event_id": "evt-small", "type": "runner.message", "text": "small"})
    large_event = _jsonl_line(
        {
            "event_id": "evt-large",
            "type": "runner.tool_result",
            "run_id": "run-001",
            "tool_name": "artifact.get_quest_state",
            "payload": "x" * 512,
        }
    )
    large_log = _jsonl_line(
        {
            "seq": 7,
            "stream": "stdout",
            "timestamp": "2026-04-01T00:00:00+00:00",
            "line": "y" * 512,
        }
    )
    events_path.write_bytes(small_event + large_event)
    log_path.write_bytes(large_log)

    manifest = slim_quest_jsonl(quest_root, threshold_bytes=200)

    assert manifest["compacted_line_count"] == 2
    assert manifest["compacted_bytes_total"] == len(large_event) + len(large_log)
    assert {item["path"] for item in manifest["files"]} == {
        ".ds/events.jsonl",
        ".ds/bash_exec/bash-001/log.jsonl",
    }
    manifest_path = Path(str(manifest["manifest_path"]))
    assert manifest_path.exists()
    rewritten_events = events_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(rewritten_events[0])["event_id"] == "evt-small"
    event_placeholder = json.loads(rewritten_events[1])
    assert event_placeholder["event_id"] == "evt-large"
    assert event_placeholder["type"] == "runner.tool_result"
    assert event_placeholder["oversized_event"] is True
    assert event_placeholder["backup_ref"].startswith(".ds/slim_backups/")
    log_placeholder = json.loads(log_path.read_text(encoding="utf-8"))
    assert log_placeholder["seq"] == 7
    assert log_placeholder["oversized_payload"] is True
    backup_path = quest_root / event_placeholder["backup_ref"]
    with gzip.open(backup_path, "rb") as handle:
        assert handle.read() == large_event


def test_slim_quest_jsonl_noops_when_no_lines_exceed_threshold(temp_home: Path) -> None:
    quest_root = temp_home / "quests" / "q-storage-noop"
    events_path = quest_root / ".ds" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    raw = _jsonl_line({"event_id": "evt-small", "type": "runner.message", "text": "small"})
    events_path.write_bytes(raw)

    manifest = slim_quest_jsonl(quest_root, threshold_bytes=1024)

    assert manifest["compacted_line_count"] == 0
    assert "manifest_path" not in manifest
    assert events_path.read_bytes() == raw


def test_dedupe_worktree_files_relinks_duplicate_large_cold_files(temp_home: Path) -> None:
    quest_root = temp_home / "quests" / "q-storage-dedupe"
    first = quest_root / ".ds" / "worktrees" / "branch-a" / ".codex" / "sessions" / "a.jsonl"
    second = quest_root / ".ds" / "worktrees" / "branch-b" / ".codex" / "sessions" / "b.jsonl"
    different = quest_root / ".ds" / "worktrees" / "branch-c" / "experiments" / "result.json"
    for path in (first, second, different):
        path.parent.mkdir(parents=True, exist_ok=True)
    duplicate_payload = b'{"payload":"' + (b"x" * 1024) + b'"}\n'
    first.write_bytes(duplicate_payload)
    second.write_bytes(duplicate_payload)
    different.write_bytes(b'{"payload":"' + (b"z" * 1024) + b'"}\n')

    manifest = dedupe_worktree_files(quest_root, min_bytes=128)

    assert manifest["groups_examined"] == 1
    assert manifest["files_relinked"] == 1
    assert manifest["bytes_deduped"] == len(duplicate_payload)
    assert manifest["groups"][0]["canonical"] == first.relative_to(quest_root).as_posix()
    assert manifest["groups"][0]["relinked"] == [second.relative_to(quest_root).as_posix()]
    assert os.stat(first).st_ino == os.stat(second).st_ino
    assert os.stat(first).st_ino != os.stat(different).st_ino
