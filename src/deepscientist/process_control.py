from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any


def process_session_popen_kwargs(
    *,
    hide_window: bool = False,
    new_process_group: bool = True,
) -> dict[str, Any]:
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        creationflags = 0
        if new_process_group and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
        if hide_window and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW")
        payload: dict[str, Any] = {}
        if creationflags:
            payload["creationflags"] = creationflags
        if hide_window and hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW")
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            payload["startupinfo"] = startupinfo
        return payload
    if new_process_group:
        return {
            "start_new_session": True,
        }
    return {}


def is_process_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name != "nt":
        proc_stat_path = Path("/proc") / str(pid) / "stat"
        if proc_stat_path.exists():
            try:
                parts = proc_stat_path.read_text(encoding="utf-8").split()
            except OSError:
                parts = []
            if len(parts) >= 3 and parts[2] == "Z":
                return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def terminate_process_ids(
    *,
    process_pid: int | None,
    process_group_id: int | None,
    force: bool = False,
) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        if isinstance(process_pid, int) and process_pid > 0:
            taskkill_args = ["taskkill", "/PID", str(process_pid), "/T"]
            if force:
                taskkill_args.append("/F")
            subprocess.run(
                taskkill_args,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if not force and is_process_alive(process_pid):
                try:
                    os.kill(process_pid, signal.SIGTERM)
                except OSError:
                    pass
        return
    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return
        return
    if isinstance(process_pid, int) and process_pid > 0:
        try:
            os.kill(process_pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return


def terminate_subprocess(
    process: subprocess.Popen[Any],
    *,
    process_group_id: int | None = None,
    force: bool = False,
    prefer_ctrl_break: bool = False,
    grace_seconds: float = 5.0,
) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":  # pragma: no cover - exercised on Windows
        if not force and prefer_ctrl_break and hasattr(signal, "CTRL_BREAK_EVENT"):
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            except (AttributeError, OSError, ValueError):
                try:
                    process.terminate()
                except OSError:
                    return
        elif not force:
            try:
                process.terminate()
            except OSError:
                return
        else:
            try:
                process.kill()
            except OSError:
                return
        if force:
            return
        deadline = time.monotonic() + max(grace_seconds, 0.1)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.05)
        try:
            process.kill()
        except OSError:
            return
        return

    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        try:
            process.kill() if force else process.terminate()
        except OSError:
            return
    if force:
        return
    deadline = time.monotonic() + max(grace_seconds, 0.1)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.05)
    if isinstance(process_group_id, int) and process_group_id > 0:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            return
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            return
