from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.memory import MemoryService
from deepscientist.prompts import PromptBuilder
from deepscientist.quest import QuestService
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
    assert "artifact.arxiv(paper_id=..., full_text=False)" in prompt
    assert "artifact.confirm_baseline(...)" in prompt
    assert "artifact.complete_quest(...)" in prompt
    assert "Canonical stage skills root:" in prompt
    assert "Standard stage skill paths:" in prompt
    assert "Companion skill paths:" in prompt
    assert "figure-polish" in prompt
    assert "intake-audit" in prompt
    assert "review" in prompt
    assert "rebuttal" in prompt
    assert "Stage execution contract" in prompt
    assert "Artifact notification discipline" in prompt
    assert "reader-first" in prompt
    assert "reviewer-first" in prompt
    assert "5-minute reviewer pass" in prompt
    assert "## Current User Message" in prompt
    assert "#F3EEE8" in prompt
    assert "fog-blue" in prompt
    assert "plt.rcParams.update" in prompt
    assert 'fig.savefig("summary_line.png"' in prompt


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
    assert "qq_auto_send_main_experiment_png: True" in prompt
    assert "qq_enable_markdown_send: False" in prompt
    assert "qq_media_rule:" in prompt
    assert "qq_visual_rule:" in prompt
    assert "qq_structured_delivery_rule:" in prompt
    assert "## Current Turn Attachments" in prompt
    assert "attachment_count: 1" in prompt
    assert "label=report.pdf" in prompt
    assert "preferred_read_path=attachments/report.txt" in prompt


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
    assert "connector_hints={\"qq\": {\"render_mode\": \"markdown\"}}" in prompt
    assert "automatically reuse the most recent inbound QQ message id" in prompt
    assert "/absolute/path/to/main_summary.png" in prompt


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
    assert "only the synopsis and key facts" in prompt


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

    assert "[user|cli] First user turn." in prompt
    assert "[assistant|codex] First assistant turn." in prompt


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
    assert "Adapter ablation plan" in prompt
    assert "Experiment debugging playbook" in prompt
    assert "matches current user message" in prompt or "recent experiment" in prompt


def test_prompt_builder_includes_active_user_requirements_for_auto_continue_turn(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_service.append_message(
        snapshot["quest_id"],
        role="user",
        content="Keep going until the experiment, analysis, and paper draft are all complete.",
        source="web-react",
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

    assert "Active interactions:" in prompt
    assert "Should I continue with the current baseline route?" in prompt


def test_prompt_builder_includes_progress_interact_cadence_guidance(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Continue the quest.",
        model="gpt-5.4",
    )

    assert "real human-meaningful checkpoints" in prompt
    assert "20 to 30 minutes" in prompt
    assert "do not send empty filler" in prompt
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
    assert "any new message or using `/resume` will continue" in prompt
    assert "[Waiting for decision]" in prompt


def test_prompt_builder_mentions_decision_request_options_and_timeout(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="Please ask me before choosing the next expensive branch.",
        model="gpt-5.4",
    )

    assert "1 to 3 concrete options" in prompt
    assert "wait up to 1 day" in prompt
    assert "choose the best option yourself" in prompt
    assert "notify the user of the chosen option" in prompt
    assert "GitHub key/token" in prompt
    assert "Hugging Face key/token" in prompt
    assert "do not fabricate placeholder credentials" in prompt
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
    assert "delivery_mode: algorithm_first" in prompt
    assert "the strongest justified algorithmic result" in prompt
    assert "do not default into `artifact.submit_paper_outline(...)`" in prompt
    assert "do not self-route into paper work by default" in prompt


def test_prompt_builder_documents_lineage_intent_rules(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Continue the research line.",
        model="gpt-5.4",
    )

    assert "lineage_intent" in prompt
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
    assert "do not emit `artifact.interact(kind='decision_request', ...)` for routine branching" in prompt
    assert "explicit quest-completion approval is still allowed" in prompt


def test_prompt_builder_mentions_record_main_experiment_protocol(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Run the main experiment and report the result.",
        model="gpt-5.4",
    )

    assert "artifact.record_main_experiment(...)" in prompt
    assert "RUN.md" in prompt
    assert "RESULT.json" in prompt


def test_prompt_builder_mentions_baseline_gate_protocol(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="baseline",
        user_message="确认 baseline 之后再继续。",
        model="gpt-5.4",
    )

    assert "baseline_gate: pending" in prompt
    assert "confirmed_baseline_ref: none" in prompt
    assert "artifact.confirm_baseline(...)" in prompt
    assert "artifact.waive_baseline(...)" in prompt
    assert "Attach, import, or publish alone does not open the downstream workflow." in prompt


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

    assert 'requested_baseline_ref: {"baseline_id": "demo-baseline", "variant_id": "v2"}' in prompt
    assert 'startup_contract: {"baseline_mode": "existing", "scope": "baseline_only"}' in prompt
    assert "confirmed_baseline_import_root: baselines/imported/demo-baseline" in prompt
    assert "prebound_baseline_ready: True" in prompt
    assert "active_baseline_metric_contract_json: baselines/imported/demo-baseline/json/metric_contract.json" in prompt
    assert "do not redo baseline discovery or reproduction unless you find a concrete incompatibility" in prompt


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


def test_prompt_builder_includes_review_gate_rule_for_paper_like_quests(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Keep drafting until the paper is strong enough.",
        model="gpt-5.4",
    )

    assert "review_gate_rule:" in prompt
    assert "open `review` for an independent skeptical audit" in prompt


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
    assert "selected_outline_title: Outline Title" in prompt
    assert "claim_status_counts: supported=1, partial=1, unsupported=0, deferred=0" in prompt
    assert "downgrade_watchlist: C2 [partial]" in prompt
    assert "baseline_inventory_status: paper/baseline_inventory.json [exists]" in prompt
    assert "open_source_manifest_status: release/open_source/manifest.json [exists]" in prompt
    assert "open_source_release_branch: release/demo" in prompt
    assert "paper_state_rule:" in prompt


def test_prompt_builder_mentions_long_running_bash_exec_monitoring_protocol(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Launch a long experiment and keep monitoring it carefully.",
        model="gpt-5.4",
    )

    assert "sleep about `60s`" in prompt
    assert "sleep about `120s`" in prompt
    assert "sleep about `300s`" in prompt
    assert "sleep about `600s`" in prompt
    assert "sleep about `1800s`" in prompt
    assert "artifact.interact(kind='progress', ...)" in prompt
    assert "bash_exec(mode='read', id=...)" in prompt
    assert "bash_exec(mode='read', id=..., tail_limit=..., order='desc')" in prompt
    assert "bash_exec(mode='read', id=..., after_seq=last_seen_seq" in prompt
    assert "include a structured `comment`" in prompt
    assert "{stage, goal, action, expected_signal, next_check}" in prompt
    assert "each completed sleep/await cycle" in prompt
    assert "estimated next reply time" in prompt
    assert "__DS_PROGRESS__" in prompt
    assert "estimate whether the command can finish within the selected wait window" in prompt
    assert "use bash_exec(mode='detach', ...) and monitor" in prompt
    assert "first run a bounded smoke test or pilot" in prompt
    assert "stop it with `bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)`" in prompt
    assert "wait=true" in prompt
    assert "force=true" in prompt
    assert "bash_exec(mode='history')" in prompt
    assert "silent_seconds" in prompt
    assert "watchdog_overdue" in prompt
    assert "tqdm-style progress reporter" in prompt


def test_prompt_builder_requires_all_shell_like_commands_to_use_bash_exec(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="experiment",
        user_message="Use curl and python to inspect the environment.",
        model="gpt-5.4",
    )

    assert "Any shell-like command execution must use `bash_exec`" in prompt
    assert "`curl`, `python`, `python3`, `bash`, `sh`, `node`" in prompt
    assert "Do not execute shell commands through any non-`bash_exec` path." in prompt


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
    assert "queued user messages waiting to be picked up via artifact.interact" in prompt
    assert "immediately send a follow-up artifact.interact acknowledgement" in prompt


def test_prompt_builder_mentions_immediate_acknowledgement_after_mailbox_poll(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="decision",
        user_message="如果我中途插话，请优先回复我。",
        model="gpt-5.4",
    )

    assert "artifact.interact(include_recent_inbound_messages=True) is the queued human-message mailbox" in prompt
    assert "immediately call artifact.interact(...) again to confirm receipt" in prompt
    assert "current background subtask is paused" in prompt


def test_prompt_builder_mentions_memory_call_protocol_and_exploration_efficiency(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="idea",
        user_message="Please explore the next efficient direction.",
        model="gpt-5.4",
    )

    assert "### `memory` call protocol" in prompt
    assert "memory.list_recent(scope='quest', limit=5)" in prompt
    assert "memory.search(query='<task or dataset or baseline>'" in prompt
    assert 'pass `tags` as a real JSON array' in prompt
    assert 'never as one comma-separated string' in prompt
    assert "first review prior idea and experiment memory as reference material" in prompt
    assert "review prior quest experiment records, failures, and result summaries" in prompt
    assert "outcome status such as `success`, `partial`, or `failure`" in prompt
    assert "### Exploration efficiency protocol" in prompt
    assert "Preserve the current best verified branch as the elite line." in prompt


def test_prompt_builder_mentions_outline_first_paper_flow(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Prepare the paper draft carefully.",
        model="gpt-5.4",
    )

    assert "artifact.submit_paper_outline(mode='candidate', ...)" in prompt
    assert "if comparison would materially improve quality" in prompt
    assert "artifact.submit_paper_outline(mode='select'|'revise', ...)" in prompt
    assert "artifact.submit_paper_bundle(...)" in prompt
    assert "The selected outline is the authoritative blueprint" in prompt
    assert "motivation" in prompt
    assert "challenge" in prompt
    assert "resolution" in prompt
    assert "validation" in prompt
    assert "impact" in prompt


def test_prompt_builder_mentions_outline_bound_analysis_campaign_contract(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="analysis-campaign",
        user_message="Launch the follow-up analysis carefully.",
        model="gpt-5.4",
    )

    assert "selected_outline_ref" in prompt
    assert "research_questions" in prompt
    assert "experimental_designs" in prompt
    assert "todo_items" in prompt
    assert "do not launch it as a free-floating batch" in prompt
    assert "one-slice analysis campaign" in prompt
    assert "current workspace/result node" in prompt


def test_prompt_builder_mentions_unified_supplementary_experiment_protocol_and_id_discipline(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="analysis-campaign",
        user_message="Plan the supplementary experiments without guessing ids.",
        model="gpt-5.4",
    )

    assert "### Supplementary experiment protocol" in prompt
    assert "ordinary analysis" in prompt
    assert "review-driven evidence gaps" in prompt
    assert "rebuttal-driven extra runs" in prompt
    assert "artifact.resolve_runtime_refs(...)" in prompt
    assert "artifact.get_analysis_campaign(campaign_id='active'|...)" in prompt
    assert "artifact.list_paper_outlines(...)" in prompt
    assert "Do not invent opaque ids" in prompt
    assert "campaign_id + slice_id" in prompt
    assert "`deviations` and `evidence_paths` are optional slice fields" in prompt


def test_prompt_builder_mentions_paperagent_like_outline_selection_rubric(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Select the best outline and continue.",
        model="gpt-5.4",
    )

    assert "method fidelity" in prompt
    assert "evidence support" in prompt
    assert "narrative coherence" in prompt
    assert "experiment ordering quality" in prompt


def test_prompt_builder_mentions_external_reasoning_and_paper_plan_contract(temp_home: Path) -> None:
    builder, snapshot = _make_builder(temp_home)

    prompt = builder.build(
        quest_id=snapshot["quest_id"],
        skill_id="write",
        user_message="Write the paper carefully and explain the reasoning.",
        model="gpt-5.4",
    )

    assert "External reasoning, planning, and verification style" in prompt
    assert "current judgment or conclusion" in prompt
    assert "verification checklist or checks performed" in prompt
    assert "paper/writing_plan.md" in prompt
    assert "experiment-to-section mapping" in prompt
    assert "figure/table-to-data-source mapping" in prompt
