from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from deepscientist.cli import build_parser
from deepscientist.config import ConfigManager
from deepscientist.doctor import render_doctor_report, run_doctor
from deepscientist.home import ensure_home_layout, repo_root


def test_cli_parser_exposes_doctor_and_removes_metrics() -> None:
    parser = build_parser()

    doctor_args = parser.parse_args(["doctor"])
    docker_args = parser.parse_args(["docker"])
    latex_args = parser.parse_args(["latex", "status"])

    assert doctor_args.command == "doctor"
    assert docker_args.command in {"doctor", "docker"}
    assert latex_args.command == "latex"
    assert latex_args.latex_command == "status"

    with pytest.raises(SystemExit):
        parser.parse_args(["metrics"])


def test_cli_parser_reports_clear_argument_errors(capsys) -> None:  # type: ignore[no-untyped-def]
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["run", "baseline", "--quest-id", "q-001", "--message", "hello", "--bogus"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "DeepScientist argument error:" in captured.err
    assert "unrecognized arguments: --bogus" in captured.err
    assert "Run `ds --help` for usage." in captured.err


def test_doctor_report_covers_ready_local_install(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.doctor.resolve_runner_binary", lambda binary, runner_name=None: "/usr/bin/codex")
    monkeypatch.setattr("deepscientist.doctor._query_local_health", lambda url: None)
    monkeypatch.setattr("deepscientist.doctor._port_is_bindable", lambda host, port: (True, None))
    monkeypatch.setattr(
        "deepscientist.doctor._check_bundles",
        lambda root: {
            "id": "bundles",
            "label": "UI bundles",
            "ok": True,
            "status": "ok",
            "summary": "Web and TUI bundles are present.",
            "warnings": [],
            "errors": [],
            "guidance": [],
            "details": {},
        },
    )
    monkeypatch.setattr("deepscientist.doctor.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(
        "deepscientist.doctor.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="uv 0.9.2\n", stderr=""),
    )

    def fake_git_readiness(self):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "installed": True,
            "user_name": "Deep Scientist",
            "user_email": "deep@example.com",
            "warnings": [],
            "errors": [],
            "guidance": [],
        }

    def fake_probe(self, *, persist=False, payload=None):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "summary": "Codex startup probe completed.",
            "warnings": [],
            "errors": [],
            "guidance": [],
            "details": {
                "resolved_binary": "/usr/bin/codex",
            },
        }

    monkeypatch.setattr(ConfigManager, "git_readiness", fake_git_readiness)
    monkeypatch.setattr(ConfigManager, "probe_codex_bootstrap", fake_probe)

    report = run_doctor(temp_home, repo_root=repo_root())
    rendered = render_doctor_report(report)

    assert report["ok"] is True
    assert "DeepScientist doctor" in rendered
    assert "Codex startup probe completed." in rendered
    assert "Everything looks ready. Run `ds` to start DeepScientist." in rendered


def test_doctor_reports_optional_latex_runtime(monkeypatch, temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()

    monkeypatch.setattr("deepscientist.doctor.resolve_runner_binary", lambda binary, runner_name=None: "/usr/bin/codex")
    monkeypatch.setattr("deepscientist.doctor._query_local_health", lambda url: None)
    monkeypatch.setattr("deepscientist.doctor._port_is_bindable", lambda host, port: (True, None))
    monkeypatch.setattr(
        "deepscientist.doctor._check_bundles",
        lambda root: {
            "id": "bundles",
            "label": "UI bundles",
            "ok": True,
            "status": "ok",
            "summary": "Web and TUI bundles are present.",
            "warnings": [],
            "errors": [],
            "guidance": [],
            "details": {},
        },
    )
    monkeypatch.setattr("deepscientist.doctor.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(
        "deepscientist.doctor.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="uv 0.9.2\n", stderr=""),
    )

    def fake_git_readiness(self):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "installed": True,
            "user_name": "Deep Scientist",
            "user_email": "deep@example.com",
            "warnings": [],
            "errors": [],
            "guidance": [],
        }

    def fake_probe(self, *, persist=False, payload=None):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "summary": "Codex startup probe completed.",
            "warnings": [],
            "errors": [],
            "guidance": [],
        }

    monkeypatch.setattr(ConfigManager, "git_readiness", fake_git_readiness)
    monkeypatch.setattr(ConfigManager, "probe_codex_bootstrap", fake_probe)
    monkeypatch.setattr(
        "deepscientist.runtime_tools.service.RuntimeToolService.status",
        lambda self, name: {
            "summary": "Local `pdflatex` is not available.",
            "warnings": ["Local PDF compilation is optional and currently unavailable because `pdflatex` is missing."],
            "guidance": ["Install a lightweight TinyTeX runtime with `ds latex install-runtime`."],
            "binaries": {"pdflatex": {"path": None, "source": None}},
            "tinytex": {"root": None},
        } if name == "tinytex" else {},
    )

    report = run_doctor(temp_home, repo_root=repo_root())
    latex_check = next(item for item in report["checks"] if item["id"] == "latex_runtime")

    assert latex_check["ok"] is True
    assert latex_check["status"] == "warn"
    assert "pdflatex" in latex_check["summary"]
