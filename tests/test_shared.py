from __future__ import annotations

from pathlib import Path
import subprocess

from deepscientist import shared


def test_resolve_runner_binary_prefers_env_override_for_codex(monkeypatch, tmp_path: Path) -> None:
    system_codex = tmp_path / "system-codex"
    system_codex.write_text("", encoding="utf-8")
    override_codex = tmp_path / "override-codex"
    override_codex.write_text("", encoding="utf-8")

    def fake_resolve(reference: str) -> str | None:
        if reference == "codex":
            return str(system_codex)
        if reference == str(override_codex):
            return str(override_codex)
        return None

    monkeypatch.setattr(shared, "_resolve_executable_reference", fake_resolve)
    monkeypatch.setenv("DEEPSCIENTIST_CODEX_BINARY", str(override_codex))

    assert shared.resolve_runner_binary("codex", runner_name="codex") == str(override_codex)


def test_resolve_runner_binary_prefers_path_codex_over_bundled_fallback(monkeypatch, tmp_path: Path) -> None:
    system_codex = tmp_path / "system-codex"
    system_codex.write_text("", encoding="utf-8")
    bundled_root = tmp_path / "repo"
    bundled_binary = bundled_root / "node_modules" / ".bin" / "codex"
    bundled_binary.parent.mkdir(parents=True, exist_ok=True)
    bundled_binary.write_text("", encoding="utf-8")

    monkeypatch.delenv("DEEPSCIENTIST_CODEX_BINARY", raising=False)
    monkeypatch.delenv("DS_CODEX_BINARY", raising=False)
    monkeypatch.setattr(
        shared,
        "_resolve_executable_reference",
        lambda reference: str(system_codex) if reference == "codex" else None,
    )
    monkeypatch.setattr(shared, "_codex_repo_roots", lambda: [bundled_root])

    assert shared.resolve_runner_binary("codex", runner_name="codex") == str(system_codex)


def test_resolve_runner_binary_uses_bundled_codex_as_fallback(monkeypatch, tmp_path: Path) -> None:
    bundled_root = tmp_path / "repo"
    bundled_binary = bundled_root / "node_modules" / ".bin" / "codex"
    bundled_binary.parent.mkdir(parents=True, exist_ok=True)
    bundled_binary.write_text("", encoding="utf-8")

    monkeypatch.delenv("DEEPSCIENTIST_CODEX_BINARY", raising=False)
    monkeypatch.delenv("DS_CODEX_BINARY", raising=False)
    monkeypatch.setattr(shared, "_resolve_executable_reference", lambda reference: None)
    monkeypatch.setattr(shared, "_codex_repo_roots", lambda: [bundled_root])

    assert shared.resolve_runner_binary("codex", runner_name="codex") == str(bundled_binary)


def test_run_command_hides_windows_console(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_process_session_popen_kwargs(*, hide_window: bool = False, new_process_group: bool = True):  # noqa: ANN001
        captured["hide_window"] = hide_window
        captured["new_process_group"] = new_process_group
        return {"creationflags": 1536}

    def fake_run(args, **kwargs):  # noqa: ANN001
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(shared, "process_session_popen_kwargs", fake_process_session_popen_kwargs)
    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.run_command(["git", "status"], cwd=tmp_path, check=False)

    assert result.returncode == 0
    assert captured["hide_window"] is True
    assert captured["new_process_group"] is False
    assert captured["kwargs"] == {
        "cwd": str(tmp_path),
        "check": False,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "capture_output": True,
        "creationflags": 1536,
    }


def test_run_command_bytes_hides_windows_console(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_process_session_popen_kwargs(*, hide_window: bool = False, new_process_group: bool = True):  # noqa: ANN001
        captured["hide_window"] = hide_window
        captured["new_process_group"] = new_process_group
        return {"creationflags": 1536}

    def fake_run(args, **kwargs):  # noqa: ANN001
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(shared, "process_session_popen_kwargs", fake_process_session_popen_kwargs)
    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.run_command_bytes(["git", "show", "HEAD:README.md"], cwd=tmp_path, check=False)

    assert result.returncode == 0
    assert result.stdout == b"ok"
    assert captured["hide_window"] is True
    assert captured["new_process_group"] is False
    assert captured["kwargs"] == {
        "cwd": str(tmp_path),
        "check": False,
        "text": False,
        "capture_output": True,
        "creationflags": 1536,
    }


def test_ensure_utf8_subprocess_env_sets_python_defaults() -> None:
    env = shared.ensure_utf8_subprocess_env({"CUSTOM_FLAG": "1"})

    assert env["CUSTOM_FLAG"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"


def test_ensure_utf8_subprocess_env_preserves_explicit_python_encoding() -> None:
    env = shared.ensure_utf8_subprocess_env(
        {
            "PYTHONIOENCODING": "utf-16",
            "PYTHONUTF8": "0",
        }
    )

    assert env["PYTHONIOENCODING"] == "utf-16"
    assert env["PYTHONUTF8"] == "0"
