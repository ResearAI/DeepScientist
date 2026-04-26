"""Daemon-startup runner health probe.

Runs the same `probe_runner_bootstrap` call that `ds doctor` uses against
each enabled runner once on daemon start, and emits structured events so
auth/credential failures surface immediately instead of waiting for the
first quest turn to fail.
"""
from __future__ import annotations

from typing import Any, Iterable, Protocol

from ..diagnostics import diagnose_runner_failure
from ..runners.metadata import list_builtin_runner_names


class _Logger(Protocol):
    def log(self, level: str, event: str, **payload: Any) -> None: ...


class _ConfigManager(Protocol):
    def load_named_normalized(self, name: str) -> dict[str, Any]: ...
    def probe_runner_bootstrap(
        self, runner_name: str, *, persist: bool = ..., payload: dict | None = ...,
    ) -> dict[str, Any]: ...


def probe_runner_health_at_startup(
    config_manager: _ConfigManager,
    logger: _Logger,
    *,
    runner_names: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Probe each enabled runner once. Returns the list of probe results."""
    runners_payload = config_manager.load_named_normalized("runners")
    candidate_names: list[str] = list(runner_names) if runner_names is not None else list(list_builtin_runner_names())
    results: list[dict[str, Any]] = []
    for runner_name in candidate_names:
        cfg = runners_payload.get(runner_name) if isinstance(runners_payload.get(runner_name), dict) else {}
        if not bool(cfg.get("enabled")):
            continue
        try:
            probe = config_manager.probe_runner_bootstrap(
                runner_name, persist=True, payload=runners_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.log(
                "warning",
                "daemon.runner_probe_exception",
                runner=runner_name,
                error=str(exc),
            )
            results.append({"runner": runner_name, "ok": False, "exception": str(exc)})
            continue
        if probe.get("ok"):
            logger.log(
                "info",
                "daemon.runner_probe_ok",
                runner=runner_name,
                summary=str(probe.get("summary") or ""),
            )
            results.append({"runner": runner_name, "ok": True, "probe": probe})
            continue
        details = probe.get("details") if isinstance(probe.get("details"), dict) else {}
        diagnosis = diagnose_runner_failure(
            runner_name=runner_name,
            summary=str(probe.get("summary") or ""),
            stderr_text=str(details.get("stderr_excerpt") or ""),
            output_text=str(details.get("stdout_excerpt") or ""),
        )
        logger.log(
            "error" if diagnosis is not None else "warning",
            "daemon.runner_probe_failed",
            runner=runner_name,
            summary=str(probe.get("summary") or ""),
            errors=list(probe.get("errors") or []),
            diagnosis_code=getattr(diagnosis, "code", None),
            problem=getattr(diagnosis, "problem", None),
            guidance=list(getattr(diagnosis, "guidance", []) or []),
        )
        results.append({"runner": runner_name, "ok": False, "probe": probe, "diagnosis_code": getattr(diagnosis, "code", None)})
    return results
