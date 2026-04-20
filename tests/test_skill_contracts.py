from __future__ import annotations

from deepscientist.home import repo_root


def _skill_text(skill_id: str) -> str:
    return (repo_root() / "src" / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8")


def _system_prompt_text() -> str:
    return (repo_root() / "src" / "prompts" / "system.md").read_text(encoding="utf-8")


def test_system_prompt_prioritizes_user_constraints_and_safe_efficiency() -> None:
    text = _system_prompt_text()

    assert "primary planning boundary" in text
    assert "best evidence-per-time-and-compute ratio" in text
    assert "For `comparison_ready`, `verify-local-existing`, attach, or import should usually beat full reproduction" in text
    assert "Do not weaken comparability, trust, or the meaning of the final result" in text
    assert "safe efficiency levers that preserve those constraints and the comparability contract" in text


def test_system_prompt_defines_metric_contract_rules_and_optional_metric_md() -> None:
    text = _system_prompt_text()

    assert "Keep the canonical `metrics_summary` flat at the top level" in text
    assert "Every canonical baseline metric entry should explain where it came from" in text
    assert "Every main experiment submission must cover all required baseline metric ids" in text
    assert "`Result/metric.md` may be used as temporary scratch memory" in text
    assert "A core metric contract is enough to confirm a comparison-ready baseline" in text
    assert "When using `artifact.confirm_baseline(...)`, keep two levels explicit" in text
    assert "If you compute an aggregate metric such as a mean, keep the aggregate as one metric" in text
    assert "Do not manually turn the actual message into a preview" in text


def test_system_prompt_budgets_smoke_checks_and_records_reusable_test_lessons() -> None:
    text = _system_prompt_text()

    assert "Treat smoke/pilot work as a stage-local budget of `0-2` runs" in text
    assert "A second smoke/pilot is justified only after a real change" in text
    assert "Search memory before reopening a previously tested command path" in text
    assert "If a smoke test, pilot, or cheap validation resolved a reusable fact" in text


def test_system_prompt_requires_checkpoint_style_memory_for_resume() -> None:
    text = _system_prompt_text()

    assert "Maintain at least one compact checkpoint-style quest memory card" in text
    assert "current route, strongest retained result or blocker, what not to reopen by default, next resume step, and which files should be read first" in text
    assert "current node history explicit" in text
    assert "which earlier node(s) or route(s) it superseded or was derived from" in text
    assert "update the checkpoint-style memory instead of leaving the old card to compete with fresher durable state" in text


def test_idea_skill_requires_survey_delta_and_memory_reuse_contract() -> None:
    text = _skill_text("idea")

    assert "artifacts/idea/literature_survey.md" in text
    assert "reused prior survey coverage" in text
    assert "newly added papers or comparisons from this pass" in text
    assert "still-missing or unresolved overlaps" in text
    assert "survey delta with retrieval hints" in text
    assert "Executive Summary" in text
    assert "Codebase Analysis" in text
    assert "utility_score" in text
    assert "quality_score" in text
    assert "exploration_score" in text
    assert "usually covers at least `5` and often `5-10`" in text
    assert "paper-ready idea packages" in text
    assert "smaller targeted survey can be enough" in text
    assert "standard citation format" in text
    assert "The selected idea draft must cite the survey papers" in text
    assert "references/idea-generation-playbook.md" in text
    assert "direction families, not a large within-family variant swarm" in text
    assert "Treat within-family micro-variants as `optimize` brief work" in text
    assert "selected / deferred / rejected outcomes explicitly" in text
    assert "one selected idea or selected direction family" in text
    assert "one-line rejection reason" in text
    assert "Set the frontier width with a validation-cost estimate before widening" in text
    assert "`fast-check`" in text
    assert "`slow-check`" in text
    assert "validation is cheaper than overthinking" in text
    assert "If DeepXiv is declared available by the system prompt" in text
    assert "If DeepXiv is declared unavailable, do not try to force it; stay on the legacy route." in text


def test_system_prompt_stays_compact_and_delegates_stage_sop() -> None:
    text = _system_prompt_text()

    assert "Stage-specific SOP belongs in the requested skill." in text
    assert "Do not restate large stage-specific playbooks" in text
    assert len(text.splitlines()) < 3500
    assert len(text) < 200000


def test_system_prompt_keeps_idea_vs_optimize_boundary_compact() -> None:
    text = _system_prompt_text()

    assert "Do not start route generation from a preferred mechanism when the active bottleneck is still underspecified." in text
    assert "When generating new routes, prefer a small differentiated frontier over many near-duplicate variants." in text
    assert "Match frontier width to validation cost: widen more when tests are cheap; gate harder when tests are slow or expensive." in text
    assert "Use `idea` for problem-framed direction families; use `optimize` for branchless candidate briefs, ranking, and promotion." in text


def test_system_prompt_restores_operational_mcp_and_mode_contracts() -> None:
    text = _system_prompt_text()

    assert "artifact.get_global_status(detail='brief'|'full')" in text
    assert "artifact.get_research_map_status(detail='summary'|'full')" in text
    assert "artifact.resolve_runtime_refs(...)" in text
    assert "artifact.get_method_scoreboard(...)" in text
    assert "recommended activation ref" in text
    assert "kind='answer'" in text
    assert "The default long-run monitoring cadence is about `60s -> 120s -> 300s -> 600s -> 1800s -> 1800s ...`" in text
    assert "`paper-plot`" in text
    assert "#### `review`" in text
    assert "#### `rebuttal`" in text
    assert "baseline_source_mode" in text
    assert "execution_start_mode" in text
    assert "baseline_acceptance_target" in text
    assert "algorithm-first optimization mode" not in text  # guard against stale naming drift
    assert "`algorithm_first` mode is the non-paper optimization mode" in text


def test_artifact_record_examples_match_payload_signature() -> None:
    system_text = _system_prompt_text()
    optimize_text = _skill_text("optimize")

    for text in (
        system_text,
        _skill_text("decision"),
        _skill_text("intake-audit"),
        _skill_text("review"),
        _skill_text("rebuttal"),
        optimize_text,
    ):
        assert "artifact.record(kind='" not in text

    assert "artifact.record(payload={kind: 'decision', ...})" in system_text
    assert "artifact.record(payload={kind: 'report', report_type: 'optimization_candidate', ...})" in system_text
    assert "artifact.record(payload={'kind': 'decision'" in optimize_text
    assert "artifact.record(payload={'kind': 'report'" in optimize_text


def test_system_prompt_restores_interaction_and_stage_protocols() -> None:
    text = _system_prompt_text()

    assert "### 7.6 Artifact interaction protocol" in text
    assert "`kind='answer'`" in text
    assert "`reply_to_interaction_id`" in text
    assert "`supersede_open_requests=True`" in text
    assert "`delivery_results` and `attachment_issues`" in text
    assert "`dedupe_key`, `suppress_if_unchanged`, and `min_interval_seconds`" in text
    assert "recommended_skill_reads" in text
    assert "### 14.3A Supplementary experiment protocol" in text
    assert "### 14.3B ID discipline" in text
    assert "### 14.3C Startup-contract delivery mode" in text
    assert "### 14.3D Artifact-managed Git contract" in text
    assert "#### `scout`" in text
    assert "#### `intake-audit`" in text
    assert "#### `decision`" in text
    assert "read `paper-plot` when measured numbers, arrays, or CSV-like results should become a paper-quality bar, line, scatter, or radar chart" in text
    assert "#### `figure-polish`" in text


def test_system_prompt_strengthens_bash_exec_only_terminal_contract() -> None:
    text = _system_prompt_text()

    assert "## 0. Hard execution redlines" in text
    assert "Native `shell_command` / `command_execution` is forbidden for this workflow." in text
    assert "Do not use `shell_command` even if the runner, model, or surface still exposes it." in text
    assert "All terminal or shell-like command execution must use `bash_exec`." in text
    assert "including `curl`, `python`, `python3`, `bash`, `sh`, `node`, `npm`, `uv`, `git`, `ls`, `cat`, `sed`" in text
    assert "Do not use any direct terminal, subprocess, or implicit shell path outside `bash_exec`." in text
    assert "Common `bash_exec` usage patterns:" in text
    assert "Terminal-command mapping examples:" in text
    assert "bash_exec(command='python -m pytest tests/test_x.py', mode='await', timeout_seconds=120, comment=...)" in text
    assert "bash_exec(mode='history')" in text
    assert "bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)" in text


def test_system_prompt_includes_stepwise_mode_operating_manuals() -> None:
    text = _system_prompt_text()

    assert "### 14.5A `paper_required` operating manual" in text
    assert "1. Recovery and route framing" in text
    assert "2. Baseline gate" in text
    assert "7. Writing line" in text
    assert "8. Skeptical audit and reviewer pressure" in text
    assert "9. Closure" in text
    assert "### 14.5B `algorithm_first` operating manual" in text
    assert "4. Frontier management and within-line optimization" in text
    assert "6. Post-result route judgment" in text
    assert "Must not drift into paper work by default." in text


def test_system_prompt_requires_outline_and_analysis_mapping_for_paper_work() -> None:
    text = _system_prompt_text()

    assert "authoritative paper contract" in text
    assert "paper experiment matrix" in text
    assert "experiments/analysis-results/" in text
    assert "repair that mapping before continuing drafting or finalize work" in text


def test_system_prompt_keeps_compact_reference_wording_templates() -> None:
    text = _system_prompt_text()

    assert "### 7.1 Reference wording" in text
    assert "These templates are references only." in text
    assert "Quick update:" in text
    assert "There's one fork I want to confirm before I continue" in text
    assert "我这边刚完成了" in text
    assert "这里有个分叉需要你确认" in text


def test_baseline_skill_prioritizes_hard_gates_over_fixed_paths() -> None:
    text = _skill_text("baseline")

    assert "## Authority and freedom" in text
    assert "The agent owns the execution path" in text
    assert "Do not treat templates, filenames, `uv`, smoke tests, detached runs, or the phase order as required paths" in text
    assert "## Hard acceptance gates" in text
    assert "Baseline success means later stages can compare against one accepted comparator without guessing" in text
    assert "the accepted comparison contract is written to `<baseline_root>/json/metric_contract.json`" in text
    assert "## Acceptance targets" in text
    assert "comparison_ready" in text
    assert "## Comparator-first rule" in text
    assert "comparator-first, not reproduction-first" in text
    assert "what is the lightest trustworthy comparator?" in text
    assert "## Route success criteria" in text
    assert "If a lighter route already satisfies the current acceptance target, stop there" in text
    assert "baseline should usually stop immediately and hand off to the next scientific step" in text
    assert "core metric contract" in text
    assert "Durable records are required in substance, not in fixed filenames" in text
    assert "`PLAN.md`, `CHECKLIST.md`, `setup.md`, `execution.md`, `verification.md`, `analysis_plan.md`, and `REPRO_CHECKLIST.md` are allowed compatibility surfaces, not mandatory success paths" in text
    assert "references/baseline-plan-template.md" in text
    assert "references/baseline-checklist-template.md" in text
    assert "A bounded smoke test is usually helpful only when" in text
    assert "Keep one dominant baseline route active at a time" in text
    assert "canonical starting point" in text
    assert "mark only the currently required canonical metrics as required" in text
    assert "flat top-level dictionary keyed by the paper-facing metric ids" in text
    assert "reuse that richer contract instead of hand-writing a thinner one" in text
    assert "`Result/metric.md` is optional temporary scratch memory only" in text
    assert "## Negative cases and stop rules" in text
    assert "same failure class reappears" in text
    assert "## Baseline id and variant rules" in text
    assert "references/artifact-payload-examples.md" in text


def test_experiment_skill_requires_incremental_seven_field_recording() -> None:
    text = _skill_text("experiment")

    assert "## Quick workflow" in text
    assert "## Required plan and checklist" in text
    assert "`PLAN.md` and `CHECKLIST.md`" in text
    assert "references/main-experiment-plan-template.md" in text
    assert "references/main-experiment-checklist-template.md" in text
    assert "selected idea summarized in `1-2` sentences" in text
    assert "minimal code-change map" in text
    assert "revise `PLAN.md` before spending more code or compute" in text
    assert "concise `1-2` sentence outcome summary" in text
    assert "rolling run log" in text or "rolling durable experiment log" in text
    assert "null hypothesis" in text
    assert "alternative hypothesis" in text
    assert "research question" in text
    assert "research type" in text
    assert "research objective" in text
    assert "experimental setup" in text
    assert "experimental results" in text
    assert "experimental analysis" in text
    assert "experimental conclusions" in text
    assert "Incremental-recording rule" in text
    assert "experiment tier: `auxiliary/dev` or `main/test`" in text
    assert "minimum -> solid -> maximum" in text
    assert "significance-testing plan" in text
    assert "evaluation_summary" in text
    assert "claim_update" in text
    assert "baseline_relation" in text
    assert "failure_mode" in text
    assert "next_action" in text
    assert "maximize valid evidence per unit time and compute" in text
    assert "equivalence-preserving efficiency upgrades" in text
    assert "For `comparison_ready`, `verify-local-existing`, attach, or import should usually beat full reproduction" in text
    assert "baseline comparability, treat it as a real experiment change" in text
    assert "one clean implementation pass and one real run" in text
    assert "implement according to the current `PLAN.md`" in text
    assert "extra metrics are allowed, but missing required metrics are not" in text
    assert "record it as supplementary output rather than replacing the canonical comparator" in text
    assert "artifact.record_main_experiment(...)" in text


def test_optimize_skill_distinguishes_candidate_briefs_lines_and_attempts() -> None:
    text = _skill_text("optimize")

    assert "submission_mode='candidate'" in text
    assert "submission_mode='line'" in text
    assert "`brief`" in text
    assert "`rank`" in text
    assert "`seed`" in text
    assert "`loop`" in text
    assert "`fusion`" in text
    assert "`debug`" in text
    assert "optimization_candidate" in text
    assert "artifact.get_optimization_frontier(...)" in text
    assert "Do not create a new Git branch/worktree for every implementation-level candidate." in text
    assert "Only promote a candidate brief into a durable line" in text
    assert "OPTIMIZE_CHECKLIST.md" in text
    assert "CANDIDATE_BOARD.md" in text
    assert "## Integrated reference appendix" in text
    assert "### optimize-checklist-template.md" in text
    assert "### candidate-board-template.md" in text
    assert "### method-brief-template.md" in text
    assert "### brief-shaping-playbook.md" in text
    assert "### candidate-ranking-template.md" in text
    assert "### frontier-review-template.md" in text
    assert "### optimization-memory-template.md" in text
    assert "### fusion-playbook.md" in text
    assert "### codegen-route-playbook.md" in text
    assert "### debug-response-template.md" in text
    assert "### prompt-patterns.md" in text
    assert "### plateau-response-playbook.md" in text
    assert "stepwise generation" in text
    assert "diff / patch generation" in text
    assert "full rewrite" in text
    assert "Mandatory first-call sequence" in text
    assert "artifact.get_optimization_frontier(...)" in text
    assert "memory.search(...)" in text
    assert "Stall-recovery protocol" in text
    assert "InternAgent maps most naturally" in text
    assert "MLEvolve maps most naturally" in text
    assert "Internal submode selection" in text
    assert "coverage contract" in text
    assert "distinct promotion policy" in text
    assert "mechanism family" in text
    assert "change-layer diversity" in text
    assert "clarify the bottleneck, constraints, and comparability boundary first" in text
    assert "generate a small differentiated slate, usually `2-3` serious approaches" in text
    assert "recommend one approach with explicit tradeoffs against the alternatives" in text
    assert "self-check the winning brief for ambiguity, overlap, and weak justification before submission" in text
    assert "why_now" in text
    assert "validation-cost-aware seed policy" in text
    assert "validation-cost-aware loop policy" in text
    assert "under about `20` minutes" in text
    assert "if the validation loop is slow, do not keep paying for frontier uncertainty that could have been reduced in `brief`" in text
    assert "gate evolution on clear objective signal" in text
    assert "a separate smoke stage is optional; direct submission into quick parallel validation is acceptable" in text
    assert "only skip smoke when the parallel quick validations are expected to produce distinguishable conclusions" in text
    assert "smoke test or direct quick validation" in text
    assert "you may skip a separate smoke stage and submit several quick validations in parallel" in text
    assert "Family-shift trigger" in text
    assert "Task-category primer" in text
    assert "simple-first" in text
    assert "one atomic improvement per pass" in text
    assert "bugfix-only" in text
    assert "same-line local attempt memory" in text


def test_algorithm_first_companion_skills_handoff_into_optimize() -> None:
    idea_text = _skill_text("idea")
    decision_text = _skill_text("decision")
    experiment_text = _skill_text("experiment")

    assert "Algorithm-first exception" in idea_text
    assert "optimization brief frontier" in idea_text
    assert "keep only a small differentiated `2-3` option slate" in idea_text
    assert "`artifact.get_optimization_frontier(...)`" in decision_text
    assert "frontier says `explore`" in decision_text
    assert "frontier says `fusion`" in decision_text
    assert "execution surface of `optimize`" in experiment_text
    assert "return to `optimize` or `decision` for frontier review" in experiment_text


def test_analysis_campaign_skill_prioritizes_evidence_boundary_over_fixed_paths() -> None:
    text = _skill_text("analysis-campaign")

    assert "## Authority and freedom" in text
    assert "The agent owns the analysis path" in text
    assert "Do not treat `PLAN.md`, `CHECKLIST.md`, `artifact.create_analysis_campaign(...)`, one-slice campaigns, returned worktrees, `evaluation_summary`, smoke tests, detached runs, or paper-matrix updates as universal required paths" in text
    assert "## Hard success gates" in text
    assert "An analysis campaign succeeds when it changes or confirms the evidence boundary of a parent claim" in text
    assert "every launched slice has a durable outcome" in text
    assert "## Slice evidence contract" in text
    assert "question, intervention or inspection target, fixed conditions, metric or observable, evidence path, claim update, comparability verdict, and next action" in text
    assert "## Comparability contract" in text
    assert "do not present the run as a direct apples-to-apples comparison" in text
    assert "## Durable route records" in text
    assert "`PLAN.md`, `CHECKLIST.md`, `paper/paper_experiment_matrix.md`, and local matrix/checklist files are allowed control surfaces, not mandatory success paths" in text
    assert "references/campaign-plan-template.md" in text
    assert "references/campaign-checklist-template.md" in text
    assert "slice feasibility, ordering, comparators, or campaign interpretation changes materially" in text
    assert "paper-ready slices must map cleanly back to a selected outline" in text
    assert "selected_outline_ref" in text
    assert "research_questions" in text
    assert "experimental_designs" in text
    assert "todo_items" in text
    assert "stable support" in text
    assert "contradiction" in text
    assert "claim-carrying" in text
    assert "supporting" in text
    assert "auxiliary" in text
    assert "comparison_baselines" in text
    assert "evaluation_summary" in text
    assert "takeaway" in text
    assert "comparability" in text
    assert "paper/paper_experiment_matrix.md" in text
    assert "`exp_id`" in text
    assert "section_id" in text
    assert "item_id" in text
    assert "claim_links" in text
    assert "paper_role" in text
    assert "highlight-validation" in text or "highlight validation" in text
    assert "efficiency or cost" in text
    assert "## Negative cases and stop rules" in text
    assert "a new main experiment is disguised as an analysis slice" in text
    assert "references/writing-facing-slice-examples.md" in text


def test_write_skill_prefers_flexible_outline_flow_and_bundle_submission() -> None:
    text = _skill_text("write")

    assert "record one or more outline candidates" in text
    assert "artifact.submit_paper_outline(mode='candidate', ...)" in text
    assert "artifact.submit_paper_outline(mode='select'|'revise', ...)" in text
    assert "artifact.submit_paper_bundle(...)" in text
    assert "do not force extra outline rounds" in text
    assert "paper/latex/" in text
    assert "templates/iclr2026/" in text
    assert "general ML or AI writing with no stronger venue constraint, default to `templates/iclr2026/`" in text
    assert "motivation" in text
    assert "challenge" in text
    assert "resolution" in text
    assert "validation" in text
    assert "impact" in text
    assert "experiment-to-section mapping" in text
    assert "figure/table-to-data-source mapping" in text
    assert "verification checkpoints" in text
    assert "paper/paper_experiment_matrix.md" in text
    assert "paper/paper_experiment_matrix.json" in text
    assert "when relevant analysis results are meant to support the active paper line" in text
    assert "current mapped paper evidence set" in text
    assert "do not allow completed analysis results to remain paper-invisible" in text
    assert "paper/evidence_ledger.json" in text or "paper/evidence_ledger.md" in text
    assert "references/outline-evidence-contract-example.md" in text
    assert "result_table" in text
    assert "stop drafting and repair the paper contract first" in text
    assert "references/paper-experiment-matrix-template.md" in text
    assert "highlight hypotheses" in text
    assert "efficiency / cost / latency / token-overhead checks" in text
    assert "currently feasible" in text
    assert "non-optional rows" in text
    assert "citation legitimacy" in text
    assert "file-structure audit" in text
    assert "Organize for the reader's understanding" in text
    assert "paper/reviewer_first_pass.md" in text
    assert "problem -> why it matters -> current bottleneck -> our remedy -> evidence preview" in text
    assert "problem" in text and "what we do" in text and "how at a high level" in text and "main result or strongest evidence" in text
    assert "running example -> intuition -> formalism" in text
    assert "This paper is organized as follows" in text
    assert "do not attack prior work merely to make the current line look more novel" in text
    assert "Publication-grade figure refinement is recommended with AutoFigure-Edit" in text
    assert "https://github.com/ResearAI/AutoFigure-Edit" in text
    assert "https://deepscientist" in text


def test_idea_skill_adds_problem_importance_and_first_principles_memo() -> None:
    text = _skill_text("idea")

    assert "the problem importance in one sentence" in text
    assert "the main challenge or bottleneck in one sentence" in text
    assert "whether the direction is emerging, stable, or late" in text
    assert "under-recognized" in text
    assert "a short first-principles memo" in text
    assert "references/outline-seeding-example.md" in text


def test_idea_skill_requires_bounded_divergence_and_why_now_checks() -> None:
    text = _skill_text("idea")

    assert "problem-first" in text
    assert "solution-first" in text
    assert "6-12" in text
    assert "usually `2-3`" in text or "usually 2 to 3" in text
    assert "strong durable evidence already narrows the route" in text
    assert "two-sentence pitch" in text
    assert "strongest-objection" in text or "strongest objection" in text
    assert "why now" in text
    assert "adjacent possible" in text
    assert "constraint manipulation" in text
    assert "negation or inversion" in text
    assert "composition / decomposition" in text


def test_idea_skill_documents_framework_selection_and_failure_recovery() -> None:
    text = _skill_text("idea")

    assert "Framework selection guide" in text
    assert "Integrated ideation workflow" in text
    assert "Treat it as a subroutine inside the main workflow" in text
    assert "Phase A. Diverge" in text
    assert "Phase B. Converge" in text
    assert "Phase C. Refine" in text
    assert "Common ideation failure modes and recovery moves" in text
    assert "premature convergence" in text
    assert "novelty without value" in text
    assert "false binary" in text


def test_finalize_and_decision_skills_require_bundle_and_outline_actions() -> None:
    finalize_text = _skill_text("finalize")
    decision_text = _skill_text("decision")

    assert "paper/paper_bundle_manifest.json" in finalize_text
    assert "paper/evidence_ledger.json" in finalize_text
    assert "evidence_ledger_path" in finalize_text
    assert "baseline_inventory_path" in finalize_text
    assert "release/open_source/manifest.json" in finalize_text
    assert "outline_path" in finalize_text
    assert "pdf_path" in finalize_text
    assert "artifact.submit_paper_outline(mode='select', ...)" in decision_text
    assert "artifact.submit_paper_bundle(...)" in decision_text
    assert "method fidelity" in decision_text
    assert "story coherence" in decision_text
    assert "belief-change log" in finalize_text
    assert "artifact.interact(kind='milestone'" in decision_text


def test_intake_audit_skill_requires_state_normalization_and_route_handoff() -> None:
    text = _skill_text("intake-audit")

    assert "startup_contract.launch_mode = custom" in text or "`startup_contract.launch_mode = custom`" in text
    assert "entry_state_summary" in text
    assert "review_summary" in text
    assert "custom_brief" in text
    assert "state-audit-template.md" in text
    assert "trust-rank" in text
    assert "route to `rebuttal`" in text or "handoff to `rebuttal`" in text
    assert "memory.write" in text


def test_rebuttal_skill_requires_review_matrix_response_bundle_and_memory() -> None:
    text = _skill_text("rebuttal")

    assert "paper/rebuttal/review_matrix.md" in text
    assert "paper/rebuttal/action_plan.md" in text
    assert "paper/rebuttal/response_letter.md" in text
    assert "paper/rebuttal/text_deltas.md" in text
    assert "paper/rebuttal/evidence_update.md" in text
    assert "paper/paper_experiment_matrix.md" in text
    assert "paper/paper_experiment_matrix.json" in text
    assert "review-matrix-template.md" in text
    assert "action-plan-template.md" in text
    assert "evidence-update-template.md" in text
    assert "response-letter-template.md" in text
    assert "R1-C1" in text
    assert "analysis before execution" in text
    assert "Do not invent rebuttal-only special tools" in text
    assert "MVP plan" in text
    assert "Enhanced plan" in text
    assert "analysis-experiment TODO list" in text
    assert "`exp_id`" in text
    assert "component_ablation" in text
    assert "efficiency_cost" in text
    assert "[[AUTHOR TO FILL]]" in text
    assert "scout" in text
    assert "baseline" in text
    assert "analysis-campaign" in text
    assert "write" in text
    assert "memory.write" in text
    assert "evaluation_summary" in text
    assert "calm, direct, precise author voice" in text
    assert "1 to 2 full paragraphs" in text
    assert "local file paths" in text or "local paths" in text
    assert "neutral reviewer or AC" in text
    assert "strengths recognized across reviewers" in text


def test_review_skill_requires_independent_audit_outputs_and_followup_routing() -> None:
    text = _skill_text("review")

    assert "independent skeptical audit" in text
    assert "paper/review/review.md" in text
    assert "paper/review/revision_log.md" in text
    assert "paper/review/experiment_todo.md" in text
    assert "paper/paper_experiment_matrix.md" in text
    assert "paper/paper_experiment_matrix.json" in text
    assert "review-report-template.md" in text
    assert "revision-log-template.md" in text
    assert "experiment-todo-template.md" in text
    assert "C1" in text and "C2" in text and "C3" in text
    assert "scout" in text
    assert "baseline" in text
    assert "analysis-campaign" in text
    assert "write" in text
    assert "memory.write" in text
    assert "evaluation_summary" in text
    assert "review_followup_policy" in text
    assert "manuscript_edit_mode" in text
    assert "latex_required" in text
    assert "matrix exp id" in text
    assert "highlight hypotheses" in text
    assert "copy-ready replacement sentence" in text or "copy-ready replacement" in text


def test_decision_and_finalize_skills_require_checkpoint_style_memory_when_resume_state_changes() -> None:
    decision_text = _skill_text("decision")
    finalize_text = _skill_text("finalize")

    assert "write one compact checkpoint-style quest memory card" in decision_text
    assert "current active node" in decision_text
    assert "node history" in decision_text
    assert "what not to reopen by default" in decision_text
    assert "first files to read" in decision_text
    assert "type:checkpoint-memory" in decision_text
    assert "references/checkpoint-memory-template.md" in decision_text

    assert "write or refresh one compact checkpoint-style quest memory card" in finalize_text
    assert "mirrors the live resume packet" in finalize_text
    assert "current active node" in finalize_text
    assert "node history" in finalize_text
    assert "type:checkpoint-memory" in finalize_text
    assert "references/checkpoint-memory-template.md" in finalize_text
    assert "if the quest is stopping at continue-later / pause-ready rather than true completion" in finalize_text


def test_finalize_resume_and_checkpoint_templates_require_current_node_history() -> None:
    repo = repo_root()
    resume_template = (repo / "src" / "skills" / "finalize" / "references" / "resume-packet-template.md").read_text(encoding="utf-8")
    checkpoint_template = (repo / "src" / "skills" / "finalize" / "references" / "checkpoint-memory-template.md").read_text(encoding="utf-8")
    decision_checkpoint_template = (repo / "src" / "skills" / "decision" / "references" / "checkpoint-memory-template.md").read_text(encoding="utf-8")

    assert "### 1A. Current node history" in resume_template
    for text in (checkpoint_template, decision_checkpoint_template):
        assert "## Recommended structure" in text
        assert "### 2. Current active node" in text
        assert "### 3. Node history" in text
        assert "superseded node(s)" in text or "superseded completion" in text


def test_stage_skill_progress_contracts_match_tool_call_keepalive_policy() -> None:
    aligned_skills = (
        "intake-audit",
        "idea",
        "optimize",
        "experiment",
        "analysis-campaign",
        "write",
        "finalize",
        "decision",
        "review",
        "rebuttal",
        "scout",
    )

    for skill_id in aligned_skills:
        text = _skill_text(skill_id)
        assert "roughly 12 tool calls or about 8 minutes" in text
        assert "Do not update by tool-call cadence." not in text


def test_experiment_and_analysis_skills_require_smoke_then_detach_tail_monitoring() -> None:
    experiment_text = _skill_text("experiment")
    analysis_text = _skill_text("analysis-campaign")
    baseline_text = _skill_text("baseline")

    for text in (experiment_text, analysis_text):
        assert "smoke test" in text
        assert "bash_exec(mode='detach', ...)" in text
        assert "2000 lines or fewer" in text
        assert ("first 500 lines plus the last 1500 lines" in text) or ("first 500 lines plus last 1500 lines" in text)
        assert "bash_exec(mode='read', id=..., start=..., tail=...)" in text
        assert "tail_limit=..., order='desc'" in text
        assert "after_seq=last_seen_seq" in text
        assert "bash_exec(mode='history')" in text
        assert "same failure class appears again" in text
        assert "bash_exec(mode='kill', id=..., wait=true, timeout_seconds=...)" in text
        assert "canonical sleep choice" in text
        assert "bash_exec(command='sleep N', mode='await', timeout_seconds=N+buffer, ...)" in text
        assert "do not set `timeout_seconds` exactly equal to `N`" in text
        assert "prefer `bash_exec(mode='await', id=..., timeout_seconds=...)` instead of starting a new sleep command" in text

    assert "verify-local-existing" in baseline_text
    assert "same failure class appears again" in baseline_text
    assert "acceptance target" in baseline_text
    assert "`0-2` budget" in experiment_text
    assert "`0-2`" in analysis_text
    assert "`0-2` default budget" in baseline_text

    assert "smoke test" in baseline_text
    assert "bash_exec(mode='detach', ...)" in baseline_text
    assert "tqdm" in experiment_text
    assert "tqdm" in analysis_text


def test_baseline_skill_prefers_fast_path_over_upfront_ceremony() -> None:
    text = _skill_text("baseline")

    assert "Default to the lightest baseline path" in text
    assert "Default to a fast path when it can establish trust with less work" in text
    assert "do not restart broad baseline discovery by default" in text
    assert "do not front-load a full codebase audit" in text
    assert "A bounded smoke test is usually helpful only when" in text
    assert "Treat smoke/pilot work as a `0-2` default budget" in text
    assert "not to repeat an unchanged check without new evidence" in text
    assert "do not require a fresh memory pass for every fast-path validation" in text
    assert "The comparison-ready minimum still requires `<baseline_root>/json/metric_contract.json`" in text
    assert "references/comparability-contract.md" in text
    assert len(text.splitlines()) < 700
    assert len(text) < 32500


def test_baseline_artifact_payload_reference_exists_and_stays_compact() -> None:
    path = repo_root() / "src" / "skills" / "baseline" / "references" / "artifact-payload-examples.md"
    text = path.read_text(encoding="utf-8")

    assert path.exists()
    assert "Route or blocked decision" in text
    assert "Accepted baseline" in text
    assert "`metrics_summary`" in text or "metrics_summary" in text
    assert len(text.splitlines()) < 80


def test_system_prompt_keeps_the_global_kernel_small() -> None:
    text = _system_prompt_text()

    assert "This system prompt is the compact global kernel" in text
    assert "The runtime tells you the `requested_skill`; open that skill before substantive stage work." in text


def test_scout_skill_mentions_deepxiv_fallback_contract() -> None:
    text = _skill_text("scout")

    assert "If DeepXiv is declared available by the system prompt" in text
    assert "If DeepXiv is declared unavailable, stay on the legacy route" in text
    assert "artifact.arxiv(paper_id=..., full_text=False)" in text


def test_write_skill_mentions_deepxiv_fallback_contract() -> None:
    text = _skill_text("write")

    assert "If DeepXiv is declared available by the system prompt" in text
    assert "If DeepXiv is declared unavailable, do not try to force it; stay on the legacy route." in text
    assert "artifact.arxiv(paper_id=..., full_text=False)" in text
