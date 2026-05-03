from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.memory import MemoryService
from deepscientist.prompts import PromptBuilder
from deepscientist.quest import QuestService
from deepscientist.shared import write_json, write_text
from deepscientist.skills import SkillInstaller


def _make_builder(temp_home: Path) -> tuple[PromptBuilder, dict]:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create("prompt builder quest")
    return PromptBuilder(repo_root(), temp_home), snapshot


def test_prompt_builder_includes_layered_runtime_context(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please decide the next step.",
        model="gpt-5.4",
    )

    assert "# DeepScientist Core System Prompt" in prompt
    assert "# Shared Interaction Contract" in prompt
    assert "## Runtime Context" in prompt
    assert "## Active Communication Surface" in prompt
    assert "## Continuation Guard" in prompt
    assert "## Quest Context" in prompt
    assert "## Recent Durable State" in prompt
    assert "## Paper And Evidence Snapshot" in prompt
    assert "## Priority Memory For This Turn" in prompt
    assert "## Recent Conversation Window" in prompt
    assert "## Current Turn Attachments" in prompt
    assert f"quest_root: {snapshot['quest_root']}" in prompt
    assert f"active_branch: {snapshot['branch']}" in prompt
    assert f"conversation_id: quest:{snapshot['quest_id']}" in prompt
    assert "research_head_branch:" in prompt
    assert "current_workspace_root:" in prompt
    assert "built_in_mcp_namespaces: memory, artifact, bash_exec" in prompt
    assert "## Cross-Quest Recall Policy" not in prompt
    assert "cross_quest_recall_enabled" not in prompt
    assert "framework_quirks.md" not in prompt
    assert "system_quirks.md" not in prompt
    assert "artifact.arxiv(paper_id=..., full_text=False)" in prompt
    assert "artifact.activate_branch(...)" in prompt
    assert "artifact.confirm_baseline(...)" in prompt
    assert "artifact.overwrite_baseline(...)" in prompt
    assert "artifact.complete_quest(...)" in prompt
    assert "## 5A. Global control surface" in prompt
    assert "chat is only a user-facing projection of state" in prompt
    assert "if autonomous continuation is enabled and the next step is clear, execution continues" in prompt
    assert "Canonical stage skills root:" in prompt
    assert "Standard stage skill paths:" in prompt
    assert "Companion skill paths:" in prompt
    assert "paper-plot" in prompt
    assert "figure-polish" in prompt
    assert "intake-audit" in prompt
    assert "review" in prompt
    assert "rebuttal" in prompt
    assert "## Current User Message" in prompt
    assert "requested_skill_rule:" in prompt
    assert "stage-specific execution detail lives in the requested skill" in prompt
    assert "#F3EEE8" in prompt
    assert "plt.rcParams.update" in prompt
    assert "AutoFigure-Edit" in prompt
    assert len(prompt.splitlines()) < 1800
    assert len(prompt) < 125000


def test_prompt_builder_enables_cross_quest_recall_only_for_shared_memory(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    config_manager = ConfigManager(temp_home)
    config_manager.ensure_files()
    config = config_manager.load_named("config")
    config["memory"] = {"read_visibility_mode": "shared_across_quests"}
    config_manager.save_named_payload("config", config)
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create("shared recall prompt quest")

    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Find a new idea.",
        model="gpt-5.4",
    )

    assert "memory_read_visibility_mode: shared_across_quests" in prompt
    assert "cross_quest_recall_enabled: true" in prompt
    assert "framework_quirks_path:" in prompt
    assert "system_quirks_path:" in prompt
    assert "sibling_quest_brief_glob:" in prompt


def test_prompt_builder_includes_recovery_resume_packet_for_daemon_recovery(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    service.update_runtime_state(
        quest_root=quest_root,
        last_resume_source="auto:daemon-recovery",
        last_resume_at="2026-03-24T07:52:25+00:00",
        last_recovery_abandoned_run_id="run-crashed-001",
        last_recovery_summary="Recovered quest from stale runtime state; previous status `running`, abandoned run `run-crashed-001`.",
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="finalize",
        user_message="",
        model="gpt-5.4",
        turn_reason="auto_continue",
    )

    assert "## Recovery Resume Packet" in prompt
    assert "resume_source: auto:daemon-recovery" in prompt
    assert "abandoned_run_id: run-crashed-001" in prompt
    assert "this turn exists because the daemon/runtime previously died" in prompt


def test_prompt_builder_stays_compact_and_avoids_redundant_stage_sop(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Please plan and run the next experiment carefully.",
        model="gpt-5.4",
    )

    assert "shared_interaction_contract_precedence:" in prompt
    assert "stage_contract_protocol:" in prompt
    assert "extract and follow the skill control surface" in prompt
    assert "stage_kickoff_protocol:" not in prompt
    assert "read_plan_keepalive_protocol:" not in prompt
    assert "tool_call_keepalive_protocol:" not in prompt
    assert "stage_plan_protocol:" not in prompt
    assert "experiment_plan_protocol:" not in prompt
    assert "analysis_plan_protocol:" not in prompt
    assert "artifact.submit_paper_outline(mode='candidate', ...)" not in prompt
    assert "problem-first vs solution-first" not in prompt


def test_prompt_builder_promotes_style_first_language_near_the_top(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="先看一下现在的情况。",
        model="gpt-5.4",
    )

    top_block = "\n".join(prompt.splitlines()[:40])
    assert "Lead with the user-facing conclusion" in top_block
    assert "都搞定啦！" in top_block
    assert "Write like a short report to the project owner" in top_block
    assert "路线切换" in top_block
    assert "Make the user payoff explicit" in top_block


def test_prompt_builder_repairs_drifted_quest_prompt_copy_and_keeps_backup(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    installer = SkillInstaller(repo_root(), temp_home)
    prompt_copy = quest_root / ".codex" / "prompts" / "system.md"
    original = prompt_copy.read_text(encoding="utf-8")
    prompt_copy.write_text(original + "\n\nQUEST_LOCAL_PROMPT_SENTINEL\n", encoding="utf-8")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Use the current system prompt.",
        model="gpt-5.4",
    )

    assert "QUEST_LOCAL_PROMPT_SENTINEL" not in prompt
    backups = installer.list_prompt_versions(quest_root)
    assert backups
    backup_id = str(backups[-1]["backup_id"])
    backup_prompt = quest_root / ".codex" / "prompt_versions" / backup_id / "system.md"
    assert "QUEST_LOCAL_PROMPT_SENTINEL" in backup_prompt.read_text(encoding="utf-8")


def test_prompt_builder_can_use_historical_prompt_backup(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    installer = SkillInstaller(repo_root(), temp_home)
    prompt_copy = quest_root / ".codex" / "prompts" / "system.md"
    original = prompt_copy.read_text(encoding="utf-8")
    prompt_copy.write_text(original + "\n\nQUEST_LOCAL_PROMPT_SENTINEL\n", encoding="utf-8")
    builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Repair the active prompt copy.",
        model="gpt-5.4",
    )
    backups = installer.list_prompt_versions(quest_root)
    assert backups
    prompt_version = str(backups[-1]["installed_version"])

    historical_builder = PromptBuilder(repo_root(), temp_home, prompt_version_selection=prompt_version)
    prompt = historical_builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Use the historical system prompt version.",
        model="gpt-5.4",
    )

    assert "QUEST_LOCAL_PROMPT_SENTINEL" in prompt


def test_prompt_builder_includes_shared_interaction_contract(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Continue the current baseline work.",
        model="gpt-5.4",
    )

    assert "# Shared Interaction Contract" in prompt
    assert "Treat `artifact.interact(...)` as the main long-lived communication thread" in prompt
    assert "Immediately follow any non-empty mailbox poll" in prompt
    assert "1 to 3 concrete options" in prompt


def test_prompt_builder_uses_copilot_system_prompt_for_copilot_workspace(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "copilot prompt quest",
        startup_contract={
            "workspace_mode": "copilot",
            "decision_policy": "user_gated",
            "launch_mode": "custom",
            "custom_profile": "freeform",
        },
    )
    quest_root = Path(snapshot["quest_root"])
    service.update_research_state(quest_root, workspace_mode="copilot")
    service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="copilot_mode",
    )

    builder = PromptBuilder(repo_root(), temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="先帮我看一下接下来怎么做。",
        model="gpt-5.4",
    )

    assert "# DeepScientist Copilot System Prompt" in prompt
    assert "- workspace_mode: copilot" in prompt
    assert "complete the user-requested unit of work" in prompt
    assert "arbitrary research tasks" in prompt
    assert "request-scoped help" in prompt
    assert "freeform_task_rule" in prompt
    assert "requested_skill_hint_rule" in prompt
    assert "turn_self_routing_rule" in prompt
    assert "route_decision_rule" in prompt
    assert "decision_skill_escalation_rule" in prompt
    assert "shell_tool_mandate" in prompt
    assert "git_tool_mandate" in prompt
    assert "decision_entry_rule" in prompt
    assert "micro_task_stop_rule" in prompt
    assert "stop_rule: once the current requested unit is done" in prompt
    assert "user-directed copilot" in prompt


def test_prompt_builder_includes_paper_contract_health_block(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    paper_root = quest_root / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "outline").mkdir(parents=True, exist_ok=True)
    write_json(
        paper_root / "selected_outline.json",
        {
            "outline_id": "outline-001",
            "title": "Health Outline",
            "detailed_outline": {
                "research_questions": ["RQ-health"],
                "experimental_designs": ["EXP-health"],
            },
            "sections": [
                {
                    "section_id": "results-health",
                    "title": "Health Results",
                    "paper_role": "main_text",
                    "required_items": ["AN-HEALTH-001"],
                    "optional_items": [],
                }
            ],
        },
    )
    write_json(
        paper_root / "paper_line_state.json",
        {
            "paper_line_id": "paper-line-health",
            "paper_branch": "paper/health",
            "selected_outline_ref": "outline-001",
            "open_supplementary_count": 1,
            "draft_status": "missing",
            "bundle_status": "missing",
        },
    )
    analysis_root = quest_root / "experiments" / "analysis-results" / "analysis-health"
    analysis_root.mkdir(parents=True, exist_ok=True)
    write_json(
        analysis_root / "todo_manifest.json",
        {
            "selected_outline_ref": "outline-001",
            "todo_items": [
                {
                    "slice_id": "slice-health",
                    "title": "Health Slice",
                    "status": "pending",
                    "tier": "main_required",
                    "section_id": "results-health",
                    "item_id": "AN-HEALTH-001",
                    "paper_role": "main_text",
                }
            ],
        },
    )
    write_text(analysis_root / "slice-health.md", "# Health Slice\n\nPending.\n")
    analysis_manifest_root = quest_root / ".ds" / "analysis_campaigns"
    analysis_manifest_root.mkdir(parents=True, exist_ok=True)
    write_json(
        analysis_manifest_root / "analysis-health.json",
        {
            "campaign_id": "analysis-health",
            "paper_line_id": "paper-line-health",
            "paper_line_branch": "paper/health",
            "selected_outline_ref": "outline-001",
            "slices": [
                {
                    "slice_id": "slice-health",
                    "status": "pending",
                    "branch": "analysis/idea/analysis-health-slice-health",
                    "worktree_root": str(quest_root / ".ds" / "worktrees" / "analysis-health-slice-health"),
                }
            ],
        },
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Continue the paper work.",
        model="gpt-5.4",
    )

    assert "paper_contract_health: evidence_ready=False, analysis_ready=False" in prompt
    assert "paper_health_counts: unresolved_required=1, unmapped_completed=0, blocking_pending=1" in prompt
    assert "paper_recommended_next_stage: analysis-campaign" in prompt
    assert "paper_health_tool:" in prompt
    assert "paper_coverage_tool:" in prompt


def test_prompt_builder_includes_surface_and_attachment_summary_for_connector_turn(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(
        snapshot["quest_id"],
        role="user",
        content="Please review the attached report.",
        source="qq:direct:openid-123",
        attachments=[
            {
                "kind": "remote",
                "name": "report.pdf",
                "content_type": "application/pdf",
                "path": "attachments/report.pdf",
                "extracted_text_path": "attachments/report.txt",
            }
        ],
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please review the attached report.",
        model="gpt-5.4",
    )

    assert "## Active Communication Surface" in prompt
    assert "active_surface: connector" in prompt
    assert "active_connector: qq" in prompt
    assert "active_chat_type: direct" in prompt
    assert "qq_surface_rule:" in prompt
    assert "qq_detail_rule:" in prompt
    assert "## Current Turn Attachments" in prompt
    assert "attachment_count: 1" in prompt
    assert "label=report.pdf" in prompt
    assert "preferred_read_path=attachments/report.txt" in prompt


def test_prompt_builder_hides_raw_binary_attachment_paths_without_readable_sidecars(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(
        snapshot["quest_id"],
        role="user",
        content="Please inspect the attached image.",
        source="qq:direct:openid-123",
        attachments=[
            {
                "kind": "remote",
                "name": "main-summary.png",
                "content_type": "image/png",
                "path": "/tmp/main-summary.png",
            }
        ],
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please inspect the attached image.",
        model="gpt-5.4",
    )

    assert "label=main-summary.png" in prompt
    assert "preferred_read_path=none" in prompt
    assert "raw_binary_path=hidden" in prompt
    assert "/tmp/main-summary.png" not in prompt


def test_prompt_builder_omits_hardware_block_by_default_when_no_gpu_subset_is_selected(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please decide the next step.",
        model="gpt-5.4",
    )

    assert "## Local Runtime Hardware" not in prompt


def test_prompt_builder_includes_selected_gpu_boundary_and_hardware_summary(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    config_manager = ConfigManager(temp_home)
    config = config_manager.load_runtime_config()
    config["hardware"] = {
        "gpu_selection_mode": "selected",
        "selected_gpu_ids": ["1"],
        "include_system_hardware_in_prompt": True,
    }
    config_manager.save_named_payload("config", config)
    write_json(
        Path(temp_home) / "runtime" / "admin" / "cache" / "system_hardware.json",
        {
            "ok": True,
            "system": {
                "cpu": {"model": "AMD EPYC Test", "logical_cores": 64},
                "memory": {"total_gb": 256.0},
                "disks": [{"mount": "/", "free_gb": 1536.0}],
                "gpus": [
                    {"gpu_id": "0", "name": "NVIDIA A100", "memory_total_gb": 80.0},
                    {"gpu_id": "1", "name": "NVIDIA A100", "memory_total_gb": 80.0},
                ],
            },
            "preferences": {
                "gpu_selection_mode": "selected",
                "selected_gpu_ids": ["1"],
                "effective_gpu_ids": ["1"],
                "cuda_visible_devices": "1",
            },
        },
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Launch the next local GPU run.",
        model="gpt-5.4",
    )

    assert "## Local Runtime Hardware" in prompt
    assert "gpu_selection_mode: selected" in prompt
    assert "selected_gpu_ids: 1" in prompt
    assert "effective_gpu_ids: 1" in prompt
    assert "cuda_visible_devices_hint: 1" in prompt
    assert "gpu_boundary_rule:" in prompt
    assert "AMD EPYC Test" in prompt
    assert "gpu_inventory: 0:NVIDIA A100 80.0GB; 1:NVIDIA A100 80.0GB" in prompt


def test_prompt_builder_omits_connector_contract_without_external_connector(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue locally.",
        model="gpt-5.4",
    )

    assert "## Connector Contract" not in prompt
    assert "connector_contract_id:" not in prompt


def test_prompt_builder_loads_qq_connector_contract_when_bound(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.bind_source(snapshot["quest_id"], "qq:direct:openid-qq-1")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "## Connector Contract" in prompt
    assert "connector_contract_id: qq" in prompt
    assert "loaded only when QQ is the active or bound external connector" in prompt
    assert "bridge itself emits the immediate transport-level receipt acknowledgement" in prompt
    assert "do not waste your first model response" in prompt
    assert "connector_hints={\"qq\": {\"render_mode\": \"markdown\"}}" in prompt
    assert "automatically reuse the most recent inbound QQ message id" in prompt
    assert "<ABSOLUTE_QUEST_LOCAL_IMAGE_FILE>" in prompt


def test_prompt_builder_can_use_historical_connector_prompt_backup(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.bind_source(snapshot["quest_id"], "qq:direct:openid-qq-1")
    quest_root = Path(snapshot["quest_root"])
    installer = SkillInstaller(repo_root(), temp_home)
    prompt_copy = quest_root / ".codex" / "prompts" / "connectors" / "qq.md"
    original = prompt_copy.read_text(encoding="utf-8")
    prompt_copy.write_text(original + "\n\nQUEST_LOCAL_CONNECTOR_PROMPT_SENTINEL\n", encoding="utf-8")
    builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Repair the active connector prompt copy.",
        model="gpt-5.4",
    )
    backups = installer.list_prompt_versions(quest_root)
    assert backups
    backup_id = str(backups[-1]["backup_id"])

    prompt = PromptBuilder(repo_root(), temp_home, prompt_version_selection=backup_id).build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "QUEST_LOCAL_CONNECTOR_PROMPT_SENTINEL" in prompt


def test_prompt_builder_loads_lingzhu_connector_contract_when_bound(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.bind_source(snapshot["quest_id"], "lingzhu:direct:glass-1")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "## Connector Contract" in prompt
    assert "connector_contract_id: lingzhu" in prompt
    assert "surface_actions" in prompt
    assert "bridge itself emits the immediate transport-level receipt acknowledgement" in prompt
    assert "do not waste your first model response" in prompt
    assert "through `artifact.interact(...)`" in prompt
    assert "clear, concise, respectful, and high-information-density" in prompt
    assert "for each Lingzhu-facing `artifact.interact(...)` message" in prompt
    assert "within about 20 Chinese characters" in prompt
    assert "only the synopsis and key facts" in prompt
    assert "text explicitly starts with `我现在的任务是`" in prompt
    assert "polling rather than giving a new task" in prompt


def test_prompt_builder_loads_weixin_connector_contract_when_bound(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.bind_source(snapshot["quest_id"], "weixin:direct:wx-user-1@im.wechat")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "## Connector Contract" in prompt
    assert "connector_contract_id: weixin" in prompt
    assert "loaded only when Weixin is the active or bound external connector" in prompt
    assert "runtime-managed `context_token`" in prompt
    assert "native image, video, and file delivery" in prompt
    assert "connector_delivery={'weixin': {'media_kind': 'image'}}" in prompt
    assert "userfiles/weixin/..." in prompt
    assert "roughly 6 tool calls" in prompt


def test_prompt_builder_prefers_local_surface_when_latest_user_turn_is_local_even_if_bound(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.bind_source(snapshot["quest_id"], "qq:direct:openid-qq-1")
    quest_service.append_message(
        snapshot["quest_id"],
        role="user",
        content="Continue this quest from the web workspace.",
        source="web-react",
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue this quest from the web workspace.",
        model="gpt-5.4",
    )

    assert "active_surface: local" in prompt
    assert "active_connector: local" in prompt
    assert "## Connector Contract" not in prompt


@pytest.mark.parametrize(("skill_id",), [("decision",), ("baseline",), ("analysis-campaign",), ("write",)])
def test_prompt_builder_includes_requested_skill_and_paths(temp_home: Path, skill_id: str) -> None:
    builder, snapshot = _make_builder(temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id=skill_id,
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert f"requested_skill: {skill_id}" in prompt
    assert str((repo_root() / "src" / "skills").resolve()) in prompt
    assert "Fallback mirrored skills root:" not in prompt


def test_prompt_builder_includes_recent_conversation_window(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(snapshot["quest_id"], role="user", content="First user turn.", source="cli")
    quest_service.append_message(snapshot["quest_id"], role="assistant", content="First assistant turn.", source="codex")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Second user turn.",
        model="gpt-5.4",
    )

    assert "## Recent Conversation Window" in prompt
    assert "conversation_tool:" in prompt
    assert "artifact.get_conversation_context" in prompt


def test_prompt_builder_includes_priority_memory_for_stage_and_message(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    memory = MemoryService(temp_home)
    memory.write_card(
        scope="quest",
        kind="ideas",
        title="Adapter ablation plan",
        body="Adapter ablation should compare against the baseline and track metric wiring carefully.",
        quest_root=quest_root,
        quest_id=snapshot["quest_id"],
        tags=["stage:experiment", "topic:adapter"],
    )
    memory.write_card(
        scope="global",
        kind="knowledge",
        title="Experiment debugging playbook",
        body="When metrics look identical to baseline, inspect seeds, dataset contract, and metric wiring first.",
        tags=["stage:experiment", "type:playbook"],
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Please inspect adapter metric wiring before the next run.",
        model="gpt-5.4",
    )

    assert "## Priority Memory For This Turn" in prompt
    assert "memory_lookup_tool:" in prompt
    assert "memory.list_recent" in prompt
    assert "memory.search" in prompt


def test_prompt_builder_includes_active_user_requirements_for_auto_continue_turn(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(
        snapshot["quest_id"],
        role="user",
        content="Keep going until the experiment, analysis, and paper draft are all complete.",
        source="web-react",
    )
    quest_service.append_message(
        snapshot["quest_id"],
        role="assistant",
        content="I finished the previous checkpoint and next I will monitor the detached experiment.",
        source="codex",
        run_id="run-prev-001",
        skill_id="experiment",
    )
    run_root = Path(snapshot["quest_root"]) / ".ds" / "runs" / "run-prev-001"
    run_root.mkdir(parents=True, exist_ok=True)
    write_json(
        run_root / "result.json",
        {
            "run_id": "run-prev-001",
            "exit_code": 0,
            "completed_at": "2026-04-04T00:00:00+00:00",
            "output_text": "Previous final result: detached experiment is running and the next check should focus on real progress.",
        },
    )
    memory_service = MemoryService(temp_home)
    memory_service.write_card(
        scope="quest",
        kind="episodes",
        title="Long run checkpoint",
        body="The detached experiment is the active long-running process and should be checked at low frequency.",
        quest_root=Path(snapshot["quest_root"]),
        quest_id=snapshot["quest_id"],
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="",
        model="gpt-5.4",
        turn_reason="auto_continue",
    )

    assert "## Turn Driver" in prompt
    assert "## Continuation Guard" in prompt
    assert "quest_not_finished: True" in prompt
    assert "current_task_status: the quest is still unfinished" in prompt
    assert "early_stop_forbidden:" in prompt
    assert "active_objective: Keep going until the experiment, analysis, and paper draft are all complete." in prompt
    assert "next_required_step:" in prompt
    assert "turn_reason: auto_continue" in prompt
    assert "there is no new user message attached to this turn" in prompt
    assert "## Active User Requirements" in prompt
    assert "Active User Requirements" in prompt
    assert "Keep going until the experiment, analysis, and paper draft are all complete." in prompt
    assert "(no new user message for this turn; continue from active user requirements and durable state)" in prompt
    assert "## Resume Context Spine" in prompt
    assert "workspace_checklist_rule:" in prompt
    assert "workspace_plan_rule:" in prompt
    assert "latest_assistant_checkpoint:" in prompt
    assert "latest_run_result:" in prompt
    assert "recent_memory_cues:" in prompt
    assert "auto_continue_interval_rule:" in prompt


def test_prompt_builder_explains_immediate_read_turns(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="These are the latest user requirements in chronological order.\n\n1. Inspect config.\n2. Verify the entrypoint.",
        model="gpt-5.4",
        turn_reason="immediate_read",
    )

    assert "turn_reason: immediate_read" in prompt
    assert "explicitly restarted because the user clicked immediate read" in prompt
    assert "runtime-prepared queued-message bundle" in prompt


def test_prompt_builder_includes_active_interactions(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.interact(
        quest_root,
        kind="decision_request",
        message="Should I continue with the current baseline route?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        options=[
            {"id": "continue", "label": "Continue", "description": "Keep the current route."},
            {"id": "reset", "label": "Reset", "description": "Revisit the baseline route."},
        ],
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please use the latest user instruction.",
        model="gpt-5.4",
    )

    assert "quest_state_tool:" in prompt
    assert "artifact.get_quest_state" in prompt
    assert "artifact.get_research_map_status" in prompt
    assert "node history" in prompt


def test_prompt_builder_includes_progress_interact_cadence_guidance(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "response_pattern: say what changed -> say what it means -> say what happens next" in prompt
    assert "compaction_protocol:" in prompt
    assert "human_progress_shape_protocol:" in prompt
    assert "do not open or rewrite large binary assets" in prompt


def test_prompt_builder_mentions_long_horizon_no_early_stop_rule(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Keep going until the research is truly done.",
        model="gpt-5.4",
    )

    assert "keep advancing until a paper-like deliverable exists" in prompt
    assert "do not self-stop after one stage or one launched detached run" in prompt
    assert "any new message or `/resume` will continue from the same quest" in prompt
    assert "standby_prefix_rule:" in prompt


def test_prompt_builder_mentions_decision_request_options_and_timeout(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please ask me before choosing the next expensive branch.",
        model="gpt-5.4",
    )

    assert "1 to 3 concrete options" in prompt
    assert "how strongly you recommend it" in prompt
    assert "impact it would have on speed, quality, cost, or risk" in prompt
    assert "wait up to 1 day" in prompt
    assert "choose the best option yourself" in prompt
    assert "notify the user of the chosen option" in prompt
    assert "GitHub key/token" in prompt
    assert "Hugging Face key/token" in prompt
    assert "do not invent placeholders" in prompt
    assert "sleep 3600" in prompt


def test_prompt_builder_mentions_algorithm_first_mode_when_paper_disabled(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "optimize the algorithm without writing a paper",
        startup_contract={
            "scope": "full_research",
            "need_research_paper": False,
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Keep optimizing the method rather than writing a paper.",
        model="gpt-5.4",
    )

    assert "## Research Delivery Policy" in prompt
    assert "## Optimization Frontier Snapshot" in prompt
    assert "optimization-state summary" in prompt
    assert "delivery_mode: algorithm_first" in prompt
    assert "the strongest justified algorithmic result" in prompt
    assert "do not default into `artifact.submit_paper_outline(...)`" in prompt
    assert "do not self-route into paper work by default" in prompt


def test_prompt_builder_strengthens_standard_optimization_entry_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "run the standard optimization-only entry",
        startup_contract={
            "launch_mode": "standard",
            "standard_profile": "optimization_task",
            "need_research_paper": False,
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="optimize",
        user_message="Keep iterating toward the strongest result without paper work.",
        model="gpt-5.4",
    )

    assert "standard_profile: optimization_task" in prompt
    assert "standard_optimization_entry_rule:" in prompt
    assert "do not route into `analysis-campaign` by default" in prompt
    assert "do not route into `write`, `review`, or `finalize`" in prompt
    assert "do not treat missing paper artifacts or missing analysis-campaign artifacts as unfinished work" in prompt


def test_prompt_builder_supports_optimize_as_standard_stage_skill(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "optimize from a branch-backed line",
        startup_contract={"need_research_paper": False},
    )
    service.update_settings(snapshot["quest_id"], active_anchor="optimize")
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="optimize",
        user_message="Continue the optimization loop from the current frontier.",
        model="gpt-5.4",
    )

    assert "requested_skill: optimize" in prompt
    assert "active_anchor: optimize" in prompt
    assert "## Optimization Frontier Snapshot" in prompt
    assert "frontier_mode:" in prompt
    assert "Continue the optimization loop from the current frontier" in prompt


def test_prompt_builder_includes_same_line_local_attempt_memory_for_optimize(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "optimize with same-line local memory",
        startup_contract={"need_research_paper": False},
    )
    quest_root = Path(snapshot["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "optimize-local-memory"
    baseline_root.mkdir(parents=True, exist_ok=True)
    write_json(
        baseline_root / "RESULT.json",
        {
            "metrics_summary": {"acc": 0.81},
            "metric_contract": {
                "primary_metric_id": "acc",
                "metrics": [{"metric_id": "acc", "direction": "maximize", "required": True}],
            },
            "primary_metric": {"metric_id": "acc", "value": 0.81, "direction": "maximize"},
        },
    )
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/local/optimize-local-memory",
        baseline_id="optimize-local-memory",
        summary="Optimize local memory baseline",
    )
    line = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="line",
        title="Local memory line",
        problem="Need same-line memory.",
        hypothesis="A local candidate memory should be visible in the prompt.",
        mechanism="Use a bounded local candidate pool.",
        next_target="optimize",
        decision_reason="Open the optimize line.",
    )
    artifact.record(
        quest_root,
        {
            "kind": "report",
            "status": "failed",
            "report_type": "optimization_candidate",
            "candidate_id": "cand-local-001",
            "idea_id": line["idea_id"],
            "branch": line["branch"],
            "strategy": "exploit",
            "mechanism_family": "adapter",
            "summary": "Adapter patch failed in smoke.",
            "details": {
                "candidate_id": "cand-local-001",
                "change_plan": "Tighten the adapter bottleneck.",
                "failure_kind": "smoke_regression",
            },
        },
        workspace_root=Path(line["worktree_root"]),
    )
    service.update_settings(snapshot["quest_id"], active_anchor="optimize")
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="optimize",
        user_message="Continue optimizing from the current line.",
        model="gpt-5.4",
    )

    assert "frontier_same_line_local_attempt_memory:" in prompt
    assert "cand-local-001 / failed / exploit / adapter / smoke_regression" in prompt
    assert "optimization_local_memory_rule" in prompt


def test_prompt_builder_documents_lineage_intent_rules(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Continue the research line.",
        model="gpt-5.4",
    )

    assert "lineage_rule:" in prompt
    assert "continue_line" in prompt
    assert "branch_alternative" in prompt
    assert "maintenance-only compatibility" in prompt
    assert "new branch/worktree and a new user-visible research node" in prompt


def test_prompt_builder_mentions_autonomous_decision_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "keep going autonomously unless the quest is truly complete",
        startup_contract={
            "decision_policy": "autonomous",
            "need_research_paper": False,
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue on your own unless explicit completion approval is required.",
        model="gpt-5.4",
    )

    assert "decision_policy: autonomous" in prompt
    assert "user_turn_self_routing_rule" in prompt
    assert "route_decision_rule" in prompt
    assert "decision_skill_escalation_rule" in prompt
    assert "micro_task_stop_rule" in prompt
    assert "do not emit `artifact.interact(kind='decision_request', ...)` for routine branching" in prompt
    assert "explicit quest-completion approval is still allowed" in prompt


def test_prompt_builder_delegates_stage_specific_sop_to_skills(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    experiment_prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Run the main experiment and report the result.",
        model="gpt-5.4",
    )
    idea_prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Brainstorm several different research directions before selecting one.",
        model="gpt-5.4",
    )
    analysis_prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="analysis-campaign",
        user_message="Plan the supplementary experiments without guessing ids.",
        model="gpt-5.4",
    )
    write_prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Prepare the paper draft carefully.",
        model="gpt-5.4",
    )

    for prompt in (experiment_prompt, idea_prompt, analysis_prompt, write_prompt):
        assert "stage_contract_protocol:" in prompt
        assert len(prompt.splitlines()) < 1800
        assert len(prompt) < 126000

    assert "RUN.md" not in experiment_prompt
    assert "problem-first vs solution-first" not in idea_prompt
    assert "### Supplementary experiment protocol" not in analysis_prompt
    assert "artifact.submit_paper_outline(mode='candidate', ...)" not in write_prompt
    assert "read `paper-plot` first" in write_prompt
    assert "figure quality remains the blocker" in write_prompt


def test_prompt_builder_mentions_baseline_gate_protocol(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="确认 baseline 之后再继续。",
        model="gpt-5.4",
    )

    assert "baseline_gate: pending" in prompt
    assert "quest_state_tool:" in prompt
    assert "artifact.confirm_baseline(...)" in prompt
    assert "artifact.overwrite_baseline(...)" in prompt
    assert "artifact.waive_baseline(...)" in prompt
    assert "Attach, import, or publish alone does not open the downstream workflow" in prompt


def test_prompt_builder_includes_requested_baseline_and_prebound_runtime_policy(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "prompt builder prebound baseline quest",
        requested_baseline_ref={"baseline_id": "demo-baseline", "variant_id": "v2"},
        startup_contract={
            "scope": "baseline_only",
            "baseline_mode": "existing",
        },
    )
    quest_root = Path(snapshot["quest_root"])
    imported_root = quest_root / "baselines" / "imported" / "demo-baseline"
    imported_root.mkdir(parents=True, exist_ok=True)
    metric_contract_json = imported_root / "json" / "metric_contract.json"
    metric_contract_json.parent.mkdir(parents=True, exist_ok=True)
    metric_contract_json.write_text('{"kind":"baseline_metric_contract"}\n', encoding="utf-8")
    service.update_baseline_state(
        quest_root,
        baseline_gate="confirmed",
        confirmed_baseline_ref={
            "baseline_id": "demo-baseline",
            "variant_id": "v2",
            "baseline_path": str(imported_root),
            "baseline_root_rel_path": "baselines/imported/demo-baseline",
            "metric_contract_json_rel_path": "baselines/imported/demo-baseline/json/metric_contract.json",
            "source_mode": "imported",
            "confirmed_at": "2026-03-12T00:00:00Z",
        },
        active_anchor="idea",
    )

    builder = PromptBuilder(repo_root(), temp_home)
    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Continue with the pre-bound baseline.",
        model="gpt-5.4",
    )

    assert "quest_state_tool:" in prompt
    assert "active_baseline_metric_contract_json: baselines/imported/demo-baseline/json/metric_contract.json" in prompt
    assert "artifact.get_quest_state" in prompt


def test_prompt_builder_includes_custom_existing_state_launch_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "continue from existing durable state",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "continue_existing_state",
            "entry_state_summary": "Trusted baseline exists and one main run already finished.",
            "custom_brief": "Audit current assets before rerunning anything expensive.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue from the current state instead of restarting from scratch.",
        model="gpt-5.4",
    )

    assert "launch_mode: custom" in prompt
    assert "custom_profile: continue_existing_state" in prompt
    assert "custom_context_rule:" in prompt
    assert "existing_state_entry_rule:" in prompt
    assert "reuse_first_rule:" in prompt
    assert "intake-audit" in prompt


def test_prompt_builder_includes_admin_ops_contract_and_knowledge_for_copilot_repairs(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "admin repair session",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "admin_ops",
            "custom_brief": "Diagnose why the admin logs page is blank.",
            "entry_state_summary": "Admin repair session `repair-test-001` from `/admin/logs`.",
            "review_materials": ["/abs/path/to/logs"],
            "admin_session": {
                "repair_id": "repair-test-001",
                "scope": "log",
                "repair_policy": "diagnose_only",
                "source_page": "/admin/logs",
                "selected_paths": ["/abs/path/to/logs"],
                "knowledge_refs": ["docs/en/09_DOCTOR.md", "src/deepscientist/daemon/api/handlers.py"],
                "targets": {
                    "log_sources": ["daemon_jsonl"],
                },
            },
        },
    )
    quest_root = Path(snapshot["quest_root"])
    service.update_research_state(quest_root, workspace_mode="copilot")
    service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="copilot_mode",
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Investigate the admin logging issue.",
        model="gpt-5.4",
    )

    assert "# Admin Ops Contract" in prompt
    assert "# Admin Ops Knowledge Base" in prompt
    assert "## Admin Ops Session Packet" in prompt
    assert "repair_id: repair-test-001" in prompt
    assert "source_page: /admin/logs" in prompt
    assert "local_daemon_api_base_url:" in prompt
    assert "local_daemon_api_admin_endpoints:" in prompt
    assert "GET /api/system/overview" in prompt
    assert "local_repo_root:" in prompt
    assert "launcher_entry:" in prompt
    assert "github_origin: https://github.com/ResearAI/DeepScientist" in prompt
    assert "command_forms_available: INSPECT, LOGS, SEARCH, REPRO, PATCH, VERIFY, ISSUE, PR" in prompt
    assert "source_address_rule:" in prompt
    assert "selected_paths_rule:" in prompt
    assert "`PATCH <goal>`" in prompt
    assert "`PR <summary>`" in prompt
    assert "docs/en/09_DOCTOR.md" in prompt
    assert "src/ui/src/components/settings/SettingsPage.tsx" in prompt
    assert "/api/system/logs/tail" in prompt
    assert "/api/admin/logs/tail" in prompt
    assert "/api/quests/:quest_id/session" in prompt
    assert "before any `git clone`, commit creation, branch publication, PR opening, or issue filing" in prompt
    assert "src/ui/src/pages/Admin" not in prompt
    assert "artifacts/reports/admin/" in prompt


def test_prompt_builder_restricts_settings_issue_profile_to_issue_tool(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "settings issue session",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "settings_issue",
            "custom_brief": "Prepare a GitHub issue draft for the settings issue page.",
        },
    )
    quest_root = Path(snapshot["quest_root"])
    service.update_research_state(quest_root, workspace_mode="copilot")
    service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="copilot_mode",
    )
    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Prepare the issue draft.",
        model="gpt-5.4",
    )

    assert "built_in_mcp_namespaces: artifact, bash_exec" in prompt
    assert "only `artifact.prepare_github_issue(...)` and `bash_exec(...)` are available in this session" in prompt
    assert "built_in_mcp_namespaces: memory, artifact, bash_exec" not in prompt


def test_prompt_builder_includes_revision_rebuttal_launch_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "respond to reviewer comments",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "revision_rebuttal",
            "entry_state_summary": "A draft and prior experiment outputs already exist.",
            "review_summary": "Reviewers asked for one extra baseline and stronger ablations.",
            "custom_brief": "Treat reviewer comments as the active contract.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Handle the revision cleanly.",
        model="gpt-5.4",
    )

    assert "launch_mode: custom" in prompt
    assert "custom_profile: revision_rebuttal" in prompt
    assert "rebuttal_entry_rule:" in prompt
    assert "rebuttal_routing_rule:" in prompt
    assert "rebuttal" in prompt


def test_prompt_builder_start_setup_block_includes_local_daemon_api_context(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    write_json(
        temp_home / "runtime" / "daemon.json",
        {
            "url": "http://127.0.0.1:20999",
            "bind_url": "http://0.0.0.0:20999",
            "auth_enabled": True,
            "auth_token": "0123456789abcdef",
        },
    )
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "setup session",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "benchmark_context": {
                    "entry_id": "bench.demo",
                    "entry_name": "Bench Demo",
                },
                "suggested_form": {
                    "title": "Bench Demo Autonomous Research",
                },
            },
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="帮我整理启动信息。",
        model="gpt-5.4",
    )

    assert "## Start Setup Session" in prompt
    assert "local_daemon_api_base_url: http://127.0.0.1:20999" in prompt
    assert "local_daemon_auth_enabled: True" in prompt
    assert "local_daemon_auth_token: 0123456789abcdef" in prompt
    assert "local_daemon_api_benchstore_endpoints:" in prompt
    assert "GET /api/benchstore/entries/:entry_id/setup-packet" in prompt
    assert "built_in_mcp_namespaces: artifact, bash_exec" in prompt
    assert "artifact.prepare_start_setup_form(...)" in prompt
    assert "reply_language_rule: answer in the user's own language" in prompt
    assert "session_patch={...}" in prompt
    assert "mode_fit_rule" in prompt
    assert "preview_plan_rule" in prompt


def test_prompt_builder_claude_start_setup_notes_namespaced_mcp_tool_names(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "claude setup session",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "Claude Setup",
                },
            },
        },
    )
    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="scout",
        user_message="帮我整理启动信息。",
        model="inherit",
        runner_name="claude",
    )

    assert "runner_tool_name_note:" in prompt
    assert "mcp__artifact__prepare_start_setup_form" in prompt
    assert "mcp__bash_exec__bash_exec" in prompt


def test_prompt_builder_start_setup_prompt_avoids_unavailable_context_tools(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "setup session without extra context tools",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "No extra context tools",
                },
            },
        },
    )

    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="scout",
        user_message="帮我整理启动信息。",
        model="inherit",
        runner_name="claude",
    )

    assert "artifact.prepare_start_setup_form(...)" in prompt
    assert "bash_exec(...)" in prompt
    assert "baseline is only the starting point" in prompt
    assert "get_start_setup_context" not in prompt
    assert "get_benchstore_catalog" not in prompt
    assert "prefer existing AISB / BenchStore entries first" in prompt
    assert "do not push the whole task-definition burden back to the user" in prompt
    assert "baseline is only the starting point" in prompt
    assert "robust improvement beyond strong baselines / SoTA" in prompt
    assert "literature / figures / writing" in prompt
    assert "mandatory_confirmation_rule" in prompt
    assert "credential_confirmation_rule" in prompt
    assert "gpu_confirmation_rule" in prompt
    assert "critical_confirmation_rule" in prompt
    assert "start_setup_prepare_schema_summary" in prompt
    assert "\"form_patch\"" in prompt
    assert "\"session_patch\"" in prompt
    assert "\"runner_namespaced_tool\": \"mcp__artifact__prepare_start_setup_form\"" in prompt
    assert "copilot_recommendation_rule" in prompt
    assert "launch_preview_rule" in prompt


def test_prompt_builder_runner_namespaced_notes_cover_supported_mcp_profiles(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    builder = PromptBuilder(repo_root(), temp_home)

    scenarios = [
        (
            "claude",
            {
                "workspace_mode": "copilot",
                "launch_mode": "custom",
                "custom_profile": "settings_issue",
            },
            "mcp__artifact__prepare_github_issue",
        ),
        (
            "kimi",
            {
                "workspace_mode": "copilot",
                "launch_mode": "custom",
                "custom_profile": "settings_issue",
            },
            "mcp__artifact__prepare_github_issue",
        ),
        (
            "opencode",
            {
                "workspace_mode": "copilot",
                "launch_mode": "custom",
                "custom_profile": "freeform",
                "start_setup_session": {
                    "source": "benchstore",
                    "locale": "zh",
                },
            },
            "mcp__artifact__prepare_start_setup_form",
        ),
        (
            "codex",
            {
                "workspace_mode": "copilot",
                "launch_mode": "custom",
                "custom_profile": "freeform",
                "start_setup_session": {
                    "source": "benchstore",
                    "locale": "zh",
                },
            },
            "mcp__artifact__prepare_start_setup_form",
        ),
    ]

    for runner_name, startup_contract, expected_tool_name in scenarios:
        snapshot = service.create(f"{runner_name} prompt scenario", startup_contract=startup_contract)
        prompt = builder.build(
            quest_id=snapshot["quest_id"],
            skill_id="scout",
            user_message="test",
            model="inherit",
            runner_name=runner_name,
        )
        assert "runner_tool_name_note:" in prompt
        assert expected_tool_name in prompt
        assert "mcp__bash_exec__bash_exec" in prompt


def test_prompt_builder_settings_issue_includes_explicit_session_packet_and_message_history(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    write_json(
        temp_home / "runtime" / "daemon.json",
        {
            "url": "http://127.0.0.1:20999",
            "bind_url": "http://0.0.0.0:20999",
            "auth_enabled": True,
            "auth_token": "0123456789abcdef",
        },
    )
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "settings issue prompt quest",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "settings_issue",
        },
    )
    service.append_message(snapshot["quest_id"], "user", "第一条消息", source="web-react")
    service.append_message(snapshot["quest_id"], "assistant", "第二条消息", source="deepscientist")

    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="scout",
        user_message="请整理 issue。",
        model="inherit",
        runner_name="claude",
    )

    assert "## Settings Issue Session Packet" in prompt
    assert "local_daemon_api_base_url: http://127.0.0.1:20999" in prompt
    assert "local_daemon_auth_enabled: True" in prompt
    assert "local_daemon_auth_token: 0123456789abcdef" in prompt
    assert "GET /api/system/overview" in prompt
    assert "GET /api/benchstore/entries" in prompt
    assert "第一条消息" in prompt
    assert "第二条消息" in prompt
    assert "settings_issue_tool_schema_summary" in prompt
    assert "\"tool\": \"prepare_github_issue\"" in prompt
    assert "\"runner_namespaced_tool\": \"mcp__artifact__prepare_github_issue\"" in prompt
    assert "\"include_system_quirks\"" in prompt


def test_prompt_builder_start_setup_expands_recent_messages(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "expanded start setup messages",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
            },
        },
    )
    service.append_message(snapshot["quest_id"], "user", "我想让你直接从现有 AISB 里面帮我选。", source="web-react")
    service.append_message(snapshot["quest_id"], "user", "机器性能一般，尽量选 API-only 和轻量一点。", source="web-react")

    prompt = PromptBuilder(repo_root(), temp_home).build(
        quest_id=snapshot["quest_id"],
        skill_id="scout",
        user_message="帮我整理启动信息。",
        model="inherit",
        runner_name="opencode",
    )

    assert "conversation_injection_rule:" in prompt
    assert "我想让你直接从现有 AISB 里面帮我选。" in prompt
    assert "机器性能一般，尽量选 API-only 和轻量一点。" in prompt


def test_prompt_builder_includes_review_audit_launch_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "audit the current draft before submission",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "review_audit",
            "entry_state_summary": "A substantial draft and figures already exist.",
            "review_summary": "Need a hard skeptical audit before finalizing.",
            "custom_brief": "Treat the current draft as the active contract.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Audit the draft before we finalize anything.",
        model="gpt-5.4",
    )

    assert "launch_mode: custom" in prompt
    assert "custom_profile: review_audit" in prompt
    assert "review_entry_rule:" in prompt
    assert "review_routing_rule:" in prompt
    assert "review" in prompt


def test_prompt_builder_includes_review_followup_and_latex_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "review the draft and keep going if the fixes are clear",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "review_audit",
            "review_followup_policy": "auto_execute_followups",
            "manuscript_edit_mode": "latex_required",
            "review_materials": ["/abs/path/reviews", "/abs/path/paper/latex"],
            "review_summary": "Audit first, then execute the justified fixes.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="review",
        user_message="Audit and keep going through the necessary fixes.",
        model="gpt-5.4",
    )

    assert "review_followup_policy: auto_execute_followups" in prompt
    assert "manuscript_edit_mode: latex_required" in prompt
    assert "review_followup_rule:" in prompt
    assert "continue automatically into the required experiments" in prompt
    assert "manuscript_edit_rule:" in prompt
    assert "LaTeX tree" in prompt or "LaTeX" in prompt


def test_prompt_builder_includes_custom_baseline_execution_policy_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "respond to reviewer comments without redoing the full baseline unless needed",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "revision_rebuttal",
            "baseline_execution_policy": "skip_unless_blocking",
            "review_summary": "Only one reviewer item might need an extra comparator.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="rebuttal",
        user_message="Handle the rebuttal efficiently.",
        model="gpt-5.4",
    )

    assert "baseline_execution_policy: skip_unless_blocking" in prompt
    assert "baseline_execution_rule:" in prompt
    assert "do not spend time on baseline reruns by default" in prompt


def test_prompt_builder_includes_baseline_source_and_plan_first_launch_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "continue from local existing system with plan-first approval",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "baseline_source_mode": "verify_local_existing",
            "execution_start_mode": "plan_then_execute",
            "baseline_acceptance_target": "comparison_ready",
            "custom_brief": "Verify the already running local system before source reproduction.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Plan the cheapest trustworthy baseline route first.",
        model="gpt-5.4",
    )

    assert "baseline_source_mode: verify_local_existing" in prompt
    assert "execution_start_mode: plan_then_execute" in prompt
    assert "baseline_acceptance_target: comparison_ready" in prompt
    assert "plan_first_entry_rule:" in prompt
    assert "baseline_source_rule:" in prompt
    assert "baseline_acceptance_rule:" in prompt
    assert "Prefer attach / import / verify-local-existing over full reproduction" in prompt


def test_prompt_builder_includes_auto_baseline_reuse_guidance(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    snapshot = service.create(
        "continue from provided sota",
        startup_contract={
            "launch_mode": "custom",
            "custom_profile": "continue_existing_state",
            "baseline_source_mode": "auto",
            "execution_start_mode": "execute_immediately",
            "baseline_acceptance_target": "comparison_ready",
            "custom_brief": "A working local comparator and a provided SOTA should be reused before any full reproduction.",
        },
    )
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Use the lightest trustworthy baseline path.",
        model="gpt-5.4",
    )

    assert "baseline_source_mode: auto" in prompt
    assert "baseline_source_rule: auto mode" in prompt
    assert "verify/reuse/attach before source reproduction" in prompt
    assert "baseline_acceptance_target: comparison_ready" in prompt
    assert "trustworthy enough for the next scientific step" in prompt
    assert "move forward immediately" in prompt


def test_prompt_builder_includes_review_gate_rule_for_paper_like_quests(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Keep drafting until the paper is strong enough.",
        model="gpt-5.4",
    )

    assert "review_gate_rule:" in prompt
    assert "consider opening `review` for an independent skeptical audit" in prompt


@pytest.mark.parametrize(("skill_id",), [("experiment",), ("analysis-campaign",)])
def test_prompt_builder_includes_active_baseline_metric_contract_guidance(temp_home: Path, skill_id: str) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    baseline_root = quest_root / "baselines" / "local" / "baseline-001"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact = ArtifactService(temp_home)
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/local/baseline-001",
        baseline_id="baseline-001",
        summary="Baseline with metric contract json",
        metrics_summary={"acc": 0.91},
        metric_contract={"primary_metric_id": "acc", "direction": "maximize"},
        primary_metric={"metric_id": "acc", "value": 0.91},
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id=skill_id,
        user_message="Continue with the confirmed baseline.",
        model="gpt-5.4",
    )

    assert "active_baseline_metric_contract_json: baselines/local/baseline-001/json/metric_contract.json" in prompt
    assert "read this JSON file and treat it as the canonical baseline comparison contract" in prompt


def test_prompt_builder_hides_deleted_reusable_baselines(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    builder.baseline_registry.publish(
        {
            "baseline_id": "baseline-keep",
            "summary": "Still available",
            "metrics_summary": {"acc": 0.92},
        }
    )
    builder.baseline_registry.publish(
        {
            "baseline_id": "baseline-delete",
            "summary": "Should disappear",
            "metrics_summary": {"acc": 0.9},
        }
    )
    builder.baseline_registry.delete("baseline-delete")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Review reusable baselines before continuing.",
        model="gpt-5.4",
    )

    assert "quest_state_tool:" in prompt


def test_prompt_builder_includes_paper_bundle_and_claim_snapshot(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    paper_root = quest_root / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "selected_outline.json").write_text(
        (
            '{'
            '"outline_id":"outline-001",'
            '"story":{"motivation":"m","challenge":"c","resolution":"r","validation":"v","impact":"i"},'
            '"ten_questions":{"q1":"why"},'
            '"detailed_outline":{"title":"Outline Title","research_questions":["RQ1","RQ2"]}'
            '}'
        )
        + "\n",
        encoding="utf-8",
    )
    (paper_root / "claim_evidence_map.json").write_text(
        (
            '{'
            '"claims":['
            '{"claim_id":"C1","support_status":"supported"},'
            '{"claim_id":"C2","support_status":"partial"}'
            ']'
            '}'
        )
        + "\n",
        encoding="utf-8",
    )
    (paper_root / "paper_bundle_manifest.json").write_text(
        (
            '{'
            '"selected_outline_ref":"outline-001",'
            '"draft_path":"paper/draft.md",'
            '"writing_plan_path":"paper/writing_plan.md",'
            '"references_path":"paper/references.bib",'
            '"claim_evidence_map_path":"paper/claim_evidence_map.json",'
            '"baseline_inventory_path":"paper/baseline_inventory.json",'
            '"compile_report_path":"paper/build/compile_report.json",'
            '"pdf_path":"paper/paper.pdf",'
            '"latex_root_path":"paper/latex",'
            '"open_source_manifest_path":"release/open_source/manifest.json",'
            '"open_source_cleanup_plan_path":"release/open_source/cleanup_plan.md"'
            '}'
        )
        + "\n",
        encoding="utf-8",
    )
    (paper_root / "baseline_inventory.json").write_text(
        '{"supplementary_baselines":[{"baseline_id":"cmp-1"}]}\n',
        encoding="utf-8",
    )
    (paper_root / "draft.md").write_text("# Draft\n", encoding="utf-8")
    (paper_root / "writing_plan.md").write_text("# Plan\n", encoding="utf-8")
    (paper_root / "references.bib").write_text("% refs\n", encoding="utf-8")
    (paper_root / "review").mkdir(parents=True, exist_ok=True)
    (paper_root / "review" / "review.md").write_text("# Review\n", encoding="utf-8")
    release_root = quest_root / "release" / "open_source"
    release_root.mkdir(parents=True, exist_ok=True)
    (release_root / "manifest.json").write_text('{"release_branch":"release/demo"}\n', encoding="utf-8")
    (release_root / "cleanup_plan.md").write_text("# Cleanup\n", encoding="utf-8")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Continue drafting with the selected outline.",
        model="gpt-5.4",
    )

    assert "selected_outline_ref: outline-001" in prompt
    assert "paper_outline_tool:" in prompt
    assert "paper_health_tool:" in prompt
    assert "paper_contract_health:" in prompt


def test_prompt_builder_mentions_long_running_bash_exec_monitoring_protocol(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Launch a long experiment and keep monitoring it carefully.",
        model="gpt-5.4",
    )

    assert "smoke_then_detach_protocol:" in prompt
    assert "progress_first_monitoring_protocol:" in prompt
    assert "long_run_reporting_protocol:" in prompt
    assert "intervention_threshold_protocol:" in prompt
    assert "timeout_protocol:" in prompt
    assert "auto_continue_monitoring_protocol:" in prompt
    assert "240 seconds" in prompt
    assert "judge health by forward progress" in prompt
    assert "do not kill or restart a run merely because a short watch window passed without final completion" in prompt


def test_prompt_builder_requires_all_shell_like_commands_to_use_bash_exec(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Use curl and python to inspect the environment.",
        model="gpt-5.4",
    )

    assert "All terminal or shell-like command execution must use `bash_exec`." in prompt
    assert "including `curl`, `python`, `python3`, `bash`, `sh`, `node`, `npm`, `uv`, `git`, `ls`, `cat`, `sed`" in prompt
    assert "Do not execute terminal commands through any non-`bash_exec` path." in prompt or "Do not execute terminal commands through any non-`bash_exec` path" in prompt


def test_prompt_builder_mentions_queued_user_message_mailbox(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(snapshot["quest_id"], role="user", content="Please check config first.", source="web-react")

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "pending_user_message_count: 1" in prompt
    assert "quest_state_tool:" in prompt
    assert "artifact.get_quest_state" in prompt
    assert "artifact.get_research_map_status" in prompt
    assert "research_map_usage_rule:" in prompt


def test_prompt_builder_mentions_immediate_acknowledgement_after_mailbox_poll(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="如果我中途插话，请优先回复我。",
        model="gpt-5.4",
    )

    assert "artifact.interact(include_recent_inbound_messages=True) is the queued human-message mailbox" in prompt
    assert "immediately send one substantive artifact.interact(...) follow-up" in prompt
    assert "do not send a redundant receipt-only message" in prompt
    assert "current background subtask is paused" in prompt
    assert "watchdog_payload_protocol:" in prompt


def test_prompt_builder_mentions_memory_contract_without_redundant_stage_playbook(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Please explore the next efficient direction.",
        model="gpt-5.4",
    )

    assert "Use `memory` for reusable lessons, compact prior context, and cross-turn retrieval." in prompt
    assert "Search memory before reopening a previously tested command path" in prompt
    assert "If a smoke test, pilot, or cheap validation resolved a reusable fact" in prompt
    assert "Maintain at least one compact checkpoint-style quest memory card" in prompt
    assert "checkpoint_memory_lookup_rule:" in prompt
    assert "current active node, node history" in prompt
    assert 'pass `tags` as a JSON array such as `["stage:baseline", "type:repro-lesson"]`' in prompt
    assert "## Priority Memory For This Turn" in prompt
    assert "memory_injection_rule:" in prompt
    assert "stage_contract_protocol:" in prompt


def test_prompt_builder_can_pull_checkpoint_style_memory_for_continue_turns(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_root = Path(snapshot["quest_root"])
    memory = MemoryService(temp_home)

    memory.write_card(
        scope="quest",
        quest_root=quest_root,
        kind="knowledge",
        title="Checkpoint continue-later route",
        body=(
            "Current checkpoint: continue-later.\n"
            "What not to reopen by default: old completion path.\n"
            "Next resume step: reread status.md and SUMMARY.md first.\n"
            "Reopen condition: only if a new evidence gap appears."
        ),
        metadata={"tags": ["stage:finalize", "type:checkpoint-memory"]},
    )
    memory.write_card(
        scope="quest",
        quest_root=quest_root,
        kind="knowledge",
        title="Irrelevant recent note",
        body="This is a newer generic note without checkpoint guidance.",
        metadata={"tags": ["stage:decision", "type:generic-note"]},
    )

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="请继续当前任务。",
        model="gpt-5.4",
    )

    assert "Checkpoint continue-later route" in prompt
    assert "matched checkpoint-memory query" in prompt
    assert "current node" in prompt


def test_prompt_builder_prefers_beginner_friendly_abstract_user_updates(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Please keep me updated in a way I can understand.",
        model="gpt-5.4",
    )

    assert "novice_context_protocol:" in prompt
    assert "omit file paths, file names" in prompt
    assert "translate them into user-facing meaning such as baseline record, draft, experiment result, or supplementary run" in prompt


def test_prompt_builder_does_not_misclassify_structured_bootstrap_as_direct_question(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    bootstrap_message = """
Project Bootstrap
- Project title: AMD

Primary Research Request
Please optimize the current system.

Research Goals
- Improve the result.

Research Contract
- What matters most is reaching rank 1.

Mandatory Working Rules
- Keep progressing automatically.
""".strip()

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message=bootstrap_message,
        model="gpt-5.4",
    )

    assert "turn_intent: continue_stage" in prompt
    assert "turn_mode: stage_execution" in prompt


def test_prompt_builder_deepxiv_capability_block_changes_with_config(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    config_manager = ConfigManager(temp_home)

    base_prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Read related papers and select one direction.",
        model="gpt-5.4",
    )
    assert "## DeepXiv Capability" in base_prompt
    assert "deepxiv_available: False" in base_prompt
    assert "deepxiv_forbidden_rule:" in base_prompt

    config = config_manager.load_runtime_config()
    literature = config.get("literature") if isinstance(config.get("literature"), dict) else {}
    deepxiv = literature.get("deepxiv") if isinstance(literature.get("deepxiv"), dict) else {}
    deepxiv["enabled"] = True
    deepxiv["token"] = "test-token"
    literature["deepxiv"] = deepxiv
    config["literature"] = literature
    config_manager.save_named_payload("config", config)

    configured_builder, configured_snapshot = _make_builder(temp_home)
    configured_prompt = configured_builder.build(
        quest_id=configured_snapshot["quest_id"],
        skill_id="idea",
        user_message="Read related papers and select one direction.",
        model="gpt-5.4",
    )
    assert "deepxiv_available: True" in configured_prompt
    assert "deepxiv_preferred_path:" in configured_prompt
    assert "deepxiv_fallback_rule:" in configured_prompt



def test_prompt_builder_uses_selected_runner_name_in_runtime_context(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please decide the next step.",
        model="gpt-5.4",
        runner_name="opencode",
    )

    assert "runner_name: opencode" in prompt
    assert "runner_name: codex" not in prompt
