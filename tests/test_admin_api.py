from __future__ import annotations

from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout
from deepscientist.shared import append_jsonl, utc_now


def _build_app(temp_home: Path) -> DaemonApp:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    app = DaemonApp(temp_home, browser_auth_enabled=False)
    app._start_background_connectors = lambda: None  # type: ignore[method-assign]
    app._stop_background_connectors = lambda: None  # type: ignore[method-assign]
    app._start_terminal_attach_server = lambda host, port: None  # type: ignore[method-assign]
    app._stop_terminal_attach_server = lambda: None  # type: ignore[method-assign]
    return app


def _seed_quest(app: DaemonApp, quest_id: str = "admin-api-quest") -> str:
    quest = app.quest_service.create(
        "Admin API quest",
        quest_id=quest_id,
        startup_contract={"workspace_mode": "copilot"},
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(app.home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-admin-api"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-admin-api",
        summary="Admin API baseline.",
        metrics_summary={"acc": 0.8},
        primary_metric={"metric_id": "acc", "value": 0.8},
        metric_contract={"primary_metric_id": "acc", "metrics": [{"metric_id": "acc", "direction": "higher"}]},
    )
    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Admin API idea",
        problem="Need admin summary coverage.",
        hypothesis="Quest summary should surface through admin APIs.",
        mechanism="Seed one line.",
        decision_reason="Test admin summary.",
        next_target="experiment",
    )
    return quest["quest_id"]


def test_admin_overview_and_runtime_surfaces_return_payloads(temp_home: Path) -> None:
    app = _build_app(temp_home)
    quest_id = _seed_quest(app)

    overview = app.handlers.admin_overview()
    assert overview["ok"] is True
    assert overview["totals"]["quests_total"] >= 1
    assert overview["latest_failure_scanned"] is True
    assert "quest_insights" in overview
    assert "connector_health" in overview
    assert "task_health" in overview

    quests = app.handlers.admin_quests("/api/admin/quests?limit=20")
    assert quests["ok"] is True
    assert any(item["quest_id"] == quest_id for item in quests["items"])

    summary = app.handlers.admin_quest_summary(quest_id)
    assert summary["ok"] is True
    assert summary["snapshot"]["quest_id"] == quest_id

    runtime = app.handlers.admin_runtime_sessions("/api/admin/runtime/sessions?limit=20")
    assert runtime["ok"] is True
    assert "items" in runtime

    charts_catalog = app.handlers.admin_chart_catalog()
    assert charts_catalog["ok"] is True
    assert any(item["chart_id"] == "runtime.active_quests" for item in charts_catalog["items"])
    assert any(item["chart_id"] == "tools.by_tool" for item in charts_catalog["items"])

    charts_query = app.handlers.admin_chart_query(
        {
            "items": [
                {"chart_id": "runtime.active_quests", "range": "24h"},
                {"chart_id": "quests.by_status"},
            ]
        }
    )
    assert not isinstance(charts_query, tuple)
    assert charts_query["ok"] is True
    assert len(charts_query["items"]) == 2

    quest_root = Path(app.quest_service._quest_root(quest_id))
    append_jsonl(
        quest_root / ".ds" / "events.jsonl",
        {
            "event_id": "evt-tool-call-1",
            "type": "runner.tool_call",
            "quest_id": quest_id,
            "run_id": "run-tool-1",
            "tool_call_id": "tool-1",
            "tool_name": "artifact.search_docs",
            "mcp_server": "artifact",
            "mcp_tool": "search_docs",
            "status": "calling",
            "created_at": utc_now(),
        },
    )
    append_jsonl(
        quest_root / ".ds" / "events.jsonl",
        {
            "event_id": "evt-tool-result-1",
            "type": "runner.tool_result",
            "quest_id": quest_id,
            "run_id": "run-tool-1",
            "tool_call_id": "tool-1",
            "tool_name": "artifact.search_docs",
            "mcp_server": "artifact",
            "mcp_tool": "search_docs",
            "status": "completed",
            "created_at": utc_now(),
        },
    )

    tool_query = app.handlers.admin_chart_query(
        {
            "items": [
                {"chart_id": "tools.calls_total", "range": "24h", "quest_id": quest_id},
                {"chart_id": "tools.by_tool", "range": "24h", "quest_id": quest_id, "limit": 5},
                {"chart_id": "quest.activity.hourly_7d", "range": "7d", "quest_id": quest_id, "step_seconds": 3600},
                {"chart_id": "quest.tools.by_tool", "range": "24h", "quest_id": quest_id, "limit": 5},
            ]
        }
    )
    assert not isinstance(tool_query, tuple)
    assert tool_query["ok"] is True
    assert len(tool_query["items"]) == 4
    assert tool_query["items"][0]["chart_id"] == "tools.calls_total"
    assert tool_query["items"][1]["categories"][0]["key"] == "artifact.search_docs"
    assert tool_query["items"][2]["chart_id"] == "quest.activity.hourly_7d"
    assert tool_query["items"][3]["chart_id"] == "quest.tools.by_tool"

    stats = app.handlers.admin_stats_summary()
    assert stats["ok"] is True
    assert stats["totals"]["quests"] >= 1
    assert "decision_backlog_buckets" in stats
    assert "message_backlog_buckets" in stats
    assert "activity_timeline_7d" in stats
    assert "active_watchlist" in stats


def test_admin_logs_and_search_surfaces_are_bounded(temp_home: Path) -> None:
    app = _build_app(temp_home)
    quest_id = _seed_quest(app)
    app.logger.log("info", "admin.api.test", quest_id=quest_id)

    sources = app.handlers.admin_log_sources()
    assert sources["ok"] is True
    assert sources["items"]
    assert sources["items"][0]["source"] == "system_backend"

    app.logger.log("info", "admin.api.test.first", quest_id=quest_id)
    app.logger.log("info", "admin.api.test.second", quest_id=quest_id)
    tail = app.handlers.admin_log_tail("/api/admin/logs/tail?source=system_backend&line_count=2")
    assert not isinstance(tail, tuple)
    assert tail["ok"] is True
    assert isinstance(tail["lines"], list)
    assert "admin.api.test.second" in tail["lines"][0]
    assert "admin.api.test.first" in tail["lines"][1]

    search = app.handlers.admin_search(f"/api/admin/search?q={quest_id}&limit=20")
    assert not isinstance(search, tuple)
    assert search["ok"] is True
    assert any(item["quest_id"] == quest_id for item in search["items"])

    errors = app.handlers.admin_errors("/api/admin/errors?limit=20")
    assert errors["ok"] is True
    assert "daemon_errors" in errors

    issue = app.handlers.admin_issue_draft(
        {
            "summary": "Admin API test issue",
            "user_notes": "Reproduced through admin API test.",
            "include_doctor": False,
            "include_logs": True,
        }
    )
    assert issue["ok"] is True
    assert "body_markdown" in issue
    assert "issue_url_base" in issue
    assert "github.com/ResearAI/DeepScientist/issues/new" in issue["issue_url_base"]
    assert "## Recommended Fixes / Workarounds" in issue["body_markdown"]
    assert "## Detected Problems" in issue["body_markdown"]
    assert "Host:" in issue["body_markdown"] or "Hardware summary unavailable." in issue["body_markdown"]
    assert "## System Quirks" not in issue["body_markdown"]

    empty_quirks_issue = app.handlers.admin_issue_draft(
        {
            "summary": "Admin API test issue with empty quirks",
            "include_doctor": False,
            "include_logs": False,
            "include_system_quirks": True,
        }
    )
    assert "## System Quirks" in empty_quirks_issue["body_markdown"]
    assert "_No system quirks have been recorded yet._" in empty_quirks_issue["body_markdown"]
    assert "Append-only durable file" not in empty_quirks_issue["body_markdown"]

    (temp_home / "system_quirks.md").write_text(
        "# System Quirks\n\n"
        "## TUI debug render mismatch\n\n"
        "- Expected behavior: TUI output matches the web surface.\n"
        "- Actual behavior: A bounded render differs from the web surface.\n"
        "- Status: confirmed\n",
        encoding="utf-8",
    )
    issue_with_quirks = app.handlers.admin_issue_draft(
        {
            "summary": "Admin API test issue with quirks",
            "include_doctor": False,
            "include_logs": False,
            "include_system_quirks": True,
        }
    )
    assert "## System Quirks" in issue_with_quirks["body_markdown"]
    assert "TUI debug render mismatch" in issue_with_quirks["body_markdown"]
    assert issue_with_quirks["body_markdown"].index("## System Quirks") < issue_with_quirks["body_markdown"].index("## Recent Runtime Failures")


def test_admin_controllers_and_repairs_support_basic_lifecycle(temp_home: Path) -> None:
    app = _build_app(temp_home)

    controllers = app.handlers.admin_controllers()
    assert controllers["ok"] is True
    assert any(item["controller_id"] == "stale_running_quest_guard" for item in controllers["items"])

    toggle = app.handlers.admin_controller_toggle("stale_running_quest_guard", {"enabled": True})
    assert not isinstance(toggle, tuple)
    assert toggle["ok"] is True
    assert toggle["controller"]["enabled"] is True

    run = app.handlers.admin_controller_run("stale_running_quest_guard", {})
    assert not isinstance(run, tuple)
    assert run["ok"] is True
    assert "result" in run

    created = app.handlers.admin_repair_create(
        {
            "request_text": "Inspect the local runtime from admin.",
            "source_page": "/admin/repairs",
            "scope": "system",
        }
    )
    assert not isinstance(created, tuple)
    assert created["ok"] is True
    repair_id = created["repair"]["repair_id"]
    assert str(created["repair"]["ops_quest_id"]).startswith("S-")

    detail = app.handlers.admin_repair_detail(repair_id)
    assert not isinstance(detail, tuple)
    assert detail["repair"]["repair_id"] == repair_id
    report_dir = Path(app.quest_service._quest_root(detail["repair"]["ops_quest_id"])) / "artifacts" / "reports" / "admin"
    assert (report_dir / f"{repair_id}.md").exists()
    assert (report_dir / f"{repair_id}.json").exists()

    listing = app.handlers.admin_repairs("/api/admin/repairs?limit=20")
    assert listing["ok"] is True
    assert any(item["repair_id"] == repair_id for item in listing["items"])

    closed = app.handlers.admin_repair_close(repair_id, {})
    assert not isinstance(closed, tuple)
    assert closed["repair"]["status"] == "closed"
    assert "closed" in (report_dir / f"{repair_id}.md").read_text(encoding="utf-8")


def test_system_aliases_cover_settings_control_surface(temp_home: Path) -> None:
    app = _build_app(temp_home)
    quest_id = _seed_quest(app)
    app.logger.log("info", "system.alias.test", quest_id=quest_id)

    overview = app.handlers.system_overview()
    assert overview["ok"] is True

    quests = app.handlers.system_quests("/api/system/quests?limit=20")
    assert quests["ok"] is True
    assert any(item["quest_id"] == quest_id for item in quests["items"])

    summary = app.handlers.system_quest_summary(quest_id)
    assert not isinstance(summary, tuple)
    assert summary["snapshot"]["quest_id"] == quest_id

    runtime = app.handlers.system_runtime_sessions("/api/system/runtime/sessions?limit=20")
    assert runtime["ok"] is True

    sources = app.handlers.system_log_sources()
    assert sources["ok"] is True
    assert sources["items"]
    assert sources["items"][0]["source"] == "system_backend"

    tail = app.handlers.system_log_tail("/api/system/logs/tail?source=system_backend&line_count=20")
    assert not isinstance(tail, tuple)
    assert tail["ok"] is True

    failures = app.handlers.system_failures("/api/system/failures?limit=20")
    assert failures["ok"] is True

    errors = app.handlers.system_errors("/api/system/errors?limit=20")
    assert errors["ok"] is True

    runtime_tools = app.handlers.system_runtime_tools()
    assert runtime_tools["ok"] is True

    doctor = app.handlers.system_doctor()
    assert doctor["ok"] is True

    tasks = app.handlers.system_tasks("/api/system/tasks?limit=20")
    assert tasks["ok"] is True

    stats = app.handlers.system_stats_summary()
    assert stats["ok"] is True

    catalog = app.handlers.system_chart_catalog()
    assert catalog["ok"] is True

    query_payload = app.handlers.system_chart_query({"items": [{"chart_id": "runtime.pending_decisions_total", "range": "24h"}]})
    assert not isinstance(query_payload, tuple)
    assert query_payload["ok"] is True

    search = app.handlers.system_search(f"/api/system/search?q={quest_id}&limit=20")
    assert not isinstance(search, tuple)
    assert search["ok"] is True
    assert any(item["quest_id"] == quest_id for item in search["items"])

    issue = app.handlers.system_issue_draft(
        {
            "summary": "System alias issue",
            "user_notes": "Created from settings/system alias coverage.",
            "include_doctor": False,
            "include_logs": True,
        }
    )
    assert issue["ok"] is True
    assert "## Recommended Fixes / Workarounds" in issue["body_markdown"]

    controllers = app.handlers.system_controllers()
    assert controllers["ok"] is True

    toggle = app.handlers.system_controller_toggle("stale_running_quest_guard", {"enabled": True})
    assert not isinstance(toggle, tuple)
    assert toggle["controller"]["enabled"] is True

    run = app.handlers.system_controller_run("stale_running_quest_guard", {})
    assert not isinstance(run, tuple)
    assert run["ok"] is True

    created = app.handlers.system_repair_create(
        {
            "request_text": "Inspect the local runtime from settings.",
            "source_page": "/settings/repairs",
            "scope": "system",
        }
    )
    assert not isinstance(created, tuple)
    assert created["ok"] is True
    repair_id = created["repair"]["repair_id"]

    detail = app.handlers.system_repair_detail(repair_id)
    assert not isinstance(detail, tuple)
    assert detail["repair"]["repair_id"] == repair_id

    listing = app.handlers.system_repairs("/api/system/repairs?limit=20")
    assert listing["ok"] is True
    assert any(item["repair_id"] == repair_id for item in listing["items"])

    closed = app.handlers.system_repair_close(repair_id, {})
    assert not isinstance(closed, tuple)
    assert closed["repair"]["status"] == "closed"


def test_admin_system_hardware_surfaces_and_gpu_selection_persist(temp_home: Path, monkeypatch) -> None:
    app = _build_app(temp_home)

    monkeypatch.setattr(
        "deepscientist.admin.service.collect_system_hardware",
        lambda _home: {
            "generated_at": None,
            "host": {"hostname": "admin-host", "platform": "Linux-test", "machine": "x86_64"},
            "cpu": {"model": "AMD EPYC Test", "logical_cores": 64, "physical_cores": 32},
            "memory": {"total_bytes": 256 * 1024**3, "available_bytes": 200 * 1024**3, "total_gb": 256.0, "available_gb": 200.0},
            "disks": [{"mount": "/", "total_bytes": 2 * 1024**4, "free_bytes": int(1.5 * 1024**4), "total_gb": 2048.0, "free_gb": 1536.0}],
            "gpus": [
                {"gpu_id": "0", "vendor": "nvidia", "name": "NVIDIA A100", "memory_total_gb": 80.0},
                {"gpu_id": "1", "vendor": "nvidia", "name": "NVIDIA A100", "memory_total_gb": 80.0},
            ],
            "gpu_count": 2,
        },
    )

    hardware = app.handlers.admin_system_hardware()
    assert hardware["ok"] is True
    assert hardware["system"]["cpu"]["model"] == "AMD EPYC Test"
    assert hardware["preferences"]["gpu_selection_mode"] == "all"
    assert hardware["preferences"]["effective_gpu_ids"] == ["0", "1"]
    assert hardware["memory_preferences"]["read_visibility_mode"] == "independent"
    assert hardware["latest_sample"] is not None
    assert hardware["recent_stats"]["sample_count"] >= 1
    assert isinstance(hardware["recent_stats"]["series"], list)
    assert hardware["recent_stats"]["series"]
    assert "cpu_usage_percent" in hardware["recent_stats"]["series"][-1]
    assert "memory_usage_percent" in hardware["recent_stats"]["series"][-1]
    assert "root_disk_usage_percent" in hardware["recent_stats"]["series"][-1]
    assert Path(str(hardware["recent_stats"]["log_path"])).exists()
    assert "Selected GPUs: 0,1" in hardware["prompt_hardware_summary"]

    system_hardware = app.handlers.system_hardware()
    assert system_hardware["ok"] is True
    assert system_hardware["preferences"]["effective_gpu_ids"] == ["0", "1"]

    updated = app.handlers.system_hardware_update(
        {
            "gpu_selection_mode": "selected",
            "selected_gpu_ids": ["1"],
            "include_system_hardware_in_prompt": True,
            "memory_read_visibility_mode": "shared_across_quests",
        }
    )
    assert not isinstance(updated, tuple)
    assert updated["preferences"]["gpu_selection_mode"] == "selected"
    assert updated["preferences"]["selected_gpu_ids"] == ["1"]
    assert updated["preferences"]["effective_gpu_ids"] == ["1"]
    assert updated["preferences"]["cuda_visible_devices"] == "1"
    assert updated["memory_preferences"]["read_visibility_mode"] == "shared_across_quests"

    config = app.config_manager.load_runtime_config()
    hardware_config = config.get("hardware") if isinstance(config.get("hardware"), dict) else {}
    memory_config = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    assert hardware_config["gpu_selection_mode"] == "selected"
    assert hardware_config["selected_gpu_ids"] == ["1"]
    assert memory_config["read_visibility_mode"] == "shared_across_quests"
