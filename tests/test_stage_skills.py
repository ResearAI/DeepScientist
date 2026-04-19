from __future__ import annotations

from pathlib import Path

from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.prompts import PromptBuilder
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller, companion_skill_ids, discover_skill_bundles, stage_skill_ids


EXPECTED_STAGE_SKILLS = {
    "scout",
    "baseline",
    "idea",
    "optimize",
    "experiment",
    "analysis-campaign",
    "write",
    "finalize",
    "decision",
}

EXPECTED_COMPANION_SKILLS = {
    "paper-plot",
    "figure-polish",
    "intake-audit",
    "review",
    "rebuttal",
}

INTERACTION_CONTRACT_SKILLS = EXPECTED_STAGE_SKILLS | {
    "paper-plot",
    "intake-audit",
    "review",
    "rebuttal",
}


def test_src_stage_skills_exist_and_are_nontrivial() -> None:
    root = repo_root() / "src" / "skills"
    for skill_id in EXPECTED_STAGE_SKILLS:
        path = root / skill_id / "SKILL.md"
        assert path.exists(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) >= 40, f"{path} is unexpectedly thin"


def test_companion_skills_exist_and_are_nontrivial() -> None:
    root = repo_root() / "src" / "skills"
    for skill_id in EXPECTED_COMPANION_SKILLS:
        path = root / skill_id / "SKILL.md"
        assert path.exists(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) >= 30, f"{path} is unexpectedly thin"


def test_skill_discovery_prefers_src_skills() -> None:
    bundles = discover_skill_bundles(repo_root())
    discovered = {bundle.skill_id for bundle in bundles}
    assert EXPECTED_STAGE_SKILLS.issubset(discovered)
    assert EXPECTED_COMPANION_SKILLS.issubset(discovered)
    for bundle in bundles:
        if bundle.skill_id in EXPECTED_STAGE_SKILLS:
            assert Path(bundle.skill_md).is_relative_to(repo_root() / "src" / "skills")


def test_skill_role_metadata_drives_stage_and_companion_catalogs() -> None:
    root = repo_root()
    stage_ids = set(stage_skill_ids(root))
    companion_ids = set(companion_skill_ids(root))

    assert EXPECTED_STAGE_SKILLS.issubset(stage_ids)
    assert EXPECTED_COMPANION_SKILLS.issubset(companion_ids)

    for skill_id in EXPECTED_STAGE_SKILLS | EXPECTED_COMPANION_SKILLS:
        text = (root / "src" / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "skill_role:" in text


def test_new_companion_skill_reference_files_exist() -> None:
    root = repo_root() / "src" / "skills"
    assert (root / "paper-plot" / "references" / "bar_grouped_hatch.md").exists()
    assert (root / "paper-plot" / "references" / "line_confidence_band.md").exists()
    assert (root / "paper-plot" / "references" / "scatter_tsne_cluster.md").exists()
    assert (root / "paper-plot" / "scripts" / "bar_spice.py").exists()
    assert (root / "paper-plot" / "scripts" / "line_selfdistill.py").exists()
    assert (root / "paper-plot" / "scripts" / "scatter_tsne.py").exists()
    assert (root / "intake-audit" / "references" / "state-audit-template.md").exists()
    assert (root / "review" / "references" / "review-report-template.md").exists()
    assert (root / "review" / "references" / "revision-log-template.md").exists()
    assert (root / "review" / "references" / "experiment-todo-template.md").exists()
    assert (root / "rebuttal" / "references" / "action-plan-template.md").exists()
    assert (root / "rebuttal" / "references" / "evidence-update-template.md").exists()
    assert (root / "rebuttal" / "references" / "review-matrix-template.md").exists()
    assert (root / "rebuttal" / "references" / "response-letter-template.md").exists()


def test_stage_plan_and_checklist_templates_exist() -> None:
    root = repo_root() / "src" / "skills"
    assert (root / "baseline" / "references" / "baseline-plan-template.md").exists()
    assert (root / "baseline" / "references" / "baseline-checklist-template.md").exists()
    assert (root / "baseline" / "references" / "artifact-payload-examples.md").exists()
    assert (root / "baseline" / "references" / "artifact-flow-examples.md").exists()
    assert (root / "baseline" / "references" / "boundary-cases.md").exists()
    assert (root / "experiment" / "references" / "main-experiment-plan-template.md").exists()
    assert (root / "experiment" / "references" / "main-experiment-checklist-template.md").exists()
    assert (root / "analysis-campaign" / "references" / "campaign-plan-template.md").exists()
    assert (root / "analysis-campaign" / "references" / "campaign-checklist-template.md").exists()
    assert (root / "analysis-campaign" / "references" / "artifact-flow-examples.md").exists()
    assert (root / "analysis-campaign" / "references" / "boundary-cases.md").exists()


def test_write_skill_venue_templates_exist_and_sync(temp_home: Path) -> None:
    root = repo_root() / "src" / "skills" / "write" / "templates"
    assert (root / "README.md").exists()
    assert (root / "DEEPSCIENTIST_NOTES.md").exists()
    assert (root / "UPSTREAM_LICENSE.txt").exists()
    assert (root / "iclr2026" / "iclr2026_conference.tex").exists()
    assert (root / "icml2026" / "example_paper.tex").exists()
    assert (root / "neurips2025" / "main.tex").exists()
    assert (root / "acl" / "acl_latex.tex").exists()

    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("write template sync quest")
    quest_root = Path(quest["quest_root"])

    synced_root = quest_root / ".codex" / "skills" / "deepscientist-write" / "templates"
    assert (synced_root / "DEEPSCIENTIST_NOTES.md").exists()
    assert (synced_root / "iclr2026" / "iclr2026_conference.tex").exists()
    assert (synced_root / "acl" / "acl_latex.tex").exists()


def test_idea_skill_requires_memory_first_literature_survey() -> None:
    idea_skill = repo_root() / "src" / "skills" / "idea" / "SKILL.md"
    text = idea_skill.read_text(encoding="utf-8")
    assert "memory.search(...)" in text
    assert "arXiv" in text
    assert "artifact.arxiv(" in text
    assert "literature survey report" in text
    assert "at least `5` and usually `5-10`" in text
    assert "task-modeling-related" in text
    assert "`5-10` usable-paper floor is durably satisfied" in text
    assert "standard citation format" in text
    assert "`References` or `Bibliography` section" in text

    template = repo_root() / "src" / "skills" / "idea" / "references" / "literature-survey-template.md"
    assert template.exists()
    template_text = template.read_text(encoding="utf-8")
    assert "hard floor of at least `5` and usually `5-10` usable papers" in template_text
    assert "standard citation string or citation key" in template_text
    assert "Citation-ready shortlist for the selected idea" in template_text

    gate_template = repo_root() / "src" / "skills" / "idea" / "references" / "selection-gate.md"
    gate_text = gate_template.read_text(encoding="utf-8")
    assert "the literature survey must already durably cover at least `5` and usually `5-10` related and usable papers" in gate_text
    assert "`references` or `bibliography` in a standard citation format" in gate_text


def test_scout_skill_requires_memory_first_literature_report() -> None:
    scout_skill = repo_root() / "src" / "skills" / "scout" / "SKILL.md"
    text = scout_skill.read_text(encoding="utf-8")
    assert "memory.search(...)" in text
    assert "arXiv" in text
    assert "artifact.arxiv(" in text
    assert "literature scouting report" in text

    template = repo_root() / "src" / "skills" / "scout" / "references" / "literature-scout-template.md"
    assert template.exists()


def test_quest_creation_syncs_all_stage_skills(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("skill sync quest")
    quest_root = Path(quest["quest_root"])

    codex_skills = sorted((quest_root / ".codex" / "skills").glob("deepscientist-*"))
    claude_skills = sorted((quest_root / ".claude" / "agents").glob("deepscientist-*.md"))
    opencode_skills = sorted((quest_root / ".opencode" / "skills").glob("deepscientist-*"))

    synced_codex = {path.name.removeprefix("deepscientist-") for path in codex_skills}
    synced_claude = {path.stem.removeprefix("deepscientist-") for path in claude_skills}
    synced_opencode = {path.name.removeprefix("deepscientist-") for path in opencode_skills}

    assert EXPECTED_STAGE_SKILLS.issubset(synced_codex)
    assert EXPECTED_STAGE_SKILLS.issubset(synced_claude)
    assert EXPECTED_STAGE_SKILLS.issubset(synced_opencode)
    assert EXPECTED_COMPANION_SKILLS.issubset(synced_codex)
    assert EXPECTED_COMPANION_SKILLS.issubset(synced_claude)
    assert EXPECTED_COMPANION_SKILLS.issubset(synced_opencode)
    assert (quest_root / ".codex" / "prompts" / "system.md").exists()
    assert (quest_root / ".codex" / "prompts" / "contracts" / "shared_interaction.md").exists()
    assert (quest_root / ".codex" / "prompts" / "connectors" / "qq.md").exists()


def test_skill_resync_repairs_frontmatter_and_removes_stale_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    installer = SkillInstaller(repo_root(), temp_home)
    quest = QuestService(temp_home, skill_installer=installer).create("skill resync quest")
    quest_root = Path(quest["quest_root"])

    installed_skill = quest_root / ".codex" / "skills" / "deepscientist-idea" / "SKILL.md"
    stale_file = quest_root / ".codex" / "skills" / "deepscientist-idea" / "stale.tmp"
    stale_removed_codex = quest_root / ".codex" / "skills" / "deepscientist-alpharxiv-paper-loopup"
    stale_removed_claude = quest_root / ".claude" / "agents" / "deepscientist-alpharxiv-paper-loopup.md"

    installed_skill.write_text("broken skill body\n", encoding="utf-8")
    stale_file.write_text("remove me\n", encoding="utf-8")
    stale_removed_codex.mkdir(parents=True)
    (stale_removed_codex / "SKILL.md").write_text("legacy skill\n", encoding="utf-8")
    stale_removed_claude.write_text("legacy claude skill\n", encoding="utf-8")

    installer.sync_quest(quest_root)

    repaired = installed_skill.read_text(encoding="utf-8")
    assert repaired.startswith("---\n")
    assert "name:" in repaired
    assert not stale_file.exists()
    assert not stale_removed_codex.exists()
    assert not stale_removed_claude.exists()


def test_paper_reading_stage_skills_use_artifact_arxiv_and_legacy_skill_is_removed() -> None:
    root = repo_root() / "src" / "skills"
    for skill_id in ("baseline", "scout", "idea", "write", "finalize"):
        text = (root / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "artifact.arxiv(" in text
        assert "alpharxiv-paper-loopup" not in text

    assert not (root / "alpharxiv-paper-loopup" / "SKILL.md").exists()


def test_baseline_skill_documents_confirm_or_waive_gate() -> None:
    text = (repo_root() / "src" / "skills" / "baseline" / "SKILL.md").read_text(encoding="utf-8")
    assert "artifact.confirm_baseline(...)" in text
    assert "artifact.waive_baseline(...)" in text
    assert "do not open the downstream gate" in text
    assert "requested_baseline_ref" in text
    assert "verify the comparator and metric contract" in text


def test_baseline_skill_documents_environment_autonomy_with_uv_as_tactic() -> None:
    text = (repo_root() / "src" / "skills" / "baseline" / "SKILL.md").read_text(encoding="utf-8")
    assert "## Environment tactics" in text
    assert "For Python baselines, prefer a reproducible isolated environment" in text
    assert "`uv` is a useful default tactic" in text
    assert "uv sync" in text
    assert "uv venv" in text
    assert "uv pip install" in text
    assert "uv run ..." in text
    assert "Switch to repo-native conda, docker, poetry" in text
    assert "Do not force a global `uv` route when it would make the reproduced baseline less faithful" in text


def test_baseline_skill_has_compact_durable_output_contract() -> None:
    text = (repo_root() / "src" / "skills" / "baseline" / "SKILL.md").read_text(encoding="utf-8")
    assert "## Durable route records" in text
    assert "Durable records are required in substance, not in fixed filenames" in text
    assert "`PLAN.md`, `CHECKLIST.md`, `setup.md`, `execution.md`, `verification.md`, `analysis_plan.md`, and `REPRO_CHECKLIST.md` are allowed compatibility surfaces" in text
    assert "`attachment.yaml` or equivalent provenance is required for attached or imported baselines" in text
    assert "`<baseline_root>/json/metric_contract.json` as the canonical accepted comparison contract" in text


def test_decision_skill_requires_reuse_baseline_to_land_on_attach_and_confirm() -> None:
    text = (repo_root() / "src" / "skills" / "decision" / "SKILL.md").read_text(encoding="utf-8")
    assert "artifact.attach_baseline(...)" in text
    assert "artifact.confirm_baseline(...)" in text
    assert "explicit blocker or waiver" in text


def test_experiment_and_decision_skills_document_activate_branch_and_analysis_cost_gate() -> None:
    experiment_text = (repo_root() / "src" / "skills" / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    decision_text = (repo_root() / "src" / "skills" / "decision" / "SKILL.md").read_text(encoding="utf-8")

    assert "artifact.activate_branch(...)" in experiment_text
    assert "clear academic or claim-level value" in experiment_text
    assert "artifact.activate_branch(...)" in decision_text
    assert "extra resource cost" in decision_text


def test_prompt_builder_skill_paths_only_reference_existing_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home)).create("skill prompt quest")
    builder = PromptBuilder(repo_root(), temp_home)

    prompt = builder.build(
        quest_id=quest["quest_id"],
        skill_id="finalize",
        user_message="Please summarize the quest and stop cleanly.",
        model="gpt-5.4",
    )

    finalize_primary = str((repo_root() / "src" / "skills" / "finalize" / "SKILL.md").resolve())
    assert "Fallback mirrored skills root:" not in prompt
    assert f"- finalize: primary={finalize_primary}" in prompt


def test_shared_interaction_contract_covers_blocking_and_mailbox_rules() -> None:
    text = (repo_root() / "src" / "prompts" / "contracts" / "shared_interaction.md").read_text(encoding="utf-8")
    assert "1 to 3 concrete options" in text
    assert "wait up to 1 day" in text
    assert "missing external credential or secret" in text
    assert "sleep 3600" in text
    assert "highest-priority user instruction bundle" in text
    assert "Immediately follow any non-empty mailbox poll" in text
    assert "real user-visible progress" in text
    assert "roughly 12 tool calls or about 8 minutes" in text
    assert "first 3 tool calls of substantial work" in text
    assert "5 consecutive tool calls on reading" in text or "5 consecutive tool calls on reading, searching" in text


def test_stage_and_companion_skills_reference_shared_interaction_contract() -> None:
    root = repo_root() / "src" / "skills"
    for skill_id in INTERACTION_CONTRACT_SKILLS:
        text = (root / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "Follow the shared interaction contract injected by the system prompt." in text


def test_all_stage_skills_require_stage_start_memory_retrieval_and_stage_end_memory_write() -> None:
    root = repo_root() / "src" / "skills"
    for skill_id in ("scout", "idea", "experiment", "analysis-campaign", "write", "finalize"):
        text = (root / skill_id / "SKILL.md").read_text(encoding="utf-8")
        assert "Stage-start requirement:" in text
        assert "memory.list_recent(scope='quest', limit=5)" in text
        assert "memory.search(...)" in text
        assert "Stage-end requirement:" in text
        assert "memory.write(...)" in text

    baseline_text = (root / "baseline" / "SKILL.md").read_text(encoding="utf-8")
    assert "do not require a fresh memory pass for every fast-path validation" in baseline_text
    assert "use `memory.list_recent(...)` or `memory.search(...)` when resuming" in baseline_text
    assert "fast-path exception:" in baseline_text


def test_experiment_skill_requires_outcome_status_in_memory_writes() -> None:
    text = (repo_root() / "src" / "skills" / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    assert "`success`, `partial`, or `failure`" in text
    assert "`idea_id`, `branch`, and `run_id`" in text


def test_long_running_skills_require_next_reply_time_reporting() -> None:
    root = repo_root() / "src" / "skills"
    experiment_text = (root / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    campaign_text = (root / "analysis-campaign" / "SKILL.md").read_text(encoding="utf-8")

    assert "estimated next reply time" in experiment_text
    assert "next_reply_at" in experiment_text
    assert "estimated next reply time" in campaign_text


def test_stage_skills_document_palette_requirements_for_connector_and_paper_outputs() -> None:
    root = repo_root() / "src" / "skills"
    experiment_text = (root / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    campaign_text = (root / "analysis-campaign" / "SKILL.md").read_text(encoding="utf-8")
    write_text = (root / "write" / "SKILL.md").read_text(encoding="utf-8")

    assert "sage-clay" in experiment_text
    assert "mist-stone" in experiment_text
    assert "dust-rose" in experiment_text
    assert "Connector-facing chart requirements" in experiment_text

    assert "sage-clay" in campaign_text
    assert "mist-stone" in campaign_text
    assert "Connector-facing campaign chart requirements" in campaign_text

    assert "mist-stone" in write_text
    assert "sage-clay" in write_text
    assert "Paper-figure requirements" in write_text
    assert "#F3EEE8" in experiment_text
    assert "#7F8F84" in campaign_text
    assert "#B88C8C" in write_text
    assert "system prompt" in experiment_text
    assert "system prompt" in campaign_text
    assert "system prompt Morandi plotting template" in write_text


def test_write_skill_documents_reviewer_first_reader_first_contract_and_references() -> None:
    root = repo_root() / "src" / "skills" / "write"
    text = (root / "SKILL.md").read_text(encoding="utf-8")

    assert "reviewer-first pass" in text
    assert "reader-centered" in text
    assert "paper experiment matrix" in text
    assert "paper/reviewer_first_pass.md" in text
    assert "paper/section_contracts.md" in text
    assert "paper/figure_storyboard.md" in text
    assert "paper/related_work_map.md" in text
    assert "paper/paper_experiment_matrix.md" in text
    assert "paper/proofing/language_issues.md" in text
    assert "`paper-plot`" in text
    assert (root / "references" / "paper-experiment-matrix-template.md").exists()
    assert (root / "references" / "reviewer-first-writing.md").exists()
    assert (root / "references" / "section-contracts.md").exists()
    assert (root / "references" / "sentence-level-proofing.md").exists()


def test_experiment_and_analysis_references_cover_evidence_ladder_and_campaign_design() -> None:
    root = repo_root() / "src" / "skills"
    experiment_text = (root / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    campaign_text = (root / "analysis-campaign" / "SKILL.md").read_text(encoding="utf-8")
    baseline_text = (root / "baseline" / "SKILL.md").read_text(encoding="utf-8")

    assert "references/evidence-ladder.md" in experiment_text
    assert "auxiliary/dev" in experiment_text
    assert "main/test" in experiment_text
    assert "minimum -> solid -> maximum" in experiment_text
    assert (root / "experiment" / "references" / "evidence-ladder.md").exists()

    assert "references/campaign-design.md" in campaign_text
    assert "references/artifact-flow-examples.md" in campaign_text
    assert "references/boundary-cases.md" in campaign_text
    assert "claim-carrying" in campaign_text
    assert "supporting" in campaign_text
    assert (root / "analysis-campaign" / "references" / "campaign-design.md").exists()
    assert "references/artifact-flow-examples.md" in baseline_text
    assert "references/boundary-cases.md" in baseline_text


def test_figure_polish_skill_requires_render_inspect_revise_workflow_and_style_asset() -> None:
    text = (repo_root() / "src" / "skills" / "figure-polish" / "SKILL.md").read_text(encoding="utf-8")
    style_asset = repo_root() / "src" / "skills" / "figure-polish" / "assets" / "deepscientist-academic.mplstyle"

    assert "render-inspect-revise" in text
    assert "open the rendered figure yourself" in text
    assert "Do not treat a figure as final" in text
    assert "main message obvious" in text
    assert "color-vision-deficient" in text
    assert "Publication-grade figure refinement is recommended with AutoFigure-Edit" in text
    assert "https://github.com/ResearAI/AutoFigure-Edit" in text
    assert "https://deepscientist" in text
    assert style_asset.exists()


def test_paper_plot_skill_requires_template_copy_and_figure_polish_handoff() -> None:
    text = (repo_root() / "src" / "skills" / "paper-plot" / "SKILL.md").read_text(encoding="utf-8")
    openai_yaml = (repo_root() / "src" / "skills" / "paper-plot" / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "Trae1ounG/paper-plot-skills" in text
    assert "Follow the shared interaction contract injected by the system prompt." in text
    assert "keep the bundled template immutable" in text
    assert "hand the result to `figure-polish`" in text
    assert "bar, line, scatter, and radar" in text
    assert "display_name: \"Paper Plot\"" in openai_yaml


def test_idea_skill_requires_review_of_prior_ideas_and_experiment_outcomes() -> None:
    text = (repo_root() / "src" / "skills" / "idea" / "SKILL.md").read_text(encoding="utf-8")
    assert "review prior quest idea records and experiment outcomes" in text
    assert "reference material, not as the active idea contract" in text


def test_stage_skills_document_new_branch_lineage_semantics() -> None:
    idea_text = (repo_root() / "src" / "skills" / "idea" / "SKILL.md").read_text(encoding="utf-8")
    experiment_text = (repo_root() / "src" / "skills" / "experiment" / "SKILL.md").read_text(encoding="utf-8")
    decision_text = (repo_root() / "src" / "skills" / "decision" / "SKILL.md").read_text(encoding="utf-8")

    assert "lineage_intent='continue_line'" in idea_text
    assert "lineage_intent='branch_alternative'" in idea_text
    assert "new canvas node" in idea_text
    assert "maintenance-only compatibility" in idea_text

    assert "new durable idea branch" in experiment_text
    assert "fixed round node" in experiment_text
    assert "accepted idea -> `artifact.submit_idea(mode='create', lineage_intent='continue_line'|'branch_alternative', ...)`" in decision_text


def test_analysis_campaign_skill_requires_one_slice_campaign_for_single_extra_experiment() -> None:
    text = (repo_root() / "src" / "skills" / "analysis-campaign" / "SKILL.md").read_text(encoding="utf-8")
    assert "one-slice campaign" in text
    assert "durable lineage matters" in text
    assert "Use a lighter durable report when one bounded answer is enough" in text


def test_review_and_rebuttal_skills_route_extra_evidence_into_shared_campaign_protocol() -> None:
    review_text = (repo_root() / "src" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
    rebuttal_text = (repo_root() / "src" / "skills" / "rebuttal" / "SKILL.md").read_text(encoding="utf-8")

    assert "shared supplementary-experiment protocol" in review_text
    assert "one-slice campaign" in review_text
    assert "Do not invent a separate review-only experiment workflow." in review_text
    assert "paper/paper_experiment_matrix.md" in review_text

    assert "shared supplementary-experiment protocol" in rebuttal_text
    assert "do not invent a rebuttal-only experiment system" in rebuttal_text
    assert "artifact.resolve_runtime_refs(...)" in rebuttal_text
    assert "paper/paper_experiment_matrix.md" in rebuttal_text
