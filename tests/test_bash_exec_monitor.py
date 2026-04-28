from __future__ import annotations

from pathlib import Path

from deepscientist.bash_exec import BashExecService
from deepscientist.bash_exec.monitor import _drain_buffer, _render_terminal_log_line
from deepscientist.home import ensure_home_layout
from deepscientist.shared import read_json, write_json


def test_drain_buffer_flushes_oversized_unterminated_exec_lines() -> None:
    oversized = "x" * 200_000
    emitted: list[tuple[str, str]] = []

    def append_line(line: str, *, stream: str = "stdout") -> None:
        emitted.append((stream, line))

    remainder = _drain_buffer(oversized, append_line, flush_partial=False)

    partial_chunks = [line for stream, line in emitted if stream == "partial"]
    assert partial_chunks
    assert "".join(partial_chunks) + remainder == oversized
    assert max(len(chunk) for chunk in partial_chunks) <= 128_000
    assert len(remainder) <= 128_000


def test_render_terminal_log_line_truncates_huge_single_line_output() -> None:
    line = "prefix:" + ("x" * 100_000) + ":suffix"

    rendered = _render_terminal_log_line(line)

    assert rendered.startswith("prefix:")
    assert rendered.endswith(":suffix")
    assert "full content remains in log.jsonl" in rendered
    assert len(rendered) < len(line)


def test_reconcile_session_sets_finished_at_when_existing_value_is_empty(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    quest_root = temp_home / "quests" / "q-bash"
    service = BashExecService(temp_home)
    session_dir = service.session_dir(quest_root, "bash-stale")
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        service.meta_path(quest_root, "bash-stale"),
        {
            "bash_id": "bash-stale",
            "quest_id": "q-bash",
            "status": "running",
            "kind": "exec",
            "command": "printf stale",
            "started_at": "2026-04-10T00:00:00+00:00",
            "finished_at": None,
            "process_pid": 999_999_991,
            "monitor_pid": 999_999_992,
        },
    )

    session = service.reconcile_session(quest_root, "bash-stale")

    assert session["status"] == "failed"
    assert session["finished_at"]
    assert read_json(service.meta_path(quest_root, "bash-stale"), {})["finished_at"]


def test_completed_session_compacts_huge_terminal_log_with_backup_reference(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    quest_root = temp_home / "quests" / "q-bash"
    service = BashExecService(temp_home)
    session_dir = service.session_dir(quest_root, "bash-huge-log")
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        service.meta_path(quest_root, "bash-huge-log"),
        {
            "bash_id": "bash-huge-log",
            "quest_id": "q-bash",
            "status": "completed",
            "kind": "exec",
            "command": "cat huge.log",
            "started_at": "2026-04-10T00:00:00+00:00",
            "finished_at": "2026-04-10T00:00:01+00:00",
        },
    )
    huge_line = "prefix:" + ("x" * 1_300_000) + ":suffix\n"
    service.terminal_log_path(quest_root, "bash-huge-log").write_text(huge_line, encoding="utf-8")

    session = service.reconcile_session(quest_root, "bash-huge-log")

    compaction = session["runtime_log_compaction"]["terminal_log"]
    compact_path = quest_root / compaction["compact_path"]
    backup_path = quest_root / compaction["backup_path"]
    assert compact_path == service.terminal_log_path(quest_root, "bash-huge-log")
    assert compact_path.exists()
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == huge_line
    compacted_text = compact_path.read_text(encoding="utf-8")
    assert "compacted completed runtime log" in compacted_text
    assert compact_path.stat().st_size < 600_000
