from __future__ import annotations

import json
import shutil
from pathlib import Path

import deepscientist.home as home_module
from deepscientist.config import ConfigManager
from deepscientist.cli import _local_ui_url, init_command, pause_command
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.mcp.context import McpContext
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl, ensure_dir, read_yaml, write_json, write_text, write_yaml
from deepscientist.skills import SkillInstaller


def test_init_creates_required_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    created = manager.ensure_files()
    assert created
    assert (temp_home / "runtime" / "python").exists()
    assert (temp_home / "runtime" / "uv-cache").exists()
    assert not (temp_home / "runtime" / "venv").exists()
    assert (temp_home / "framework_quirks.md").exists()
    assert (temp_home / "system_quirks.md").exists()
    assert (temp_home / "config" / "config.yaml").exists()
    assert (temp_home / "config" / "runners.yaml").exists()
    assert (temp_home / "config" / "connectors.yaml").exists()
    config = manager.load_named("config")
    runners = manager.load_named_normalized("runners")
    assert config["ui"]["host"] == "0.0.0.0"
    assert config["ui"]["port"] == 20999
    assert config["ui"]["default_mode"] == "web"
    assert config["ui"]["auto_open_browser"] is True
    assert config["bootstrap"]["codex_ready"] is False
    assert config["bootstrap"]["codex_last_checked_at"] is None
    assert config["bootstrap"]["locale_source"] == "default"
    assert config["bootstrap"]["locale_initialized_from_browser"] is False
    assert config["bootstrap"]["locale_initialized_at"] is None
    assert config["bootstrap"]["locale_initialized_browser_locale"] is None
    assert config["connectors"]["system_enabled"]["qq"] is True
    assert config["connectors"]["system_enabled"]["weixin"] is True
    assert config["connectors"]["system_enabled"]["telegram"] is True
    assert config["connectors"]["system_enabled"]["discord"] is False
    assert config["connectors"]["system_enabled"]["slack"] is False
    assert config["connectors"]["system_enabled"]["feishu"] is True
    assert config["connectors"]["system_enabled"]["whatsapp"] is True
    assert config["connectors"]["system_enabled"]["lingzhu"] is True
    assert runners["codex"]["profile"] == ""
    assert runners["codex"]["model"] == "inherit"
    assert runners["codex"]["model_reasoning_effort"] == "xhigh"
    assert runners["codex"]["retry_max_attempts"] == 7
    assert runners["codex"]["retry_initial_backoff_sec"] == 10.0
    assert runners["codex"]["retry_backoff_multiplier"] == 6.0
    assert runners["codex"]["retry_max_backoff_sec"] == 1800.0


def test_legacy_codex_retry_profile_is_upgraded_when_loading_normalized_runners(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    runners_path = manager.path_for("runners")
    runners_path.write_text(
        "\n".join(
            [
                "codex:",
                "  enabled: true",
                "  binary: codex",
                "  retry_on_failure: true",
                "  retry_max_attempts: 5",
                "  retry_initial_backoff_sec: 1",
                "  retry_backoff_multiplier: 2",
                "  retry_max_backoff_sec: 8",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runners = manager.load_named_normalized("runners")

    assert runners["codex"]["retry_max_attempts"] == 7
    assert runners["codex"]["retry_initial_backoff_sec"] == 10.0
    assert runners["codex"]["retry_backoff_multiplier"] == 6.0
    assert runners["codex"]["retry_max_backoff_sec"] == 1800.0


def test_repo_root_falls_back_to_launcher_path_when_env_repo_root_is_missing(tmp_path: Path, monkeypatch) -> None:
    fake_repo_root = tmp_path / 'cli-runtime'
    (fake_repo_root / 'src' / 'deepscientist').mkdir(parents=True)
    (fake_repo_root / 'src' / 'skills').mkdir(parents=True)
    (fake_repo_root / 'pyproject.toml').write_text('[build-system]\n', encoding='utf-8')
    (fake_repo_root / 'bin').mkdir(parents=True)
    launcher_path = fake_repo_root / 'bin' / 'ds.js'
    launcher_path.write_text('// launcher\n', encoding='utf-8')

    packaged_module = tmp_path / 'runtime' / 'python-env' / 'lib' / 'python3.13' / 'site-packages' / 'deepscientist' / 'home.py'
    packaged_module.parent.mkdir(parents=True)
    packaged_module.write_text('# placeholder\n', encoding='utf-8')

    monkeypatch.delenv('DEEPSCIENTIST_REPO_ROOT', raising=False)
    monkeypatch.setenv('DEEPSCIENTIST_LAUNCHER_PATH', str(launcher_path))
    monkeypatch.setattr(home_module, '__file__', str(packaged_module))
    monkeypatch.chdir(tmp_path)

    assert repo_root() == fake_repo_root.resolve()


def test_new_creates_standalone_git_repo(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create("test quest")
    quest_root = Path(snapshot["quest_root"])
    assert (quest_root / ".git").exists()
    assert (quest_root / ".gitignore").exists()
    assert (quest_root / "quest.yaml").exists()
    assert (quest_root / "tmp").exists()
    assert (quest_root / "userfiles").exists()
    assert (quest_root / ".codex" / "prompts" / "system.md").exists()
    assert (quest_root / ".codex" / "prompts" / "connectors" / "qq.md").exists()
    assert (quest_root / ".codex" / "skills").exists()
    assert (quest_root / ".claude" / "agents").exists()
    assert (quest_root / ".claude" / "agents" / "deepscientist-decision.md").exists()
    assert (quest_root / ".kimi" / "skills").exists()
    assert (quest_root / ".kimi" / "skills" / "deepscientist-decision" / "SKILL.md").exists()
    assert (quest_root / ".codex" / "skills" / "deepscientist-finalize" / "SKILL.md").exists()
    assert snapshot["quest_id"] == "001"
    assert snapshot["runner"] == "codex"
    assert "paths" in snapshot
    assert snapshot["summary"]["status_line"] == "Quest created. Waiting for baseline setup or reuse."


def test_copilot_quest_defaults_to_scout_anchor(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))

    snapshot = service.create("copilot quest", startup_contract={"workspace_mode": "copilot"})
    quest_root = Path(snapshot["quest_root"])
    quest_yaml = read_yaml(quest_root / "quest.yaml", {})

    assert quest_yaml["active_anchor"] == "scout"
    assert snapshot["active_anchor"] == "scout"


def test_legacy_copilot_baseline_anchor_is_normalized_to_scout_when_no_baseline_context_exists(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home)

    snapshot = service.create("legacy copilot quest", startup_contract={"workspace_mode": "copilot"})
    quest_root = Path(snapshot["quest_root"])
    write_yaml(
        quest_root / "quest.yaml",
        {
            **read_yaml(quest_root / "quest.yaml", {}),
            "active_anchor": "baseline",
            "requested_baseline_ref": None,
            "confirmed_baseline_ref": None,
        },
    )

    normalized = service.read_quest_yaml(quest_root)

    assert normalized["active_anchor"] == "scout"


def test_sync_quest_prompts_backs_up_previous_active_tree(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    installer = SkillInstaller(repo_root(), temp_home)
    snapshot = QuestService(temp_home, skill_installer=installer).create("prompt backup quest")
    quest_root = Path(snapshot["quest_root"])

    prompt_copy = quest_root / ".codex" / "prompts" / "system.md"
    original = prompt_copy.read_text(encoding="utf-8")
    prompt_copy.write_text(original + "\nPROMPT_BACKUP_SENTINEL\n", encoding="utf-8")

    result = installer.sync_quest_prompts(quest_root, installed_version="9.9.9")

    assert result["updated"] is True
    backup_id = str(result["backup_id"] or "")
    assert backup_id
    assert "PROMPT_BACKUP_SENTINEL" not in prompt_copy.read_text(encoding="utf-8")
    backup_prompt = quest_root / ".codex" / "prompt_versions" / backup_id / "system.md"
    assert "PROMPT_BACKUP_SENTINEL" in backup_prompt.read_text(encoding="utf-8")
    index_payload = json.loads((quest_root / ".codex" / "prompt_versions" / "index.json").read_text(encoding="utf-8"))
    versions = index_payload.get("versions") if isinstance(index_payload.get("versions"), list) else []
    assert any(str(item.get("backup_id") or "") == backup_id for item in versions if isinstance(item, dict))


def test_sync_quest_prompts_recovers_from_existing_backup_directory_race(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    installer = SkillInstaller(repo_root(), temp_home)
    snapshot = QuestService(temp_home, skill_installer=installer).create("prompt backup retry quest")
    quest_root = Path(snapshot["quest_root"])

    prompt_copy = quest_root / ".codex" / "prompts" / "system.md"
    prompt_copy.write_text(prompt_copy.read_text(encoding="utf-8") + "\nPROMPT_BACKUP_RETRY_SENTINEL\n", encoding="utf-8")

    versions_root = quest_root / ".codex" / "prompt_versions"
    (versions_root / "conflict").mkdir(parents=True, exist_ok=True)
    backup_ids = iter(["conflict", "resolved"])

    monkeypatch.setattr(
        installer,
        "_unique_prompt_backup_id",
        lambda *_args, **_kwargs: next(backup_ids),
    )

    result = installer.sync_quest_prompts(quest_root, installed_version="9.9.9")

    assert result["updated"] is True
    assert result["backup_id"] == "resolved"
    backup_prompt = quest_root / ".codex" / "prompt_versions" / "resolved" / "system.md"
    assert "PROMPT_BACKUP_RETRY_SENTINEL" in backup_prompt.read_text(encoding="utf-8")


def test_auto_generated_quest_ids_are_sequential(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    first = service.create("first quest")
    second = service.create("second quest")
    third = service.create("third quest")

    assert [first["quest_id"], second["quest_id"], third["quest_id"]] == ["001", "002", "003"]


def test_system_prefixed_quest_ids_are_preserved_and_consume_numeric_sequence(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    settings_snapshot = service.create(
        "settings quest",
        quest_id="S-001",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "admin_ops",
        },
    )
    bench_snapshot = service.create(
        "benchstore quest",
        quest_id="B-002",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {"source": "benchstore"},
        },
    )
    research_snapshot = service.create(
        "research quest",
        startup_contract={"workspace_mode": "autonomous"},
    )

    assert settings_snapshot["quest_id"] == "S-001"
    assert bench_snapshot["quest_id"] == "B-002"
    assert research_snapshot["quest_id"] == "003"


def test_summary_compact_marks_system_quests_hidden_from_projects(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    settings_snapshot = service.create(
        "settings quest",
        quest_id="S-001",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "admin_ops",
        },
    )
    bench_snapshot = service.create(
        "benchstore quest",
        quest_id="B-002",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "benchstore_context": {"entry_id": "bench.sample"},
        },
    )
    research_snapshot = service.create(
        "research quest",
        startup_contract={"workspace_mode": "copilot"},
    )

    settings_summary = service.summary_compact(settings_snapshot["quest_id"])
    bench_summary = service.summary_compact(bench_snapshot["quest_id"])
    research_summary = service.summary_compact(research_snapshot["quest_id"])

    assert settings_summary["quest_class"] == "settings"
    assert settings_summary["listed_in_projects"] is False
    assert bench_summary["quest_class"] == "benchstore"
    assert bench_summary["listed_in_projects"] is False
    assert research_summary["quest_class"] == "research"
    assert research_summary["listed_in_projects"] is True


def test_events_slice_uses_placeholder_for_oversized_event_lines(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home)
    snapshot = service.create("oversized event slice quest")
    quest_root = Path(snapshot["quest_root"])
    events_path = quest_root / ".ds" / "events.jsonl"
    huge_output = "x" * (9 * 1024 * 1024)
    oversized_event = {
        "event_id": "evt-huge",
        "type": "runner.tool_result",
        "quest_id": snapshot["quest_id"],
        "run_id": "run-huge",
        "tool_name": "bash_exec.bash_exec",
        "output": huge_output,
    }
    small_event = {
        "event_id": "evt-small",
        "type": "runner.agent_message",
        "quest_id": snapshot["quest_id"],
        "text": "small tail event",
    }
    events_path.write_text(
        json.dumps(oversized_event, ensure_ascii=False) + "\n" + json.dumps(small_event, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    payload = service.events(snapshot["quest_id"], tail=True, limit=2)

    assert payload["events"][0]["type"] == "runner.tool_result"
    assert payload["events"][0]["oversized_event"] is True
    assert payload["events"][0]["oversized_bytes"] > 8 * 1024 * 1024
    assert payload["events"][1]["type"] == "runner.agent_message"


def test_deleted_quest_ids_are_not_reused(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    first = service.create("first quest")
    second = service.create("second quest")
    third = service.create("third quest")
    shutil.rmtree(Path(second["quest_root"]))

    fourth = service.create("fourth quest")

    assert [first["quest_id"], second["quest_id"], third["quest_id"], fourth["quest_id"]] == ["001", "002", "003", "004"]


def test_events_tail_preserves_cursor_order_after_file_grows(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    snapshot = service.create("tail cursor quest")
    quest_id = snapshot["quest_id"]
    events_path = Path(snapshot["quest_root"]) / ".ds" / "events.jsonl"

    for index in range(1, 11):
        append_jsonl(
            events_path,
            {
                "event_id": f"evt-{index}",
                "type": "conversation.message",
                "quest_id": quest_id,
                "role": "assistant",
                "content": f"message-{index}",
            },
        )

    first_tail = service.events(quest_id, tail=True, limit=3)
    assert [item["cursor"] for item in first_tail["events"]] == [8, 9, 10]
    assert [item["content"] for item in first_tail["events"]] == [
        "message-8",
        "message-9",
        "message-10",
    ]

    append_jsonl(
        events_path,
        {
            "event_id": "evt-11",
            "type": "conversation.message",
            "quest_id": quest_id,
            "role": "assistant",
            "content": "message-11",
        },
    )

    second_tail = service.events(quest_id, tail=True, limit=2)
    assert [item["cursor"] for item in second_tail["events"]] == [10, 11]
    assert [item["content"] for item in second_tail["events"]] == [
        "message-10",
        "message-11",
    ]


def test_snapshot_exposes_paper_contract_and_analysis_inventory(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    snapshot = service.create("paper analysis snapshot quest")
    quest_root = Path(snapshot["quest_root"])
    idea_root = ensure_dir(quest_root / "artifacts" / "ideas")
    run_root = ensure_dir(quest_root / "artifacts" / "runs")

    write_json(
        idea_root / "idea-001.json",
        {
            "kind": "idea",
            "idea_id": "idea-001",
            "branch": "idea/001-idea-001",
            "parent_branch": "main",
            "updated_at": "2026-03-28T00:00:00Z",
            "details": {
                "title": "Audit-ready idea",
                "lineage_intent": "continue_line",
            },
            "paths": {
                "idea_md": str(quest_root / "memory" / "ideas" / "idea-001" / "idea.md"),
                "idea_draft_md": str(quest_root / "memory" / "ideas" / "idea-001" / "draft.md"),
            },
        },
    )
    write_json(
        run_root / "run-main-001.json",
        {
            "kind": "run",
            "idea_id": "idea-001",
            "run_id": "run-main-001",
            "run_kind": "experiment",
            "branch": "run/run-main-001",
            "parent_branch": "idea/001-idea-001",
            "updated_at": "2026-03-28T00:05:00Z",
            "metric_rows": [{"metric_id": "acc", "value": 0.91}],
        },
    )

    paper_root = ensure_dir(quest_root / "paper")
    write_json(
        paper_root / "selected_outline.json",
        {
            "outline_id": "outline-001",
            "title": "Outline Title",
            "story": "Outline story",
            "detailed_outline": {
                "research_questions": ["RQ1", "RQ2"],
                "experimental_designs": ["EXP1", "EXP2"],
                "contributions": ["C1"],
            },
            "sections": [
                {
                    "section_id": "results-main",
                    "title": "Main Results",
                    "paper_role": "main_text",
                    "required_items": ["run-main-001"],
                    "result_table": [],
                }
            ],
            "evidence_contract": {"main_text_items_must_be_ready": True},
        },
    )
    write_text(paper_root / "paper_experiment_matrix.md", "# Matrix\n")
    write_json(paper_root / "paper_bundle_manifest.json", {"paper_branch": "paper/test", "selected_outline_ref": "outline-001"})
    write_json(paper_root / "claim_evidence_map.json", {"claims": []})
    write_json(
        paper_root / "paper_line_state.json",
        {
            "paper_line_id": "paper-line-001",
            "paper_branch": "paper/test",
            "source_branch": "run/run-main-001",
            "source_run_id": "run-main-001",
            "source_idea_id": "idea-001",
            "selected_outline_ref": "outline-001",
            "title": "Outline Title",
            "required_count": 1,
            "ready_required_count": 1,
            "unmapped_count": 0,
            "open_supplementary_count": 0,
            "updated_at": "2026-03-28T00:00:00Z",
        },
    )
    write_json(
        paper_root / "evidence_ledger.json",
        {
            "selected_outline_ref": "outline-001",
            "items": [
                {
                    "item_id": "run-main-001",
                    "title": "Main run",
                    "kind": "main_experiment",
                    "paper_role": "main_text",
                    "section_id": "results-main",
                    "status": "completed",
                }
            ],
        },
    )
    write_text(paper_root / "evidence_ledger.md", "# Ledger\n")
    review_root = ensure_dir(paper_root / "review")
    write_json(review_root / "submission_checklist.json", {"blocking_items": []})
    write_text(paper_root / "draft.md", "# Draft\n")
    analysis_manifest_root = ensure_dir(quest_root / ".ds" / "analysis_campaigns")
    write_json(
        analysis_manifest_root / "analysis-test.json",
        {
            "campaign_id": "analysis-test",
            "active_idea_id": "idea-001",
            "parent_run_id": "run-main-001",
            "parent_branch": "run/run-main-001",
            "paper_line_id": "paper-line-001",
            "paper_line_branch": "paper/test",
            "paper_line_root": str(quest_root),
            "selected_outline_ref": "outline-001",
            "slices": [
                {
                    "slice_id": "slice-a",
                    "branch": "analysis/idea-001/analysis-test-slice-a",
                    "worktree_root": str(quest_root / ".ds" / "worktrees" / "analysis-test-slice-a"),
                    "status": "completed",
                }
            ],
        },
    )

    analysis_root = ensure_dir(quest_root / "experiments" / "analysis-results" / "analysis-test")
    write_json(
        analysis_root / "todo_manifest.json",
        {
            "selected_outline_ref": "outline-001",
            "todo_items": [
                {
                    "slice_id": "slice-a",
                    "title": "Slice A",
                    "status": "completed",
                    "section_id": "results-main",
                    "item_id": "AN-001",
                    "claim_links": ["C1"],
                    "research_question": "RQ-A",
                    "experimental_design": "ED-A",
                    "paper_role": "main_text",
                }
            ],
        },
    )
    write_text(analysis_root / "campaign.md", "# Campaign\n")
    write_text(analysis_root / "SUMMARY.md", "# Summary\n\nCampaign summary.\n")
    write_text(analysis_root / "slice-a.md", "# Slice A\n\nResult summary.\n")

    refreshed = service.snapshot(snapshot["quest_id"])

    assert refreshed["paper_contract"]["selected_outline_ref"] == "outline-001"
    assert refreshed["paper_contract"]["title"] == "Outline Title"
    assert refreshed["paper_contract"]["research_questions"] == ["RQ1", "RQ2"]
    assert refreshed["paper_contract"]["paths"]["experiment_matrix"].endswith("paper/paper_experiment_matrix.md")
    assert refreshed["paper_contract"]["paths"]["evidence_ledger_json"].endswith("paper/evidence_ledger.json")
    assert refreshed["paper_contract"]["paths"]["paper_line_state"].endswith("paper/paper_line_state.json")
    assert refreshed["paper_contract"]["sections"][0]["section_id"] == "results-main"
    assert refreshed["paper_contract"]["evidence_summary"]["item_count"] == 1
    assert refreshed["paper_evidence"]["item_count"] == 1
    assert refreshed["idea_lines"][0]["idea_line_id"] == "idea-001"
    assert refreshed["active_idea_line_ref"] == "idea-001"
    assert refreshed["idea_lines"][0]["latest_main_run_id"] == "run-main-001"
    assert refreshed["idea_lines"][0]["paper_line_id"] == "paper-line-001"
    assert refreshed["paper_contract_health"]["contract_ok"] is True
    assert refreshed["paper_contract_health"]["writing_ready"] is True
    assert refreshed["paper_contract_health"]["recommended_next_stage"] == "finalize"
    assert refreshed["paper_lines"][0]["paper_line_id"] == "paper-line-001"
    assert refreshed["active_paper_line_ref"] == "paper-line-001"
    assert refreshed["analysis_inventory"]["campaign_count"] == 1
    assert refreshed["analysis_inventory"]["slice_count"] == 1
    assert refreshed["analysis_inventory"]["mapped_slice_count"] == 1
    assert refreshed["analysis_inventory"]["campaigns"][0]["campaign_id"] == "analysis-test"
    assert refreshed["analysis_inventory"]["campaigns"][0]["active_idea_id"] == "idea-001"
    assert refreshed["analysis_inventory"]["campaigns"][0]["paper_line_id"] == "paper-line-001"
    assert refreshed["analysis_inventory"]["campaigns"][0]["slices"][0]["slice_id"] == "slice-a"
    assert refreshed["analysis_inventory"]["campaigns"][0]["slices"][0]["branch"] == "analysis/idea-001/analysis-test-slice-a"
    assert refreshed["analysis_inventory"]["campaigns"][0]["slices"][0]["mapped"] is True


def test_auto_generated_quest_ids_initialize_from_existing_numeric_quests(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    for quest_id in ("001", "002", "010"):
        quest_root = ensure_dir(temp_home / "quests" / quest_id)
        write_text(quest_root / "quest.yaml", f'quest_id: "{quest_id}"\n')

    service = QuestService(temp_home)
    snapshot = service.create("after existing quests")

    assert snapshot["quest_id"] == "011"


def test_skill_installer_can_resync_existing_quests_after_version_change(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    installer = SkillInstaller(repo_root(), temp_home)
    service = QuestService(temp_home, skill_installer=installer)
    snapshot = service.create("sync existing quest skills")
    quest_root = Path(snapshot["quest_root"])
    stale_file = quest_root / ".codex" / "skills" / "deepscientist-scout" / "obsolete.txt"
    stale_prompt = quest_root / ".codex" / "prompts" / "obsolete.txt"
    stale_file.write_text("stale", encoding="utf-8")
    stale_prompt.write_text("stale", encoding="utf-8")

    result = installer.ensure_release_sync(
        installed_version="9.9.9",
        sync_global_enabled=False,
        sync_existing_quests_enabled=True,
        force=True,
    )

    assert result["updated"] is True
    assert result["existing_quests_synced"] is True
    assert result["existing_quests"]["count"] == 1
    assert not stale_file.exists()
    assert not stale_prompt.exists()
    assert (quest_root / ".codex" / "prompts" / "system.md").exists()
    assert (quest_root / ".codex" / "skills" / "deepscientist-scout" / "SKILL.md").exists()
    state_path = temp_home / "runtime" / "skill-sync-state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["installed_version"] == "9.9.9"


def test_explicit_custom_quest_id_still_works(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    snapshot = service.create("custom quest", quest_id="demo-quest")

    assert snapshot["quest_id"] == "demo-quest"


def test_explicit_numeric_quest_id_advances_next_auto_id(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    explicit = service.create("explicit numeric quest", quest_id="010")
    automatic = service.create("automatic after explicit numeric")

    assert explicit["quest_id"] == "010"
    assert automatic["quest_id"] == "011"


def test_preview_next_numeric_quest_id_matches_allocator_without_consuming_it(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)

    assert service.preview_next_numeric_quest_id() == "001"
    assert service.preview_next_numeric_quest_id() == "001"

    created = service.create("preview quest")

    assert created["quest_id"] == "001"
    assert service.preview_next_numeric_quest_id() == "002"

def test_init_command_syncs_global_skills(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)

    calls: list[str] = []

    def _record_sync(self):  # type: ignore[no-untyped-def]
        calls.append("sync_global")
        return {"codex": [], "claude": [], "kimi": [], "opencode": [], "notes": []}

    monkeypatch.setattr(SkillInstaller, "sync_global", _record_sync)
    exit_code = init_command(temp_home)
    assert exit_code in {0, 1}
    assert calls == ["sync_global"]


def test_pause_command_prefers_daemon_control_when_available(temp_home: Path, monkeypatch, capsys) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ok": True,
                    "action": "pause",
                    "snapshot": {
                        "quest_id": "q-demo",
                        "status": "paused",
                    },
                }
            ).encode("utf-8")

    monkeypatch.setattr("deepscientist.cli.urlopen", lambda request, timeout=3: _FakeResponse())

    exit_code = pause_command(temp_home, "q-demo")

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"status": "paused"' in captured.out


def test_local_ui_url_uses_loopback_for_bind_all_hosts() -> None:
    assert _local_ui_url("0.0.0.0", 20999) == "http://127.0.0.1:20999"
    assert _local_ui_url("", 20999) == "http://127.0.0.1:20999"
    assert _local_ui_url("::", 20999) == "http://127.0.0.1:20999"


def test_mcp_context_prefers_deepscientist_home_env(monkeypatch, tmp_path: Path) -> None:
    primary_home = tmp_path / "primary-home"
    fallback_home = tmp_path / "fallback-home"
    monkeypatch.setenv("DEEPSCIENTIST_HOME", str(primary_home))
    monkeypatch.setenv("DS_HOME", str(fallback_home))

    context = McpContext.from_env()

    assert context.home == primary_home


def test_repo_root_prefers_explicit_env(monkeypatch, tmp_path: Path) -> None:
    install_root = tmp_path / "install-root"
    ensure_dir(install_root / "src" / "deepscientist")
    ensure_dir(install_root / "src" / "skills")
    write_text(install_root / "pyproject.toml", "[project]\nname='deepscientist'\n")
    monkeypatch.setenv("DEEPSCIENTIST_REPO_ROOT", str(install_root))

    assert repo_root() == install_root.resolve()



def test_quest_create_uses_configured_default_runner(temp_home) -> None:  # type: ignore[no-untyped-def]
    from deepscientist.config import ConfigManager
    from deepscientist.shared import read_yaml, write_yaml

    manager = ConfigManager(temp_home)
    config = manager.load_named('config')
    config['default_runner'] = 'claude'
    write_yaml(manager.path_for('config'), config)

    service = QuestService(temp_home)
    snapshot = service.create('runner-default quest')

    quest_yaml = read_yaml(temp_home / 'quests' / snapshot['quest_id'] / 'quest.yaml', {})
    assert quest_yaml['default_runner'] == 'claude'
    assert snapshot['runner'] == 'claude'
