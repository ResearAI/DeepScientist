from __future__ import annotations

from typing import Any

import pytest

from deepscientist.daemon.runner_health import probe_runner_health_at_startup


class FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def log(self, level: str, event: str, **payload: Any) -> None:
        self.events.append((level, event, payload))


class FakeConfigManager:
    def __init__(
        self,
        *,
        runners: dict[str, dict[str, Any]] | None = None,
        probe_results: dict[str, dict[str, Any]] | None = None,
        probe_exceptions: dict[str, Exception] | None = None,
    ) -> None:
        self._runners = runners or {}
        self._probe_results = probe_results or {}
        self._probe_exceptions = probe_exceptions or {}
        self.calls: list[tuple[str, dict | None]] = []

    def load_named_normalized(self, name: str) -> dict[str, Any]:
        if name == "runners":
            return dict(self._runners)
        return {}

    def probe_runner_bootstrap(
        self, runner_name: str, *, persist: bool = False, payload: dict | None = None,
    ) -> dict[str, Any]:
        self.calls.append((runner_name, payload))
        if runner_name in self._probe_exceptions:
            raise self._probe_exceptions[runner_name]
        return self._probe_results.get(runner_name, {"ok": True, "summary": "ok"})


def test_probe_skips_disabled_runners() -> None:
    cm = FakeConfigManager(
        runners={
            "claude": {"enabled": False},
            "codex": {"enabled": True},
        },
        probe_results={"codex": {"ok": True, "summary": "codex hello"}},
    )
    logger = FakeLogger()

    results = probe_runner_health_at_startup(cm, logger, runner_names=["claude", "codex"])

    assert [c[0] for c in cm.calls] == ["codex"]
    assert len(results) == 1
    assert results[0]["runner"] == "codex"
    # info-level event for the success
    levels_events = [(lvl, evt) for lvl, evt, _ in logger.events]
    assert ("info", "daemon.runner_probe_ok") in levels_events


def test_probe_emits_error_with_diagnosis_for_claude_401() -> None:
    cm = FakeConfigManager(
        runners={"claude": {"enabled": True}},
        probe_results={
            "claude": {
                "ok": False,
                "summary": "Failed to authenticate. API Error: 401 authentication_error Invalid authentication credentials",
                "errors": ["Claude Code did not complete the startup hello probe successfully."],
                "details": {"stderr_excerpt": "", "stdout_excerpt": ""},
            }
        },
    )
    logger = FakeLogger()

    probe_runner_health_at_startup(cm, logger, runner_names=["claude"])

    failed_events = [(lvl, evt, payload) for lvl, evt, payload in logger.events if evt == "daemon.runner_probe_failed"]
    assert len(failed_events) == 1
    level, _, payload = failed_events[0]
    assert level == "error"
    assert payload["runner"] == "claude"
    assert payload["diagnosis_code"] == "claude_authentication_failed"
    assert payload["problem"] is not None
    assert any("claude login" in g.lower() for g in payload["guidance"])


def test_probe_emits_warning_when_failure_has_no_diagnosis() -> None:
    cm = FakeConfigManager(
        runners={"claude": {"enabled": True}},
        probe_results={
            "claude": {
                "ok": False,
                "summary": "some unknown failure",
                "errors": ["unknown"],
                "details": {},
            }
        },
    )
    logger = FakeLogger()

    probe_runner_health_at_startup(cm, logger, runner_names=["claude"])

    failed_events = [(lvl, evt, payload) for lvl, evt, payload in logger.events if evt == "daemon.runner_probe_failed"]
    assert len(failed_events) == 1
    level, _, payload = failed_events[0]
    assert level == "warning"
    assert payload["diagnosis_code"] is None


def test_probe_handles_exception_from_bootstrap_call() -> None:
    cm = FakeConfigManager(
        runners={"claude": {"enabled": True}},
        probe_exceptions={"claude": RuntimeError("boom")},
    )
    logger = FakeLogger()

    results = probe_runner_health_at_startup(cm, logger, runner_names=["claude"])

    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["exception"] == "boom"
    assert any(evt == "daemon.runner_probe_exception" for _, evt, _ in logger.events)


def test_probe_uses_default_runner_list_when_none_passed() -> None:
    # When runner_names is None, the function consults list_builtin_runner_names()
    # internally; we just verify it walks the runners payload (no enabled runner here →
    # no probe calls).
    cm = FakeConfigManager(runners={"claude": {"enabled": False}})
    logger = FakeLogger()

    results = probe_runner_health_at_startup(cm, logger)

    assert results == []
    assert cm.calls == []
