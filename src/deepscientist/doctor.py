from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
import socket
import subprocess
import sys
import tempfile
from shutil import which
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .bash_exec.shells import build_exec_shell_launch, build_terminal_shell_launch
from .config import ConfigManager
from .diagnostics import diagnose_runner_failure
from .home import ensure_home_layout
from .runtime_tools import RuntimeToolService
from .shared import read_json, read_jsonl_tail, resolve_runner_binary, utc_now, utf8_text_subprocess_kwargs


_RUNTIME_FAILURE_LOOKBACK = timedelta(hours=24)


def _browser_ui_url(host: str, port: int) -> str:
    normalized = str(host or "").strip()
    browser_host = "127.0.0.1" if normalized in {"", "0.0.0.0", "::", "[::]"} else normalized
    return f"http://{browser_host}:{port}"


def _check_status(ok: bool, warnings: list[str] | None = None) -> str:
    if not ok:
        return "error"
    if warnings:
        return "warn"
    return "ok"


def _make_check(
    *,
    check_id: str,
    label: str,
    ok: bool,
    summary: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    guidance: list[str] | None = None,
    details: dict[str, Any] | None = None,
    problem: str | None = None,
    why: str | None = None,
    fix: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    normalized_warnings = list(warnings or [])
    normalized_errors = list(errors or [])
    return {
        "id": check_id,
        "label": label,
        "ok": ok and not normalized_errors,
        "status": _check_status(ok and not normalized_errors, normalized_warnings),
        "summary": summary,
        "warnings": normalized_warnings,
        "errors": normalized_errors,
        "guidance": list(guidance or []),
        "details": dict(details or {}),
        "problem": str(problem or "").strip() or None,
        "why": str(why or "").strip() or None,
        "fix": [str(line) for line in (fix or []) if str(line).strip()],
        "evidence": [str(line) for line in (evidence or []) if str(line).strip()],
    }


def _check_python_runtime() -> dict[str, Any]:
    try:
        import _cffi_backend  # noqa: F401
        import cryptography  # noqa: F401
        import deepscientist.cli  # noqa: F401
    except Exception as exc:  # pragma: no cover - import failures are environment-dependent
        return _make_check(
            check_id="python_runtime",
            label="Python runtime",
            ok=False,
            summary="Local Python runtime is not healthy.",
            errors=[str(exc)],
            guidance=[
                "Reinstall the package or rerun `ds` so DeepScientist can rebuild its local Python runtime.",
            ],
            details={"python": sys.executable, "version": sys.version.split()[0]},
        )
    return _make_check(
        check_id="python_runtime",
        label="Python runtime",
        ok=True,
        summary="Local Python runtime imports succeeded.",
        details={"python": sys.executable, "version": sys.version.split()[0]},
    )


def _check_home_writable(home: Path) -> dict[str, Any]:
    try:
        ensure_home_layout(home)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=home / "runtime", delete=False) as handle:
            handle.write("doctor\n")
            temp_path = Path(handle.name)
        temp_path.unlink(missing_ok=True)
    except Exception as exc:
        return _make_check(
            check_id="home_writable",
            label="Home path",
            ok=False,
            summary="DeepScientist home is not writable.",
            errors=[str(exc)],
            guidance=[
                f"Ensure `{home}` exists and is writable by the current user.",
            ],
            details={"home": str(home)},
        )
    return _make_check(
        check_id="home_writable",
        label="Home path",
        ok=True,
        summary="DeepScientist home exists and is writable.",
        details={"home": str(home)},
    )


def _resolve_uv_binary(home: Path) -> str | None:
    for env_name in ("DEEPSCIENTIST_UV", "UV_BIN"):
        override = str(os.environ.get(env_name) or "").strip()
        if not override:
            continue
        override_path = Path(override).expanduser()
        if override_path.exists():
            return str(override_path)
        resolved_override = which(override)
        if resolved_override:
            return resolved_override

    local_candidates = [
        home / "runtime" / "tools" / "uv" / "bin" / "uv",
        home / "runtime" / "tools" / "uv" / "bin" / "uv.exe",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return which("uv")


def _check_uv(home: Path) -> dict[str, Any]:
    resolved = _resolve_uv_binary(home)
    if not resolved:
        guidance = [
            "Run `ds` once so DeepScientist can bootstrap a local uv runtime manager automatically.",
        ]
        if sys.platform == "win32":
            guidance.append('PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`')
        else:
            guidance.append("macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`")
        return _make_check(
            check_id="uv",
            label="uv runtime manager",
            ok=False,
            summary="uv is not available to DeepScientist.",
            errors=["DeepScientist cannot provision or repair its local Python runtime without `uv`."],
            guidance=guidance,
        )

    version = ""
    try:
        result = subprocess.run(
            [resolved, "--version"],
            check=False,
            capture_output=True,
            **utf8_text_subprocess_kwargs(),
        )
        if result.returncode == 0:
            version = (result.stdout or result.stderr or "").strip()
    except OSError:
        version = ""

    return _make_check(
        check_id="uv",
        label="uv runtime manager",
        ok=True,
        summary="uv is available for locked Python runtime management.",
        details={"resolved_binary": resolved, "version": version or None},
    )


def _check_git(config_manager: ConfigManager) -> dict[str, Any]:
    readiness = config_manager.git_readiness()
    return _make_check(
        check_id="git",
        label="Git",
        ok=bool(readiness.get("installed")) and not list(readiness.get("errors") or []),
        summary="Git is available for quest repositories." if readiness.get("installed") else "Git is not available.",
        warnings=list(readiness.get("warnings") or []),
        errors=list(readiness.get("errors") or []),
        guidance=list(readiness.get("guidance") or []),
        details={
            "user_name": readiness.get("user_name"),
            "user_email": readiness.get("user_email"),
        },
    )


def _check_config_validation(config_manager: ConfigManager) -> dict[str, Any]:
    validation = config_manager.validate_all()
    warnings: list[str] = []
    errors: list[str] = []
    optional_missing_prefix = "Optional config file is missing"

    for item in validation.get("files") or []:
        item_errors = [str(value) for value in item.get("errors") or []]
        item_warnings = [str(value) for value in item.get("warnings") or []]
        errors.extend(item_errors)
        warnings.extend([value for value in item_warnings if not value.startswith(optional_missing_prefix)])

    return _make_check(
        check_id="config_validation",
        label="Config files",
        ok=len(errors) == 0,
        summary="Required config files validated successfully." if len(errors) == 0 else "Config validation failed.",
        warnings=warnings,
        errors=errors,
        guidance=["Run `ds config validate` for the full structured validation report."] if errors else [],
    )


def _check_runner_support(config_manager: ConfigManager) -> dict[str, Any]:
    config_payload = config_manager.load_named_normalized("config")
    runners_payload = config_manager.load_named_normalized("runners")

    default_runner = str(config_payload.get("default_runner") or "codex").strip().lower() or "codex"
    enabled_runners = sorted(
        name for name, value in runners_payload.items() if isinstance(value, dict) and bool(value.get("enabled", False))
    )

    errors: list[str] = []
    warnings: list[str] = []
    guidance: list[str] = []

    if not enabled_runners:
        errors.append("At least one runner must be enabled.")
        guidance.append("Enable one of `codex`, `claude`, `kimi`, or `opencode` in `~/DeepScientist/config/runners.yaml`.")
    if default_runner not in runners_payload:
        errors.append(f"Configured default runner `{default_runner}` does not exist in `runners.yaml`.")
    elif default_runner not in enabled_runners:
        errors.append(f"Configured default runner `{default_runner}` is currently disabled.")
        guidance.append(
            f"Set `runners.{default_runner}.enabled: true`, or switch `default_runner` to one of: {', '.join(enabled_runners) or 'none'}."
        )
    if len(enabled_runners) > 1:
        warnings.append(f"Multiple runners are enabled: {', '.join(enabled_runners)}.")

    return _make_check(
        check_id="runner_support",
        label="Supported runners",
        ok=len(errors) == 0,
        summary="Runner policy is internally consistent." if len(errors) == 0 else "Runner policy needs adjustment.",
        warnings=warnings,
        errors=errors,
        guidance=guidance,
        details={"default_runner": default_runner, "enabled_runners": enabled_runners},
    )


def _check_runner(config_manager: ConfigManager, runner_name: str) -> dict[str, Any]:
    normalized_runner = str(runner_name or "codex").strip().lower() or "codex"
    runners_payload = config_manager.load_named_normalized("runners")
    runner_cfg = runners_payload.get(normalized_runner) if isinstance(runners_payload.get(normalized_runner), dict) else {}
    binary = str(runner_cfg.get("binary") or normalized_runner).strip() or normalized_runner
    resolved_binary = resolve_runner_binary(binary, runner_name=normalized_runner)
    label = {
        "codex": "Codex CLI",
        "claude": "Claude Code CLI",
        "kimi": "Kimi Code CLI",
        "opencode": "OpenCode CLI",
    }.get(normalized_runner, normalized_runner)

    if not resolved_binary:
        guidance = config_manager._runner_missing_binary_guidance(normalized_runner, runner_cfg)
        return _make_check(
            check_id=normalized_runner,
            label=label,
            ok=False,
            summary=f"{label} is not available to DeepScientist.",
            errors=[f"Runner binary `{binary}` could not be resolved."],
            guidance=guidance,
            details={"binary": binary},
        )

    probe = (
        config_manager.probe_codex_bootstrap(persist=False, payload=runners_payload)
        if normalized_runner == "codex"
        else config_manager.probe_runner_bootstrap(normalized_runner, persist=False, payload=runners_payload)
    )
    probe_errors = [str(value) for value in probe.get("errors") or []]
    probe_warnings = [str(value) for value in probe.get("warnings") or []]
    probe_guidance = [str(value) for value in probe.get("guidance") or []]
    summary = str(probe.get("summary") or f"{label} startup probe completed.")
    probe_details = probe.get("details") if isinstance(probe.get("details"), dict) else {}
    diagnosis = None
    if normalized_runner == "codex":
        diagnosis = diagnose_runner_failure(
            runner_name="codex",
            summary="\n".join([summary, *probe_errors]),
            stderr_text=str(probe_details.get("stderr_excerpt") or ""),
            output_text=str(probe_details.get("stdout_excerpt") or ""),
        )
    if probe.get("ok"):
        return _make_check(
            check_id=normalized_runner,
            label=label,
            ok=True,
            summary=summary,
            warnings=probe_warnings,
            details={"resolved_binary": resolved_binary},
        )
    return _make_check(
        check_id=normalized_runner,
        label=label,
        ok=False,
        summary=diagnosis.problem if diagnosis is not None else summary,
        warnings=probe_warnings,
        errors=probe_errors or [f"{label} startup probe did not succeed."],
        guidance=probe_guidance,
        details={"resolved_binary": resolved_binary},
        problem=diagnosis.problem if diagnosis is not None else None,
        why=diagnosis.why if diagnosis is not None else None,
        fix=list(diagnosis.guidance) if diagnosis is not None else None,
        evidence=([f"matched: {diagnosis.matched_text}"] if diagnosis is not None and diagnosis.matched_text else None),
    )


def _check_codex(config_manager: ConfigManager) -> dict[str, Any]:
    return _check_runner(config_manager, "codex")

def _parse_timestamp(value: object) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _read_runtime_failure_record(home: Path) -> dict[str, Any] | None:
    quests_root = home / "quests"
    if not quests_root.exists():
        return None

    latest: dict[str, Any] | None = None
    latest_at: datetime | None = None
    cutoff = datetime.now(UTC) - _RUNTIME_FAILURE_LOOKBACK
    interesting_types = {
        "runner.turn_error",
        "runner.turn_retry_exhausted",
        "quest.runtime_auto_resume_suppressed",
    }

    for quest_root in sorted(quests_root.glob("*/")):
        events = read_jsonl_tail(quest_root / ".ds" / "events.jsonl", 300)
        for event in reversed(events):
            event_type = str(event.get("type") or "").strip()
            if event_type not in interesting_types:
                continue
            created_at = _parse_timestamp(event.get("created_at"))
            if created_at is None or created_at < cutoff:
                continue
            run_id = str(event.get("run_id") or "").strip() or None
            stderr_text = ""
            output_text = ""
            if run_id:
                run_root = quest_root / ".ds" / "runs" / run_id
                result_payload = read_json(run_root / "result.json", {})
                if isinstance(result_payload, dict):
                    stderr_text = str(result_payload.get("stderr_text") or "").strip()
                    output_text = str(result_payload.get("output_text") or "").strip()
                stderr_path = run_root / "stderr.txt"
                if not stderr_text and stderr_path.exists():
                    try:
                        stderr_text = stderr_path.read_text(encoding="utf-8")
                    except OSError:
                        stderr_text = ""
            candidate = {
                "quest_id": quest_root.name,
                "run_id": run_id,
                "event_type": event_type,
                "summary": str(event.get("summary") or "").strip(),
                "created_at": created_at.isoformat(),
                "stderr_text": stderr_text,
                "output_text": output_text,
                "recent_attempts": event.get("recent_attempts"),
            }
            if latest_at is None or created_at > latest_at:
                latest = candidate
                latest_at = created_at
            break
    return latest


def _check_recent_runtime_failures(home: Path) -> dict[str, Any]:
    record = _read_runtime_failure_record(home)
    if record is None:
        return _make_check(
            check_id="recent_runtime_failures",
            label="Recent runtime failures",
            ok=True,
            summary="No recent quest runtime failures were found.",
        )

    event_type = str(record.get("event_type") or "").strip()
    quest_id = str(record.get("quest_id") or "").strip() or None
    run_id = str(record.get("run_id") or "").strip() or None
    summary = str(record.get("summary") or "").strip()
    details = {
        "quest_id": quest_id,
        "run_id": run_id,
        "event_type": event_type,
        "observed_at": record.get("created_at"),
    }

    if event_type == "quest.runtime_auto_resume_suppressed":
        recent_attempts = int(record.get("recent_attempts") or 0)
        return _make_check(
            check_id="recent_runtime_failures",
            label="Recent runtime failures",
            ok=True,
            summary="DeepScientist recently suppressed auto-resume to avoid a crash loop.",
            warnings=["Automatic continuation was paused after repeated recovery attempts in a short window."],
            guidance=[
                "Inspect the most recent failing runner path before using `/resume` again.",
                "If the failure was a provider-side 400/protocol error, fix that request path first instead of retrying immediately.",
            ],
            details=details,
            problem="Automatic crash recovery was suppressed.",
            why="The same quest hit repeated recovery attempts in a short window, so DeepScientist parked it instead of looping forever.",
            fix=[
                "Open the latest failing quest logs and identify the deterministic runner/provider error.",
                "Resume manually only after the underlying runner or provider issue is corrected.",
            ],
            evidence=[
                *( [f"quest: {quest_id}"] if quest_id else [] ),
                f"recent recovery attempts: {recent_attempts}",
            ],
        )

    diagnosis = diagnose_runner_failure(
        runner_name="codex",
        summary=summary,
        stderr_text=str(record.get("stderr_text") or ""),
        output_text=str(record.get("output_text") or ""),
    )
    if diagnosis is None:
        return _make_check(
            check_id="recent_runtime_failures",
            label="Recent runtime failures",
            ok=True,
            summary="A recent quest runtime failure was found.",
            warnings=[summary or "The latest quest run failed, but doctor could not classify it precisely yet."],
            guidance=[
                "Open the latest run stderr and events journal for the failing quest.",
                "If the same failure repeats, capture the run_id and provider response text before retrying again.",
            ],
            details=details,
            problem="A recent quest run failed.",
            why="Doctor found a recent runtime failure event but could not match it to a known deterministic error pattern.",
            fix=[
                "Inspect the failing run's stderr and provider response text.",
                "If the error is deterministic, avoid burning the retry budget until the request shape or config is fixed.",
            ],
            evidence=[
                *( [f"quest: {quest_id}"] if quest_id else [] ),
                *( [f"run: {run_id}"] if run_id else [] ),
                *( [f"summary: {summary}"] if summary else [] ),
            ],
        )

    return _make_check(
        check_id="recent_runtime_failures",
        label="Recent runtime failures",
        ok=True,
        summary=diagnosis.problem,
        warnings=[summary] if summary and summary != diagnosis.problem else [],
        guidance=list(diagnosis.guidance),
        details=details,
        problem=diagnosis.problem,
        why=diagnosis.why,
        fix=list(diagnosis.guidance),
        evidence=[
            *( [f"quest: {quest_id}"] if quest_id else [] ),
            *( [f"run: {run_id}"] if run_id else [] ),
            *( [f"matched: {diagnosis.matched_text}"] if diagnosis.matched_text else [] ),
        ],
    )


def _check_bundles(repo_root: Path) -> dict[str, Any]:
    web_entry = repo_root / "src" / "ui" / "dist" / "index.html"
    tui_entry = repo_root / "src" / "tui" / "dist" / "index.js"
    errors: list[str] = []
    guidance: list[str] = []

    if not web_entry.exists():
        errors.append(f"Missing web bundle: {web_entry}")
        guidance.append("Build the web UI: `npm --prefix src/ui install && npm --prefix src/ui run build`.")
    if not tui_entry.exists():
        errors.append(f"Missing TUI bundle: {tui_entry}")
        guidance.append("Build the TUI: `npm --prefix src/tui install && npm --prefix src/tui run build`.")

    return _make_check(
        check_id="bundles",
        label="UI bundles",
        ok=len(errors) == 0,
        summary="Web and TUI bundles are present." if len(errors) == 0 else "One or more UI bundles are missing.",
        errors=errors,
        guidance=guidance,
        details={"web_bundle": str(web_entry), "tui_bundle": str(tui_entry)},
    )


def _check_shell_backend() -> dict[str, Any]:
    exec_launch = build_exec_shell_launch("echo ok")
    terminal_launch = build_terminal_shell_launch(Path("doctor-terminal-probe"))

    def resolve_binary(binary: str) -> str | None:
        candidate = str(binary or "").strip()
        if not candidate:
            return None
        if os.path.isabs(candidate) or os.path.sep in candidate or (os.path.altsep and os.path.altsep in candidate):
            return candidate if Path(candidate).exists() else None
        return which(candidate)

    details = {
        "exec_shell": exec_launch.shell_name,
        "exec_shell_family": exec_launch.family,
        "exec_argv": exec_launch.argv,
        "terminal_shell": terminal_launch.shell_name,
        "terminal_shell_family": terminal_launch.family,
        "terminal_argv": terminal_launch.argv,
    }
    warnings: list[str] = []
    guidance: list[str] = []
    errors: list[str] = []

    exec_binary = resolve_binary(exec_launch.argv[0])
    terminal_binary = resolve_binary(terminal_launch.argv[0])
    details["exec_resolved_binary"] = exec_binary
    details["terminal_resolved_binary"] = terminal_binary

    if sys.platform == "win32":
        warnings.append("Native Windows support is currently experimental; WSL2 remains the most battle-tested path.")
        if not exec_binary:
            errors.append("DeepScientist could not resolve a Windows command shell for bash_exec.")
            guidance.append("Install PowerShell (`pwsh`) or ensure `powershell.exe` is available on PATH.")
        if not terminal_binary:
            errors.append("DeepScientist could not resolve a Windows interactive shell backend.")
            guidance.append("Ensure `powershell.exe` is available on PATH for the interactive terminal surface.")
    return _make_check(
        check_id="shell_backend",
        label="Shell backend",
        ok=len(errors) == 0,
        summary="DeepScientist resolved platform shell backends for command and terminal sessions." if len(errors) == 0 else "DeepScientist could not resolve a required shell backend.",
        warnings=warnings,
        errors=errors,
        guidance=guidance,
        details=details,
    )


def _check_latex_runtime(home: Path) -> dict[str, Any]:
    runtime = RuntimeToolService(home).status("tinytex")
    pdflatex = runtime.get("binaries", {}).get("pdflatex") or {}
    details = {
        "latex_runtime_summary": runtime.get("summary"),
        "latex_pdflatex_path": pdflatex.get("path"),
        "latex_pdflatex_source": pdflatex.get("source"),
        "latex_tinytex_root": runtime.get("tinytex", {}).get("root"),
    }
    return _make_check(
        check_id="latex_runtime",
        label="LaTeX runtime (optional)",
        ok=True,
        summary=str(runtime.get("summary") or "Optional local LaTeX runtime was checked."),
        warnings=list(runtime.get("warnings") or []),
        guidance=list(runtime.get("guidance") or []),
        details=details,
    )


def _query_local_health(url: str) -> dict[str, Any] | None:
    request = Request(f"{url}/api/health", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=1.5) as response:  # noqa: S310
            import json

            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, TimeoutError, URLError, ValueError):
        return None


def _port_is_bindable(host: str, port: int) -> tuple[bool, str | None]:
    normalized = str(host or "").strip() or "0.0.0.0"
    family = socket.AF_INET6 if ":" in normalized and normalized != "0.0.0.0" else socket.AF_INET
    bind_host = "::" if normalized in {"[::]", "::"} else normalized
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()
    return True, None


def _check_ui_port(home: Path, config_manager: ConfigManager) -> dict[str, Any]:
    config_payload = config_manager.load_named_normalized("config")
    ui_payload = config_payload.get("ui") if isinstance(config_payload.get("ui"), dict) else {}
    host = str(ui_payload.get("host") or "0.0.0.0").strip() or "0.0.0.0"
    port = int(ui_payload.get("port") or 20999)
    browser_url = _browser_ui_url(host, port)
    health = _query_local_health(browser_url)

    if health and health.get("status") == "ok":
        daemon_home = str(health.get("home") or "").strip()
        if daemon_home == str(home.resolve()):
            return _make_check(
                check_id="ui_port",
                label="Web port",
                ok=True,
                summary="DeepScientist daemon is already running on the configured port.",
                guidance=[f"Open {browser_url} in your browser or stop it with `ds --stop`."],
                details={"browser_url": browser_url, "host": host, "port": port},
            )
        return _make_check(
            check_id="ui_port",
            label="Web port",
            ok=False,
            summary="The configured port is already used by another DeepScientist home.",
            errors=[f"{browser_url} is already serving a daemon for `{daemon_home}`."],
            guidance=[
                "Stop the other daemon first or change `ui.port` in `~/DeepScientist/config/config.yaml`.",
            ],
            details={"browser_url": browser_url, "host": host, "port": port},
        )

    bindable, bind_error = _port_is_bindable(host, port)
    if bindable:
        return _make_check(
            check_id="ui_port",
            label="Web port",
            ok=True,
            summary="The configured web port is free.",
            details={"browser_url": browser_url, "host": host, "port": port},
        )
    return _make_check(
        check_id="ui_port",
        label="Web port",
        ok=False,
        summary="The configured web port is not available.",
        errors=[bind_error or "Port bind failed."],
        guidance=[
            "Run `ds --stop` if this is an old managed daemon.",
            "Otherwise set a different `ui.port` in `~/DeepScientist/config/config.yaml`.",
        ],
        details={"browser_url": browser_url, "host": host, "port": port},
    )


DoctorProgressCallback = Callable[[dict[str, Any]], None]


def run_doctor(
    home: Path,
    *,
    repo_root: Path,
    on_check: DoctorProgressCallback | None = None,
) -> dict[str, Any]:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    config_payload = config_manager.load_named_normalized("config")
    ui_payload = config_payload.get("ui") if isinstance(config_payload.get("ui"), dict) else {}
    host = str(ui_payload.get("host") or "0.0.0.0").strip() or "0.0.0.0"
    port = int(ui_payload.get("port") or 20999)
    browser_url = _browser_ui_url(host, port)

    check_factories: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("python_runtime", _check_python_runtime),
        ("home_writable", lambda: _check_home_writable(home)),
        ("uv", lambda: _check_uv(home)),
        ("shell_backend", _check_shell_backend),
        ("git", lambda: _check_git(config_manager)),
        ("config_validation", lambda: _check_config_validation(config_manager)),
        ("runner_support", lambda: _check_runner_support(config_manager)),
    ]
    runners_payload = config_manager.load_named_normalized("runners")
    default_runner = str(config_payload.get("default_runner") or "codex").strip().lower() or "codex"
    runner_targets: list[str] = []
    for candidate in [default_runner, *sorted(name for name, value in runners_payload.items() if isinstance(value, dict) and bool(value.get("enabled", False)))]:
        normalized_candidate = str(candidate or "").strip().lower()
        if normalized_candidate and normalized_candidate not in runner_targets:
            runner_targets.append(normalized_candidate)
    check_factories.extend((runner_name, (lambda runner_name=runner_name: _check_runner(config_manager, runner_name))) for runner_name in runner_targets)
    check_factories.extend([
        ("recent_runtime_failures", lambda: _check_recent_runtime_failures(home)),
        ("latex_runtime", lambda: _check_latex_runtime(home)),
        ("bundles", lambda: _check_bundles(repo_root)),
        ("ui_port", lambda: _check_ui_port(home, config_manager)),
    ])
    checks: list[dict[str, Any]] = []
    total_checks = len(check_factories)
    for index, (check_id, factory) in enumerate(check_factories, start=1):
        check = factory()
        checks.append(check)
        if on_check is not None:
            on_check(
                {
                    "check_id": check_id,
                    "index": index,
                    "total": total_checks,
                    "check": check,
                }
            )

    return {
        "ok": all(item["ok"] for item in checks),
        "timestamp": utc_now(),
        "home": str(home),
        "browser_url": browser_url,
        "checks": checks,
    }


def render_doctor_report(report: dict[str, Any]) -> str:
    lines = [
        "DeepScientist doctor",
        "",
        f"Home: {report.get('home')}",
        f"Web UI: {report.get('browser_url')}",
        f"Checked at: {report.get('timestamp')}",
        "",
    ]

    for item in report.get("checks") or []:
        status = str(item.get("status") or "ok").upper()
        icon = {"OK": "[ok]", "WARN": "[warn]", "ERROR": "[fail]"}.get(status, "[info]")
        lines.append(f"{icon} {item.get('label')}: {item.get('summary')}")
        problem = str(item.get("problem") or "").strip()
        why = str(item.get("why") or "").strip()
        fix_lines = [str(line) for line in item.get("fix") or [] if str(line).strip()]
        evidence_lines = [str(line) for line in item.get("evidence") or [] if str(line).strip()]
        if problem:
            lines.append(f"  problem: {problem}")
        if why:
            lines.append(f"  why: {why}")
        for line in fix_lines:
            lines.append(f"  fix: {line}")
        for line in evidence_lines:
            lines.append(f"  evidence: {line}")
        for warning in item.get("warnings") or []:
            lines.append(f"  warning: {warning}")
        for error in item.get("errors") or []:
            lines.append(f"  error: {error}")
        details = item.get("details") or {}
        if isinstance(details, dict):
            resolved_binary = str(details.get("resolved_binary") or "").strip()
            if resolved_binary:
                lines.append(f"  resolved binary: {resolved_binary}")
            latex_pdflatex_path = str(details.get("latex_pdflatex_path") or "").strip()
            if latex_pdflatex_path:
                lines.append(f"  pdflatex: {latex_pdflatex_path}")
            latex_tinytex_root = str(details.get("latex_tinytex_root") or "").strip()
            if latex_tinytex_root:
                lines.append(f"  tinytex root: {latex_tinytex_root}")
            browser_url = str(details.get("browser_url") or "").strip()
            if browser_url:
                lines.append(f"  url: {browser_url}")
        lines.append("")

    guidance: list[str] = []
    seen_guidance: set[str] = set()
    for item in report.get("checks") or []:
        for line in item.get("guidance") or []:
            if line not in seen_guidance:
                seen_guidance.add(line)
                guidance.append(str(line))

    if guidance:
        lines.append("Next steps")
        lines.append("")
        for index, line in enumerate(guidance, start=1):
            lines.append(f"{index}. {line}")
        lines.append("")

    if report.get("ok"):
        lines.append("Everything looks ready. Run `ds` to start DeepScientist.")
    else:
        lines.append("DeepScientist is not fully ready yet. Fix the failed checks above, then rerun `ds doctor`.")
    return "\n".join(lines).rstrip() + "\n"
