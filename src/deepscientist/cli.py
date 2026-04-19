from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

from .artifact import ArtifactService
from .config import ConfigManager
from .daemon import DaemonApp
from .doctor import render_doctor_report, run_doctor
from .home import default_home, ensure_home_layout, repo_root
from .memory import MemoryService
from .migration import migrate_deepscientist_root
from .network import configure_runtime_proxy, urlopen_with_proxy as urlopen
from .prompts import PromptBuilder
from .quest import QuestService
from .registries import BaselineRegistry
from .runners import ClaudeRunner, CodexRunner, OpenCodeRunner, RunRequest, get_runner_factory, register_builtin_runners
from .runtime_tools import RuntimeToolService
from .runtime_logs import JsonlLogger
from .shared import ensure_dir, read_json, read_yaml
from .skills import SkillInstaller
from .tui import watch_tui


class DeepScientistArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"DeepScientist argument error: {message}\nRun `{self.prog} --help` for usage.\n")


def _local_ui_url(host: str, port: int) -> str:
    normalized = str(host or "").strip()
    connect_host = "127.0.0.1" if normalized in {"0.0.0.0", "::", "[::]", ""} else normalized
    if connect_host.startswith("[") and connect_host.endswith("]"):
        rendered_host = connect_host
    elif ":" in connect_host:
        rendered_host = f"[{connect_host}]"
    else:
        rendered_host = connect_host
    return f"http://{rendered_host}:{port}"


def _parse_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _daemon_request_headers(home: Path) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    state = read_json(home / "runtime" / "daemon.json", {})
    if not isinstance(state, dict):
        return headers
    if bool(state.get("auth_enabled")):
        token = str(state.get("auth_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def _daemon_launch_url(home: Path, *, host: str, port: int) -> str:
    state = read_json(home / "runtime" / "daemon.json", {})
    if isinstance(state, dict):
        launch_url = str(state.get("launch_url") or "").strip()
        if launch_url:
            return launch_url
    return _local_ui_url(host, port)


def build_parser() -> argparse.ArgumentParser:
    parser = DeepScientistArgumentParser(
        prog="ds",
        description="DeepScientist Core skeleton",
        allow_abbrev=False,
    )
    parser.add_argument("--home", default=None, help="Override DeepScientist home")
    parser.add_argument("--proxy", default=None, help="Explicit outbound HTTP/WS proxy, for example `http://127.0.0.1:7890`.")
    parser.add_argument("--codex", default=None, help="Override the Codex executable path for this invocation.")

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=DeepScientistArgumentParser,
    )

    subparsers.add_parser("init")

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("goal")
    new_parser.add_argument("--quest-id", default=None)

    subparsers.add_parser("status").add_argument("quest_id", nargs="?")

    pause_parser = subparsers.add_parser("pause")
    pause_parser.add_argument("quest_id")

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("quest_id")

    daemon_parser = subparsers.add_parser("daemon")
    daemon_parser.add_argument("--host", default=None)
    daemon_parser.add_argument("--port", type=int, default=None)
    daemon_parser.add_argument("--auth", default=None)
    daemon_parser.add_argument("--auth-token", default=None)
    daemon_parser.add_argument(
        "--prompt-version",
        default=None,
        help="Use `latest` managed prompts, an official historical prompt version such as `1.5.13`, or an exact backup id from `.codex/prompt_versions/` for this daemon session.",
    )

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("skill_id")
    run_parser.add_argument("--quest-id", required=True)
    run_parser.add_argument("--message", required=True)
    run_parser.add_argument("--model", default=None)
    run_parser.add_argument("--runner", default=None)
    run_parser.add_argument(
        "--prompt-version",
        default=None,
        help="Use `latest` managed prompts, an official historical prompt version such as `1.5.13`, or an exact backup id from `.codex/prompt_versions/` for this one-off run.",
    )

    ui_parser = subparsers.add_parser("ui")
    ui_parser.add_argument("--mode", choices=("web", "tui", "both"), default="web")

    note_parser = subparsers.add_parser("note")
    note_parser.add_argument("quest_id")
    note_parser.add_argument("text")

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("quest_id")
    approve_parser.add_argument("decision_id")
    approve_parser.add_argument("--reason", default="Approved by user.")

    graph_parser = subparsers.add_parser("graph")
    graph_parser.add_argument("quest_id")

    subparsers.add_parser("doctor", aliases=["docker"])

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("quest_id")

    memory_parser = subparsers.add_parser("memory")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_search = memory_subparsers.add_parser("search")
    memory_search.add_argument("query")

    baseline_parser = subparsers.add_parser("baseline")
    baseline_subparsers = baseline_parser.add_subparsers(dest="baseline_command", required=True)
    baseline_subparsers.add_parser("list")
    baseline_attach = baseline_subparsers.add_parser("attach")
    baseline_attach.add_argument("--quest-id", required=True)
    baseline_attach.add_argument("--baseline-id", required=True)
    baseline_attach.add_argument("--variant-id", default=None)

    latex_parser = subparsers.add_parser("latex")
    latex_subparsers = latex_parser.add_subparsers(dest="latex_command", required=True)
    latex_subparsers.add_parser("status")
    latex_subparsers.add_parser("install-runtime")

    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_show = config_subparsers.add_parser("show")
    config_show.add_argument("name", choices=("config", "runners", "connectors", "plugins", "mcp_servers"))
    config_edit = config_subparsers.add_parser("edit")
    config_edit.add_argument("name", choices=("config", "runners", "connectors", "plugins", "mcp_servers"))
    config_subparsers.add_parser("validate")

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("target")

    return parser


def resolve_home(args: argparse.Namespace) -> Path:
    return Path(args.home).expanduser() if args.home else default_home()


def init_command(home: Path) -> int:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    created = config_manager.ensure_files()
    git_info = config_manager.git_readiness()
    installer = SkillInstaller(repo_root(), home)
    synced = installer.sync_global()
    print(json.dumps(
        {
            "home": str(home),
            "created_config_files": [str(path) for path in created],
            "git": git_info,
            "skills": synced,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if git_info["installed"] else 1


def new_command(home: Path, goal: str, quest_id: str | None) -> int:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    payload = _daemon_create_quest(home, goal=goal, quest_id=quest_id)
    if payload is not None:
        print(json.dumps(payload.get("snapshot") or payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok", True) else 1
    installer = SkillInstaller(repo_root(), home)
    quest_service = QuestService(home, skill_installer=installer)
    snapshot = quest_service.create(goal=goal, quest_id=quest_id)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


def status_command(home: Path, quest_id: str | None) -> int:
    quest_service = QuestService(home)
    if quest_id:
        print(json.dumps(quest_service.snapshot(quest_id), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(quest_service.list_quests(), ensure_ascii=False, indent=2))
    return 0


def pause_command(home: Path, quest_id: str) -> int:
    payload = _daemon_control_quest(home, quest_id, action="pause")
    if payload is not None:
        print(json.dumps(payload.get("snapshot") or payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok", True) else 1
    snapshot = QuestService(home).set_status(quest_id, "paused")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


def resume_command(home: Path, quest_id: str) -> int:
    payload = _daemon_control_quest(home, quest_id, action="resume")
    if payload is not None:
        print(json.dumps(payload.get("snapshot") or payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok", True) else 1
    snapshot = QuestService(home).set_status(quest_id, "active")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0

def _daemon_control_quest(home: Path, quest_id: str, *, action: str) -> dict | None:
    config = ConfigManager(home).load_named("config", create_optional=False)
    ui_config = config.get("ui", {})
    url = f"{_local_ui_url(str(ui_config.get('host', '0.0.0.0')), int(ui_config.get('port', 20999)))}/api/quests/{quest_id}/control"
    request = Request(
        url,
        data=json.dumps({"action": action, "source": "cli"}).encode("utf-8"),
        headers=_daemon_request_headers(home),
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, URLError, ValueError):
        return None


def _daemon_create_quest(home: Path, *, goal: str, quest_id: str | None) -> dict | None:
    config = ConfigManager(home).load_named("config", create_optional=False)
    ui_config = config.get("ui", {})
    url = f"{_local_ui_url(str(ui_config.get('host', '0.0.0.0')), int(ui_config.get('port', 20999)))}/api/quests"
    request = Request(
        url,
        data=json.dumps({"goal": goal, "quest_id": quest_id, "source": "cli"}).encode("utf-8"),
        headers=_daemon_request_headers(home),
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, URLError, ValueError):
        return None


def daemon_command(
    home: Path,
    host: str | None,
    port: int | None,
    auth: str | None,
    auth_token: str | None,
    prompt_version: str | None,
) -> int:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    config = config_manager.load_named("config")
    ui_config = config.get("ui", {})
    daemon = DaemonApp(
        home,
        browser_auth_enabled=_parse_optional_bool(auth),
        browser_auth_token=str(auth_token or "").strip() or None,
        prompt_version_selection=str(prompt_version or "").strip() or None,
    )
    daemon.serve(host or ui_config.get("host", "0.0.0.0"), port or ui_config.get("port", 20999))
    return 0


def run_command(
    home: Path,
    quest_id: str,
    skill_id: str,
    message: str,
    model: str | None,
    prompt_version: str | None,
    runner_override: str | None = None,
) -> int:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()
    config = config_manager.load_named("config")
    runners = config_manager.load_runners_config()
    quest_root = home / "quests" / quest_id
    codex_cfg = runners.get("codex", {})
    claude_cfg = runners.get("claude", {})
    opencode_cfg = runners.get("opencode", {})
    logger = JsonlLogger(home / "logs", level=config.get("logging", {}).get("level", "info"))
    prompt_builder = PromptBuilder(
        repo_root(),
        home,
        prompt_version_selection=str(prompt_version or "").strip() or None,
    )
    artifact_service = ArtifactService(home)
    codex_runner = CodexRunner(
        home=home,
        repo_root=repo_root(),
        binary=codex_cfg.get("binary", "codex"),
        logger=logger,
        prompt_builder=prompt_builder,
        artifact_service=artifact_service,
    )
    claude_runner = ClaudeRunner(
        home=home,
        repo_root=repo_root(),
        binary=claude_cfg.get("binary", "claude"),
        logger=logger,
        prompt_builder=prompt_builder,
        artifact_service=artifact_service,
    )
    opencode_runner = OpenCodeRunner(
        home=home,
        repo_root=repo_root(),
        binary=opencode_cfg.get("binary", "opencode"),
        logger=logger,
        prompt_builder=prompt_builder,
        artifact_service=artifact_service,
    )
    register_builtin_runners(
        codex_runner=codex_runner,
        claude_runner=claude_runner,
        opencode_runner=opencode_runner,
    )
    runner_name = str(runner_override or config.get("default_runner", "codex")).strip().lower()
    runner_cfg = runners.get(runner_name, {})
    if runner_cfg.get("enabled") is False:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": f"Runner `{runner_name}` is disabled in `runners.yaml`.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    try:
        selected_runner = get_runner_factory(runner_name)(home=home, config=runner_cfg)
    except KeyError as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    request = RunRequest(
        quest_id=quest_id,
        quest_root=quest_root,
        worktree_root=QuestService(home).active_workspace_root(quest_root),
        run_id=f"run-{skill_id}-{quest_id[-4:]}",
        skill_id=skill_id,
        message=message,
        model=model or runner_cfg.get("model", codex_cfg.get("model", "gpt-5.4")),
        approval_policy=runner_cfg.get("approval_policy", codex_cfg.get("approval_policy", "on-request")),
        sandbox_mode=runner_cfg.get("sandbox_mode", codex_cfg.get("sandbox_mode", "workspace-write")),
    )
    result = selected_runner.run(request)
    if result.output_text:
        QuestService(home).append_message(quest_id, role="assistant", content=result.output_text, source=runner_name)
    print(
        json.dumps(
            {
                "ok": result.ok,
                "runner": runner_name,
                "run_id": result.run_id,
                "model": result.model,
                "exit_code": result.exit_code,
                "history_root": str(result.history_root),
                "run_root": str(result.run_root),
                "output_text": result.output_text,
                "stderr_text": result.stderr_text,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.ok else 1


def launch_ink_tui(home: Path, url: str) -> int:
    node_binary = shutil.which("node")
    if node_binary is None:
        watch_tui(url)
        return 0
    entry = repo_root() / "src" / "tui" / "dist" / "index.js"
    if not entry.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": "Ink TUI bundle is missing. Run `npm --prefix src/tui install && npm --prefix src/tui run build` first.",
                    "entry": str(entry),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    state = read_json(home / "runtime" / "daemon.json", {})
    args = [node_binary, str(entry), "--base-url", url]
    if isinstance(state, dict) and bool(state.get("auth_enabled")):
        token = str(state.get("auth_token") or "").strip()
        if token:
            args.extend(["--auth-token", token])
    return subprocess.call(args)


def ui_command(home: Path, mode: str) -> int:
    config = ConfigManager(home).load_named("config", create_optional=False)
    host = config.get("ui", {}).get("host", "0.0.0.0")
    port = config.get("ui", {}).get("port", 20999)
    base_url = _local_ui_url(str(host), int(port))
    launch_url = _daemon_launch_url(home, host=str(host), port=int(port))
    if mode in {"web", "both"}:
        webbrowser.open(launch_url)
        print(f"Opened {launch_url}")
    if mode in {"tui", "both"}:
        return launch_ink_tui(home, base_url)
    return 0


def note_command(home: Path, quest_id: str, text: str) -> int:
    quest_service = QuestService(home)
    message = quest_service.append_message(quest_id, role="user", content=text, source="cli")
    print(json.dumps(message, ensure_ascii=False, indent=2))
    return 0


def approve_command(home: Path, quest_id: str, decision_id: str, reason: str) -> int:
    quest_root = home / "quests" / quest_id
    result = ArtifactService(home).record(
        quest_root,
        {
            "kind": "approval",
            "decision_id": decision_id,
            "reason": reason,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def graph_command(home: Path, quest_id: str) -> int:
    from .gitops import export_git_graph

    quest_root = home / "quests" / quest_id
    payload = export_git_graph(quest_root, ensure_dir(quest_root / "artifacts" / "graphs"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def doctor_command(home: Path) -> int:
    report = run_doctor(home, repo_root=repo_root())
    sys.stdout.write(render_doctor_report(report))
    return 0 if report.get("ok") else 1


def push_command(home: Path, quest_id: str) -> int:
    from .shared import run_command

    quest_root = home / "quests" / quest_id
    result = run_command(["git", "push"], cwd=quest_root, check=False)
    print(
        json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.returncode == 0 else 1


def memory_search_command(home: Path, query: str) -> int:
    memory_service = MemoryService(home)
    print(json.dumps(memory_service.search(query, scope="global"), ensure_ascii=False, indent=2))
    return 0


def baseline_list_command(home: Path) -> int:
    registry = BaselineRegistry(home)
    print(json.dumps(registry.list_entries(), ensure_ascii=False, indent=2))
    return 0


def baseline_attach_command(home: Path, quest_id: str, baseline_id: str, variant_id: str | None) -> int:
    result = ArtifactService(home).attach_baseline(home / "quests" / quest_id, baseline_id, variant_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def latex_status_command(home: Path) -> int:
    ensure_home_layout(home)
    payload = RuntimeToolService(home).status("tinytex")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def latex_install_runtime_command(home: Path) -> int:
    ensure_home_layout(home)
    payload = RuntimeToolService(home).install("tinytex")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def config_show_command(home: Path, name: str) -> int:
    manager = ConfigManager(home)
    text = manager.load_named_text(name, create_optional=True)
    sys.stdout.write(text)
    return 0


def config_edit_command(home: Path, name: str) -> int:
    manager = ConfigManager(home)
    path = manager.path_for(name)
    if name in {"plugins", "mcp_servers"} and not path.exists():
        manager.ensure_optional_file(name)
    editor = os.environ.get("EDITOR")
    if editor:
        import subprocess

        return subprocess.call([editor, str(path)])
    print(str(path))
    return 0


def config_validate_command(home: Path) -> int:
    manager = ConfigManager(home)
    print(json.dumps(manager.validate_all(), ensure_ascii=False, indent=2))
    return 0


def migrate_command(home: Path, target: str) -> int:
    try:
        payload = migrate_deepscientist_root(home, Path(target))
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "source": str(home.expanduser().resolve()),
                    "target": str(Path(target).expanduser().resolve()),
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.codex:
        os.environ["DEEPSCIENTIST_CODEX_BINARY"] = str(args.codex)
    configure_runtime_proxy(args.proxy)
    home = resolve_home(args)

    if args.command == "init":
        return init_command(home)
    if args.command == "new":
        return new_command(home, args.goal, args.quest_id)
    if args.command == "status":
        return status_command(home, args.quest_id)
    if args.command == "pause":
        return pause_command(home, args.quest_id)
    if args.command == "resume":
        return resume_command(home, args.quest_id)
    if args.command == "daemon":
        return daemon_command(home, args.host, args.port, args.auth, args.auth_token, args.prompt_version)
    if args.command == "run":
        return run_command(home, args.quest_id, args.skill_id, args.message, args.model, args.prompt_version, args.runner)
    if args.command == "ui":
        return ui_command(home, args.mode)
    if args.command == "note":
        return note_command(home, args.quest_id, args.text)
    if args.command == "approve":
        return approve_command(home, args.quest_id, args.decision_id, args.reason)
    if args.command == "graph":
        return graph_command(home, args.quest_id)
    if args.command in {"doctor", "docker"}:
        return doctor_command(home)
    if args.command == "push":
        return push_command(home, args.quest_id)
    if args.command == "memory" and args.memory_command == "search":
        return memory_search_command(home, args.query)
    if args.command == "baseline" and args.baseline_command == "list":
        return baseline_list_command(home)
    if args.command == "baseline" and args.baseline_command == "attach":
        return baseline_attach_command(home, args.quest_id, args.baseline_id, args.variant_id)
    if args.command == "latex" and args.latex_command == "status":
        return latex_status_command(home)
    if args.command == "latex" and args.latex_command == "install-runtime":
        return latex_install_runtime_command(home)
    if args.command == "config" and args.config_command == "show":
        return config_show_command(home, args.name)
    if args.command == "config" and args.config_command == "edit":
        return config_edit_command(home, args.name)
    if args.command == "config" and args.config_command == "validate":
        return config_validate_command(home)
    if args.command == "migrate":
        return migrate_command(home, args.target)
    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
