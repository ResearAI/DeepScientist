from __future__ import annotations

import codecs
import json
import os
import pty
import select
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .service import (
    BASH_CARRIAGE_RETURN_PREFIX,
    BASH_PROGRESS_PREFIX,
    BASH_TERMINAL_PROMPT_PREFIX,
    BASH_STATUS_MARKER_PREFIX,
    _atomic_write_json,
    _coerce_session_status,
    _parse_progress_marker,
)
from ..shared import append_jsonl, ensure_dir, read_json, read_jsonl, utc_now

DEFAULT_STOP_GRACE_SECONDS = 5
TERMINAL_IO_POLL_SECONDS = 0.02


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_meta(session_dir: Path) -> dict[str, Any]:
    return read_json(session_dir / "meta.json", {})


def _summary_path(session_dir: Path) -> Path:
    return session_dir.parent / "summary.json"


def _summary_session_payload(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "bash_id": meta.get("bash_id") or meta.get("id"),
        "command": meta.get("command"),
        "kind": meta.get("kind") or "exec",
        "label": meta.get("label"),
        "workdir": meta.get("workdir"),
        "status": _coerce_session_status(meta.get("status")),
        "exit_code": meta.get("exit_code"),
        "stop_reason": meta.get("stop_reason"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "updated_at": meta.get("updated_at"),
        "last_progress": meta.get("last_progress"),
    }


def _summary_sort_key(session: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(session.get("updated_at") or ""),
        str(session.get("started_at") or ""),
        str(session.get("bash_id") or ""),
    )


def _is_active_status(value: object) -> bool:
    return _coerce_session_status(value) in {"running", "terminating"}


def _default_summary() -> dict[str, Any]:
    return {
        "session_count": 0,
        "running_count": 0,
        "latest_session": None,
        "updated_at": utc_now(),
    }


def _load_summary(session_dir: Path) -> dict[str, Any] | None:
    summary = read_json(_summary_path(session_dir), None)
    if not isinstance(summary, dict):
        return None
    return {**_default_summary(), **summary}


def _write_summary(session_dir: Path, summary: dict[str, Any]) -> None:
    _atomic_write_json(
        _summary_path(session_dir),
        {
            **_default_summary(),
            **summary,
            "updated_at": utc_now(),
        },
    )


def _rebuild_summary(session_dir: Path) -> dict[str, Any]:
    summary = _default_summary()
    latest_session: dict[str, Any] | None = None
    session_count = 0
    running_count = 0
    for meta_path in session_dir.parent.glob("*/meta.json"):
        meta = read_json(meta_path, {})
        if not isinstance(meta, dict) or not meta:
            continue
        session_count += 1
        if _is_active_status(meta.get("status")):
            running_count += 1
        compact = _summary_session_payload(meta)
        if latest_session is None or _summary_sort_key(compact) >= _summary_sort_key(latest_session):
            latest_session = compact
    summary["session_count"] = session_count
    summary["running_count"] = running_count
    summary["latest_session"] = latest_session
    _write_summary(session_dir, summary)
    return summary


def _summary_payload_changed(previous: dict[str, Any], payload: dict[str, Any]) -> bool:
    previous_compact = _summary_session_payload(previous)
    payload_compact = _summary_session_payload(payload)
    previous_compact.pop("updated_at", None)
    payload_compact.pop("updated_at", None)
    return previous_compact != payload_compact


def _refresh_summary(session_dir: Path, previous: dict[str, Any], payload: dict[str, Any]) -> None:
    summary = _load_summary(session_dir)
    if summary is None:
        summary = _rebuild_summary(session_dir)

    old_exists = isinstance(previous, dict) and bool(previous)
    if old_exists and not _summary_payload_changed(previous, payload):
        return

    old_running = _is_active_status(previous.get("status")) if old_exists else False
    new_running = _is_active_status(payload.get("status"))
    if not old_exists:
        summary["session_count"] = int(summary.get("session_count") or 0) + 1
    if old_running != new_running:
        running_count = int(summary.get("running_count") or 0)
        running_count += 1 if new_running else -1
        summary["running_count"] = max(0, running_count)

    compact = _summary_session_payload(payload)
    latest_session = summary.get("latest_session")
    if (
        not isinstance(latest_session, dict)
        or str(latest_session.get("bash_id") or "") == str(compact.get("bash_id") or "")
        or _summary_sort_key(compact) >= _summary_sort_key(latest_session)
    ):
        summary["latest_session"] = compact
    _write_summary(session_dir, summary)


def _write_meta(session_dir: Path, payload: dict[str, Any]) -> None:
    previous = _read_meta(session_dir)
    _atomic_write_json(session_dir / "meta.json", payload)
    _refresh_summary(session_dir, previous, payload)


def _safe_reason(reason: str | None) -> str:
    if not reason:
        return "none"
    return reason.replace('"', '\\"').replace("\n", "\\n")


def _status_marker(meta: dict[str, Any], *, status: str, exit_code: int | None, reason: str | None) -> str:
    return (
        f"{BASH_STATUS_MARKER_PREFIX} status={status} bash_id={meta.get('bash_id')} ts={utc_now()} "
        f"user_id={meta.get('started_by_user_id') or 'agent'} session_id={meta.get('session_id') or 'none'} "
        f"agent_id={meta.get('agent_id') or 'none'} agent_instance_id={meta.get('agent_instance_id') or 'none'} "
        f"exit_code={exit_code if exit_code is not None else 'none'} reason=\"{_safe_reason(reason)}\""
    )


def _terminate_process(process: subprocess.Popen[bytes], process_group_id: int | None) -> None:
    if process.poll() is not None:
        return
    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        process.terminate()
    deadline = time.monotonic() + DEFAULT_STOP_GRACE_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)
    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            return
    elif process.poll() is None:
        process.kill()


def _terminate_process_force(process: subprocess.Popen[bytes], process_group_id: int | None) -> None:
    if process.poll() is not None:
        return
    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        process.kill()


def _drain_buffer(
    buffer: str,
    append_line,
    *,
    flush_partial: bool = False,
    carriage_mode: str = "marker",
) -> str:
    while True:
        index_r = buffer.find("\r")
        index_n = buffer.find("\n")
        if index_r == -1 and index_n == -1:
            break
        if index_r != -1 and (index_n == -1 or index_r < index_n):
            segment = buffer[:index_r]
            if index_r + 1 < len(buffer) and buffer[index_r + 1] == "\n":
                buffer = buffer[index_r + 2 :]
                append_line(segment)
            else:
                buffer = buffer[index_r + 1 :]
                if carriage_mode == "stream":
                    append_line(segment, stream="carriage")
                else:
                    append_line(f"{BASH_CARRIAGE_RETURN_PREFIX}{segment}")
            continue
        segment = buffer[:index_n]
        buffer = buffer[index_n + 1 :]
        append_line(segment)
    if flush_partial and buffer:
        append_line(buffer, stream="partial")
        return ""
    return buffer


def _parse_terminal_prompt_marker(line: str) -> dict[str, str] | None:
    if not line.startswith(BASH_TERMINAL_PROMPT_PREFIX):
        return None
    raw = line[len(BASH_TERMINAL_PROMPT_PREFIX) :].strip()
    if not raw:
        return None
    payload: dict[str, str] = {}
    try:
        for token in shlex.split(raw):
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            payload[key.strip()] = value
    except ValueError:
        return None
    return payload or None


def _format_terminal_prompt(meta: dict[str, Any], cwd_value: str) -> str:
    quest_root = Path(str(meta.get("quest_root") or ".")).expanduser().resolve()
    cwd_path = Path(str(cwd_value or quest_root)).expanduser().resolve()
    home = Path.home().expanduser().resolve()
    try:
        relative = cwd_path.relative_to(home).as_posix()
        display = "~" if relative == "." else f"~/{relative}"
    except ValueError:
        display = str(cwd_path)
    return f"{display}$ "


def run_monitor(session_dir: Path) -> int:
    meta = _read_meta(session_dir)
    if not meta:
        raise SystemExit("missing_meta")

    command = str(meta.get("command") or "").strip()
    cwd = Path(str(meta.get("cwd") or meta.get("quest_root") or ".")).expanduser().resolve()
    timeout_seconds = meta.get("timeout_seconds")
    session_kind = str(meta.get("kind") or "exec").strip().lower()
    stop_reason: str | None = None
    seq = int(meta.get("latest_seq") or 0)
    progress_path = session_dir / "progress.json"
    stop_request_path = session_dir / "stop_request.json"
    input_path = session_dir / "input.jsonl"
    input_cursor_path = session_dir / "input.cursor.json"
    terminal_log_path = session_dir / "terminal.log"
    log_path = session_dir / "log.jsonl"
    terminal_log_path.touch(exist_ok=True)
    log_path.touch(exist_ok=True)
    input_path.touch(exist_ok=True)
    if not input_cursor_path.exists():
        _atomic_write_json(input_cursor_path, {"offset": len(read_jsonl(input_path)), "updated_at": utc_now()})

    tool_env = os.environ.pop("DS_BASH_EXEC_TOOL_ENV", "")
    env_payload = os.environ.copy()
    env_payload.setdefault("PYTHONUNBUFFERED", "1")
    env_payload.setdefault("TERM", "xterm-256color")
    env_payload.setdefault("COLORTERM", "truecolor")
    if tool_env:
        try:
            extra_env = json.loads(tool_env)
        except json.JSONDecodeError:
            extra_env = {}
        if isinstance(extra_env, dict):
            for key, value in extra_env.items():
                if not isinstance(key, str) or value is None:
                    continue
                env_payload[key] = str(value)

    ensure_dir(session_dir)
    ensure_dir(log_path.parent)

    def update_meta(**changes: Any) -> dict[str, Any]:
        nonlocal meta
        meta = {**meta, **changes, "updated_at": utc_now()}
        _write_meta(session_dir, meta)
        return meta

    def append_line(line: str, *, stream: str = "stdout") -> None:
        nonlocal seq
        prompt_marker = _parse_terminal_prompt_marker(line) if session_kind == "terminal" else None
        if prompt_marker is not None:
            prompt_ts = str(prompt_marker.get("ts") or utc_now())
            prompt_cwd = str(prompt_marker.get("cwd") or meta.get("cwd") or cwd)
            update_meta(cwd=prompt_cwd, last_prompt_at=prompt_ts)
            seq += 1
            _append_jsonl(
                log_path,
                {
                    "seq": seq,
                    "stream": "prompt",
                    "line": _format_terminal_prompt(meta, prompt_cwd),
                    "timestamp": prompt_ts,
                },
            )
            return
        seq += 1
        timestamp = utc_now()
        with terminal_log_path.open("a", encoding="utf-8") as handle:
            if stream == "partial":
                handle.write(line)
            elif stream == "carriage":
                handle.write(f"\r{line}")
            else:
                handle.write(f"{line}\n")
        _append_jsonl(
            log_path,
            {
                "seq": seq,
                "stream": stream,
                "line": line,
                "timestamp": timestamp,
            },
        )
        progress = _parse_progress_marker(line)
        output_updates: dict[str, Any] = {}
        if stream not in {"system", "prompt"}:
            output_updates = {"last_output_at": timestamp, "last_output_seq": seq}
        if progress is not None:
            progress.setdefault("ts", timestamp)
            _atomic_write_json(progress_path, progress)
            update_meta(last_progress=progress, latest_seq=seq, **output_updates)
        else:
            update_meta(latest_seq=seq, **output_updates)

    master_fd: int | None = None
    slave_fd: int | None = None
    output_fd: int | None = None
    process: subprocess.Popen[bytes] | None = None
    try:
        using_pty = True
        try:
            master_fd, slave_fd = pty.openpty()
            process = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=str(cwd),
                env=env_payload,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
            )
            os.close(slave_fd)
            slave_fd = None
            output_fd = master_fd
        except OSError:
            using_pty = False
            process = subprocess.Popen(
                ["bash", "-lc", command],
                cwd=str(cwd),
                env=env_payload,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            if process.stdout is None:
                raise RuntimeError("bash_exec_missing_stdout_pipe")
            output_fd = process.stdout.fileno()
        process_group_id = os.getpgid(process.pid)
        update_meta(
            monitor_pid=os.getpid(),
            process_pid=process.pid,
            process_group_id=process_group_id,
            status="running",
            transport="pty" if using_pty else "pipe",
        )
        append_line(_status_marker(meta, status="running", exit_code=None, reason="none"), stream="system")

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buffer = ""
        deadline = time.monotonic() + int(timeout_seconds) if isinstance(timeout_seconds, int) and timeout_seconds > 0 else None
        stop_requested = False

        while True:
            if not stop_requested and stop_request_path.exists():
                request = read_json(stop_request_path, {}) or {}
                stop_reason = str(request.get("reason") or "user_stop").strip() or "user_stop"
                force_stop = bool(request.get("force"))
                update_meta(
                    status="terminating",
                    stop_reason=stop_reason,
                    stopped_by_user_id=str(request.get("user_id") or meta.get("stopped_by_user_id") or meta.get("agent_id") or "agent"),
                )
                append_line(
                    f"{'Force t' if force_stop else 'T'}ermination requested: {stop_reason}",
                    stream="system",
                )
                if force_stop:
                    _terminate_process_force(process, process_group_id)
                else:
                    _terminate_process(process, process_group_id)
                stop_requested = True

            if deadline is not None and time.monotonic() >= deadline and process.poll() is None and not stop_requested:
                stop_reason = "timeout"
                update_meta(status="terminating", stop_reason=stop_reason)
                append_line("Process timed out and is being terminated.", stream="system")
                _terminate_process(process, process_group_id)
                stop_requested = True

            if session_kind == "terminal" and output_fd is not None and process.poll() is None:
                cursor_payload = read_json(input_cursor_path, {}) or {}
                offset = int(cursor_payload.get("offset") or 0)
                input_entries = read_jsonl(input_path)
                if offset < len(input_entries):
                    for entry in input_entries[offset:]:
                        raw_data = str(entry.get("data") or "")
                        if raw_data:
                            try:
                                os.write(output_fd, raw_data.encode("utf-8"))
                            except OSError:
                                break
                        offset += 1
                    _atomic_write_json(
                        input_cursor_path,
                        {
                            "offset": offset,
                            "updated_at": utc_now(),
                        },
                    )

            ready, _unused_w, _unused_x = select.select([output_fd], [], [], TERMINAL_IO_POLL_SECONDS)
            if ready:
                try:
                    chunk = os.read(output_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    buffer += decoder.decode(chunk)
                    buffer = _drain_buffer(
                        buffer,
                        append_line,
                        flush_partial=session_kind == "terminal",
                        carriage_mode="stream" if session_kind == "terminal" else "marker",
                    )
            if process.poll() is not None:
                break

        while True:
            try:
                chunk = os.read(output_fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buffer += decoder.decode(chunk)
            buffer = _drain_buffer(
                buffer,
                append_line,
                flush_partial=session_kind == "terminal",
                carriage_mode="stream" if session_kind == "terminal" else "marker",
            )
        buffer += decoder.decode(b"", final=True)
        if buffer:
            append_line(buffer, stream="partial" if session_kind == "terminal" else "stdout")

        if not stop_requested and not stop_reason and stop_request_path.exists():
            request = read_json(stop_request_path, {}) or {}
            stop_reason = str(request.get("reason") or "user_stop").strip() or "user_stop"
            stop_requested = True
            update_meta(
                status="terminating",
                stop_reason=stop_reason,
                stopped_by_user_id=str(request.get("user_id") or meta.get("stopped_by_user_id") or meta.get("agent_id") or "agent"),
            )

        exit_code = process.wait()
        if stop_requested or stop_reason:
            status = "terminated"
        else:
            status = "completed" if exit_code == 0 else "failed"
        append_line(_status_marker(meta, status=status, exit_code=exit_code, reason=stop_reason), stream="system")
        update_meta(
            status=status,
            exit_code=exit_code,
            finished_at=utc_now(),
            stop_reason=stop_reason,
        )
        return 0
    finally:
        if slave_fd is not None:
            try:
                os.close(slave_fd)
            except OSError:
                pass
        if process is not None and process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if not args:
        raise SystemExit("session_dir_required")
    session_dir = Path(args[0]).expanduser().resolve()
    return run_monitor(session_dir)


if __name__ == "__main__":
    raise SystemExit(main())
