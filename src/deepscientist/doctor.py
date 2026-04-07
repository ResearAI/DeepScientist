from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from shutil import which
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .bash_exec.shells import build_exec_shell_launch, build_terminal_shell_launch
from .config import ConfigManager
from .home import ensure_home_layout
from .runtime_tools import RuntimeToolService
from .shared import resolve_runner_binary, utc_now


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
            text=True,
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
    codex_cfg = runners_payload.get("codex") if isinstance(runners_payload.get("codex"), dict) else {}
    claude_cfg = runners_payload.get("claude") if isinstance(runners_payload.get("claude"), dict) else {}

    errors: list[str] = []
    warnings: list[str] = []
    guidance: list[str] = []

    if default_runner != "codex":
        errors.append("Current open-source release supports `codex` as the runnable default runner.")
        guidance.append("Set `default_runner: codex` in `~/DeepScientist/config/config.yaml`.")
    if not bool(codex_cfg.get("enabled", False)):
        errors.append("`runners.codex.enabled` must stay `true` in the current release.")
        guidance.append("Set `runners.codex.enabled: true` in `~/DeepScientist/config/runners.yaml`.")
    if bool(claude_cfg.get("enabled", False)):
        errors.append("`claude` is still TODO in the current release and should stay disabled.")
        guidance.append("Set `runners.claude.enabled: false` in `~/DeepScientist/config/runners.yaml`.")
    else:
        warnings.append("`claude` remains a TODO/reserved runner slot and is not runnable yet.")

    return _make_check(
        check_id="runner_support",
        label="Supported runners",
        ok=len(errors) == 0,
        summary="Runner policy matches the current release surface." if len(errors) == 0 else "Runner policy needs adjustment.",
        warnings=warnings,
        errors=errors,
        guidance=guidance,
        details={"default_runner": default_runner},
    )


def _check_codex(config_manager: ConfigManager) -> dict[str, Any]:
    runners_payload = config_manager.load_named_normalized("runners")
    codex_cfg = runners_payload.get("codex") if isinstance(runners_payload.get("codex"), dict) else {}
    binary = str(codex_cfg.get("binary") or "codex").strip() or "codex"
    resolved_binary = resolve_runner_binary(binary, runner_name="codex")

    if not resolved_binary:
        return _make_check(
            check_id="codex",
            label="Codex CLI",
            ok=False,
            summary="Codex CLI is not available to DeepScientist.",
            errors=[f"Runner binary `{binary}` could not be resolved."],
            guidance=config_manager._codex_missing_binary_guidance(codex_cfg),
            details={"binary": binary},
        )

    probe = config_manager.probe_codex_bootstrap(persist=False, payload=runners_payload)
    probe_errors = [str(value) for value in probe.get("errors") or []]
    probe_warnings = [str(value) for value in probe.get("warnings") or []]
    probe_guidance = [str(value) for value in probe.get("guidance") or []]
    summary = str(probe.get("summary") or "Codex startup probe completed.")
    if probe.get("ok"):
        return _make_check(
            check_id="codex",
            label="Codex CLI",
            ok=True,
            summary=summary,
            warnings=probe_warnings,
            details={"resolved_binary": resolved_binary},
        )
    if not probe_guidance:
        probe_guidance = [
            "Run `codex login` (or just `codex`) manually once and complete login, then retry `ds doctor`.",
        ]
    return _make_check(
        check_id="codex",
        label="Codex CLI",
        ok=False,
        summary=summary,
        warnings=probe_warnings,
        errors=probe_errors or ["Codex startup probe did not succeed."],
        guidance=probe_guidance,
        details={"resolved_binary": resolved_binary},
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


def run_doctor(home: Path, *, repo_root: Path) -> dict[str, Any]:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    config_payload = config_manager.load_named_normalized("config")
    ui_payload = config_payload.get("ui") if isinstance(config_payload.get("ui"), dict) else {}
    host = str(ui_payload.get("host") or "0.0.0.0").strip() or "0.0.0.0"
    port = int(ui_payload.get("port") or 20999)
    browser_url = _browser_ui_url(host, port)

    checks = [
        _check_python_runtime(),
        _check_home_writable(home),
        _check_uv(home),
        _check_shell_backend(),
        _check_git(config_manager),
        _check_config_validation(config_manager),
        _check_runner_support(config_manager),
        _check_codex(config_manager),
        _check_latex_runtime(home),
        _check_bundles(repo_root),
        _check_ui_port(home, config_manager),
    ]

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
