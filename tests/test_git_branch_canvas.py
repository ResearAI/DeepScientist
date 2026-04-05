from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.metrics import build_metrics_timeline
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.gitops import checkpoint_repo
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import run_command, write_json, write_text
from deepscientist.skills import SkillInstaller


def _confirm_local_baseline(artifact: ArtifactService, quest_root: Path, baseline_id: str = "baseline-local") -> None:
    baseline_root = quest_root / "baselines" / "local" / baseline_id
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id=baseline_id,
        summary=f"Confirmed {baseline_id}",
        metrics_summary={"acc": 0.8},
        primary_metric={"name": "acc", "value": 0.8},
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [{"metric_id": "acc", "direction": "higher"}],
        },
    )


def _write_run_artifact(
    quest_root: Path,
    *,
    run_id: str,
    branch: str,
    base: str,
    head: str,
    workspace_root: Path,
) -> None:
    run_root = quest_root / ".ds" / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    write_json(
        run_root / "artifact.json",
        {
            "ok": True,
            "workspace_root": str(workspace_root),
            "record": {
                "run_id": run_id,
                "branch": branch,
                "head_commit": base,
                "workspace_root": str(workspace_root),
            },
            "checkpoint": {
                "head": head,
            },
        },
    )


def test_git_branch_canvas_distinguishes_major_and_analysis_branches(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("branch canvas quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    idea_branch = artifact.prepare_branch(
        quest_root,
        idea_id="idea-001",
        branch_kind="idea",
        create_worktree_flag=False,
    )
    assert idea_branch["parent_branch"] == "main"

    run_command(["git", "checkout", idea_branch["branch"]], cwd=quest_root, check=True)
    write_text(quest_root / "plan.md", "# Idea branch\n\nPromote this idea.\n")
    checkpoint_repo(quest_root, "idea branch update", allow_empty=False)
    artifact.record(
        quest_root,
        {
            "kind": "decision",
            "verdict": "continue",
            "action": "branch",
            "reason": "The first idea is worth implementing.",
            "summary": "Promoted idea-001 to implementation.",
            "idea_id": "idea-001",
        },
    )

    main_branch = artifact.prepare_branch(
        quest_root,
        run_id="main-exp-001",
        branch_kind="run",
        create_worktree_flag=False,
    )
    assert main_branch["parent_branch"] == idea_branch["branch"]

    run_command(["git", "checkout", main_branch["branch"]], cwd=quest_root, check=True)
    write_text(quest_root / "status.md", "# Main experiment\n\nacc: 0.91\n")
    checkpoint_repo(quest_root, "main experiment update", allow_empty=False)
    artifact.record(
        quest_root,
        {
            "kind": "run",
            "run_id": "main-exp-001",
            "run_kind": "experiment",
            "summary": "Main implementation improved the baseline.",
            "metrics_summary": {"acc": 0.91, "f1": 0.88},
        },
    )

    analysis_branch = artifact.prepare_branch(
        quest_root,
        run_id="analysis-001",
        branch_kind="run",
        create_worktree_flag=False,
    )
    assert analysis_branch["parent_branch"] == main_branch["branch"]

    run_command(["git", "checkout", analysis_branch["branch"]], cwd=quest_root, check=True)
    write_text(quest_root / "experiments" / "analysis" / "report.md", "# Ablation\n\nAnalysis details here.\n")
    checkpoint_repo(quest_root, "analysis branch update", allow_empty=False)
    artifact.record(
        quest_root,
        {
            "kind": "run",
            "run_id": "analysis-001",
            "run_kind": "analysis-campaign",
            "summary": "Ablation branch explored robustness.",
            "metrics_summary": {"acc": 0.89},
        },
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}

    assert nodes["main"]["branch_kind"] == "quest"
    assert nodes[idea_branch["branch"]]["branch_kind"] == "idea"
    assert nodes[idea_branch["branch"]]["tier"] == "major"
    assert nodes[main_branch["branch"]]["branch_kind"] == "implementation"
    assert nodes[analysis_branch["branch"]]["branch_kind"] == "analysis"
    assert nodes[analysis_branch["branch"]]["tier"] == "minor"
    assert nodes[analysis_branch["branch"]]["parent_ref"] == main_branch["branch"]
    assert nodes[analysis_branch["branch"]]["latest_metric"]["key"] == "acc"

    compare = app.handlers.git_compare(
        quest_id,
        path=f"/api/quests/{quest_id}/git/compare?base={quote(main_branch['branch'])}&head={quote(analysis_branch['branch'])}",
    )
    assert compare["ok"] is True
    assert any(item["path"] == "experiments/analysis/report.md" for item in compare["files"])

    log_payload = app.handlers.git_log(
        quest_id,
        path=f"/api/quests/{quest_id}/git/log?ref={quote(analysis_branch['branch'])}&base={quote(main_branch['branch'])}&limit=10",
    )
    assert log_payload["ok"] is True
    assert log_payload["commits"]
    target_sha = None
    for item in log_payload["commits"]:
        detail = app.handlers.git_commit(
            quest_id,
            path=f"/api/quests/{quest_id}/git/commit?sha={quote(item['sha'])}",
        )
        if any(file_item["path"] == "experiments/analysis/report.md" for file_item in detail["files"]):
            target_sha = item["sha"]
            break
    assert target_sha is not None

    commit_payload = app.handlers.git_commit(
        quest_id,
        path=f"/api/quests/{quest_id}/git/commit?sha={quote(target_sha)}",
    )
    assert commit_payload["ok"] is True
    assert commit_payload["sha"] == target_sha
    assert any(item["path"] == "experiments/analysis/report.md" for item in commit_payload["files"])

    diff = app.handlers.git_diff_file(
        quest_id,
        path=(
            f"/api/quests/{quest_id}/git/diff-file?base={quote(main_branch['branch'])}"
            f"&head={quote(analysis_branch['branch'])}&path={quote('experiments/analysis/report.md')}"
        ),
    )
    assert diff["ok"] is True
    assert diff["path"] == "experiments/analysis/report.md"
    assert any("Analysis details here." in line for line in diff["lines"])

    commit_diff = app.handlers.git_commit_file(
        quest_id,
        path=f"/api/quests/{quest_id}/git/commit-file?sha={quote(target_sha)}&path={quote('experiments/analysis/report.md')}",
    )
    assert commit_diff["ok"] is True
    assert commit_diff["path"] == "experiments/analysis/report.md"
    assert any("Analysis details here." in line for line in commit_diff["lines"])


def test_git_branch_canvas_reads_artifacts_from_worktrees(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("worktree canvas quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root)

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A lightweight adapter helps.",
        mechanism="Insert a residual adapter.",
        decision_reason="Promote the strongest current route.",
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Ablation suite",
        campaign_goal="Stress-test the promoted idea.",
        slices=[
            {
                "slice_id": "ablation",
                "title": "Adapter ablation",
                "goal": "Disable the adapter and compare.",
                "required_changes": "Disable adapter only.",
                "metric_contract": "Report full validation metrics.",
            }
        ],
    )
    artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the adapter only.",
        execution="Ran the full validation sweep.",
        results="Accuracy dropped as expected.",
        metric_rows=[{"name": "acc", "value": 0.84}],
        evidence_paths=["experiments/analysis/ablation/result.json"],
        evaluation_summary={
            "takeaway": "The ablation removes the observed gain.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    analysis_branch = campaign["slices"][0]["branch"]

    assert nodes[idea["branch"]]["branch_kind"] == "idea"
    assert nodes[idea["branch"]]["branch_no"] == "001"
    assert nodes[idea["branch"]]["idea_title"] == "Adapter route"
    assert nodes[idea["branch"]]["lineage_intent"] == "continue_line"
    assert nodes[idea["branch"]]["parent_branch"] == "main"
    assert nodes[idea["branch"]]["idea_draft_path"].endswith("/draft.md")
    assert nodes[idea["branch"]]["foundation_ref"]["kind"] == "current_head"
    assert nodes[analysis_branch]["branch_kind"] == "analysis"
    assert nodes[analysis_branch]["latest_metric"]["key"] == "acc"
    assert nodes[analysis_branch]["worktree_root"] == campaign["slices"][0]["worktree_root"]
    assert nodes[analysis_branch]["latest_result"]["evaluation_summary"]["next_action"] == "write"


def test_git_branch_canvas_supports_copilot_workspace_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "copilot branch canvas quest",
        startup_contract={"workspace_mode": "copilot"},
    )
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-copilot-canvas")

    first_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Copilot adapter route",
        problem="Need a branch graph even when the quest is parked in copilot mode.",
        hypothesis="The copilot workspace should still expose the same durable branch graph.",
        mechanism="Create and promote the first durable idea branch.",
        decision_reason="Open the first implementation route from copilot mode.",
    )
    main_result = artifact.record_main_experiment(
        quest_root,
        run_id="main-copilot-001",
        title="Copilot main run",
        hypothesis="The copilot branch improved the primary metric.",
        setup="Use the confirmed baseline recipe.",
        execution="Ran the main validation sweep once.",
        results="Accuracy improved over baseline.",
        conclusion="Use this run as the next durable foundation.",
        metric_rows=[{"metric_id": "acc", "value": 0.91, "direction": "higher_better"}],
    )
    second_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Run-informed copilot route",
        problem="Need a follow-up branch from the measured main run.",
        hypothesis="The measured run is the right foundation for the next route.",
        mechanism="Continue from the best measured run in the same parked workspace.",
        decision_reason="Continue from the strongest measured branch.",
        foundation_ref={"kind": "run", "ref": "main-copilot-001"},
        foundation_reason="Carry forward the strongest measured branch.",
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    edges = branches["edges"]

    assert branches["workspace_mode"] == "copilot"
    assert nodes[first_idea["branch"]]["branch_no"] == "001"
    assert nodes[first_idea["branch"]]["idea_title"] == "Copilot adapter route"
    assert nodes["run/main-copilot-001"]["latest_main_experiment"]["run_id"] == main_result["run_id"]
    assert nodes[second_idea["branch"]]["branch_no"] == "002"
    assert nodes[second_idea["branch"]]["foundation_ref"]["kind"] == "run"
    assert nodes[second_idea["branch"]]["foundation_ref"]["ref"] == "main-copilot-001"
    assert nodes[second_idea["branch"]]["foundation_reason"] == "Carry forward the strongest measured branch."
    assert any(
        edge["from"] == "run/main-copilot-001" and edge["to"] == second_idea["branch"]
        for edge in edges
    )


def test_git_branch_canvas_dedupes_mirrored_main_experiment_counts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("worktree main run dedupe quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root)

    parent = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Primary route",
        problem="Baseline saturates.",
        hypothesis="A lightweight adapter helps.",
        mechanism="Insert a residual adapter.",
        decision_reason="Promote the strongest current route.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-dedupe-001",
        title="Primary route main run",
        hypothesis="The promoted route is strong enough for a measured run.",
        setup="Standard validation recipe.",
        execution="Ran the main experiment once.",
        results="The primary route improved accuracy.",
        conclusion="Use the result as the next foundation.",
        metric_rows=[{"metric_id": "acc", "value": 0.86}],
    )
    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Follow-up route",
        problem="Continue from the best measured result.",
        hypothesis="A second route can build on the measured gain.",
        mechanism="Branch from the durable main result.",
        decision_reason="Create a child route from the promoted evidence.",
        foundation_ref={"kind": "run", "ref": "main-dedupe-001"},
        foundation_reason="Build on the best measured run.",
        next_target="experiment",
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}

    assert nodes["run/main-dedupe-001"]["latest_result"]["run_id"] == "main-dedupe-001"
    assert nodes["run/main-dedupe-001"]["parent_ref"] == parent["branch"]


def test_git_branch_canvas_preserves_structured_main_result_over_later_unstructured_run(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("branch canvas structured result quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-structured-result")

    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Structured result route",
        problem="Canvas should keep the recorded experiment metrics visible.",
        hypothesis="A later bookkeeping run must not overwrite the measured result payload.",
        mechanism="Prefer structured experiment artifacts over plain follow-up run records.",
        decision_reason="Open the route for a measured experiment.",
    )
    main_result = artifact.record_main_experiment(
        quest_root,
        run_id="main-structured-001",
        title="Structured main run",
        hypothesis="The structured run provides the real branch result.",
        setup="Use the confirmed baseline recipe.",
        execution="Ran the comparable validation pass once.",
        results="The structured main result improved the primary metric.",
        conclusion="Keep this durable result visible on the branch canvas.",
        metric_rows=[{"metric_id": "acc", "value": 0.91, "direction": "higher_better"}],
        evaluation_summary={
            "takeaway": "The structured main result is the real branch result.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )
    run_worktree_root = str(main_result["artifact"]["record"]["worktree_root"])
    artifact.record(
        quest_root,
        {
            "kind": "run",
            "run_id": "agent-followup-001",
            "run_kind": "idea",
            "branch": main_result["branch"],
            "worktree_root": run_worktree_root,
            "status": "completed",
            "summary": "A later follow-up agent run wrote notes on the same branch.",
        },
        checkpoint=False,
        workspace_root=Path(run_worktree_root),
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    run_node = nodes[main_result["branch"]]

    assert run_node["run_id"] == "main-structured-001"
    assert run_node["run_kind"] == "main_experiment"
    assert run_node["latest_result"]["run_id"] == "main-structured-001"
    assert run_node["latest_result"]["metrics_summary"] == {"acc": 0.91}
    assert run_node["latest_result"]["evaluation_summary"]["next_action"] == "write"
    assert run_node["latest_metric"]["key"] == "acc"
    assert run_node["latest_metric"]["value"] == pytest.approx(0.91)
    assert run_node["latest_summary"] == "A later follow-up agent run wrote notes on the same branch."


def test_git_branch_canvas_keeps_latest_metric_aligned_with_selected_structured_result(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("branch canvas metric alignment quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-metric-alignment")

    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Metric alignment route",
        problem="Canvas metric badges should match the selected structured branch result.",
        hypothesis="A later weaker run with its own metric must not replace the branch metric badge.",
        mechanism="Force latest_metric to follow the chosen structured branch result when one exists.",
        decision_reason="Open the route for a measured experiment.",
    )
    main_result = artifact.record_main_experiment(
        quest_root,
        run_id="main-metric-align-001",
        title="Metric alignment main run",
        hypothesis="The measured branch result should remain the source of truth.",
        setup="Use the confirmed baseline recipe.",
        execution="Ran the comparable validation pass once.",
        results="The structured main result improved the primary metric.",
        conclusion="Keep the branch metric aligned with this durable result.",
        metric_rows=[{"metric_id": "acc", "value": 0.91, "direction": "higher_better"}],
        evaluation_summary={
            "takeaway": "The structured main result should own the branch metric badge.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )
    run_worktree_root = str(main_result["artifact"]["record"]["worktree_root"])
    artifact.record(
        quest_root,
        {
            "kind": "run",
            "run_id": "agent-followup-metric-001",
            "run_kind": "idea",
            "branch": main_result["branch"],
            "worktree_root": run_worktree_root,
            "status": "completed",
            "summary": "A later follow-up run reported a lower temporary metric.",
            "metric_rows": [{"metric_id": "acc", "value": 0.55, "direction": "higher_better"}],
            "metrics_summary": {"acc": 0.55},
        },
        checkpoint=False,
        workspace_root=Path(run_worktree_root),
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    run_node = nodes[main_result["branch"]]

    assert run_node["latest_result"]["run_id"] == "main-metric-align-001"
    assert run_node["latest_metric"]["key"] == "acc"
    assert run_node["latest_metric"]["value"] == pytest.approx(0.91)


def test_file_change_diff_falls_back_to_run_commit_range_for_quest_root(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("file change diff quest root")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    target = quest_root / "plan.md"
    write_text(target, "# Plan\n\nQuest-root base change.\n")
    base = checkpoint_repo(quest_root, "quest root diff base", allow_empty=False)["head"]
    write_text(target, "# Plan\n\nQuest-root head change.\n")
    head = checkpoint_repo(quest_root, "quest root diff head", allow_empty=False)["head"]
    _write_run_artifact(
        quest_root,
        run_id="run-file-change-root",
        branch="main",
        base=base,
        head=head,
        workspace_root=quest_root,
    )

    app = DaemonApp(temp_home)
    diff = app.handlers.file_change_diff(
        quest_id,
        path=(
            f"/api/quests/{quest_id}/operations/file-change-diff?run_id=run-file-change-root"
            f"&path={quote(str(target))}&event_id=evt-root"
        ),
    )

    assert diff["ok"] is True
    assert diff["available"] is True
    assert diff["source"] == "run_range"
    assert diff["path"] == "plan.md"
    assert diff["display_path"] == "plan.md"
    assert diff["run_id"] == "run-file-change-root"
    assert diff["event_id"] == "evt-root"
    assert any("Quest-root head change." in line for line in diff["lines"])


def test_file_change_diff_falls_back_to_run_commit_range_for_worktree_root(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("file change diff worktree root")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    prepared = artifact.prepare_branch(
        quest_root,
        run_id="run-file-change-worktree",
        branch_kind="run",
        create_worktree_flag=True,
    )
    worktree_root = Path(str(prepared["worktree_root"]))
    target = worktree_root / "plan.md"
    write_text(target, "# Plan\n\nWorktree base change.\n")
    base = checkpoint_repo(worktree_root, "worktree diff base", allow_empty=False)["head"]
    write_text(target, "# Plan\n\nWorktree head change.\n")
    head = checkpoint_repo(worktree_root, "worktree diff head", allow_empty=False)["head"]
    _write_run_artifact(
        quest_root,
        run_id="run-file-change-worktree",
        branch=str(prepared["branch"]),
        base=base,
        head=head,
        workspace_root=worktree_root,
    )

    app = DaemonApp(temp_home)
    diff = app.handlers.file_change_diff(
        quest_id,
        path=(
            f"/api/quests/{quest_id}/operations/file-change-diff?run_id=run-file-change-worktree"
            f"&path={quote(str(target))}&event_id=evt-worktree"
        ),
    )

    assert diff["ok"] is True
    assert diff["available"] is True
    assert diff["source"] == "run_range"
    assert diff["path"] == "plan.md"
    assert str(diff["display_path"]).endswith("/plan.md")
    assert diff["branch"] == prepared["branch"]
    assert any("Worktree head change." in line for line in diff["lines"])


def test_file_change_diff_reports_unavailable_when_file_is_not_in_final_run_diff(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("file change diff unavailable")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    changed_path = quest_root / "status.md"
    untouched_path = quest_root / "plan.md"
    write_text(changed_path, "# Status\n\nOnly this file changes in base.\n")
    base = checkpoint_repo(quest_root, "unavailable diff base", allow_empty=False)["head"]
    write_text(changed_path, "# Status\n\nOnly this file changes in head.\n")
    head = checkpoint_repo(quest_root, "unavailable diff head", allow_empty=False)["head"]
    _write_run_artifact(
        quest_root,
        run_id="run-file-change-unavailable",
        branch="main",
        base=base,
        head=head,
        workspace_root=quest_root,
    )

    app = DaemonApp(temp_home)
    diff = app.handlers.file_change_diff(
        quest_id,
        path=(
            f"/api/quests/{quest_id}/operations/file-change-diff?run_id=run-file-change-unavailable"
            f"&path={quote(str(untouched_path))}&event_id=evt-unavailable"
        ),
    )

    assert diff["ok"] is True
    assert diff["available"] is False
    assert diff["source"] == "unavailable"
    assert diff["path"] == "plan.md"
    assert "final checkpoint" in str(diff["message"])


def test_git_branch_canvas_marks_breakthrough_and_metrics_timeline(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("branch breakthrough quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-graph"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Graph baseline\n", encoding="utf-8")

    artifact.record(
        quest_root,
        {
            "kind": "baseline",
            "publish_global": True,
            "baseline_id": "baseline-graph",
            "name": "Graph baseline",
            "primary_metric": {"name": "acc", "value": 0.8},
            "metrics_summary": {"acc": 0.8},
            "baseline_variants": [{"variant_id": "main", "label": "Main", "metrics_summary": {"acc": 0.8}}],
            "default_variant_id": "main",
        },
    )
    artifact.attach_baseline(quest_root, "baseline-graph", "main")
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/imported/baseline-graph",
        baseline_id="baseline-graph",
        variant_id="main",
        summary="Baseline graph confirmed",
    )
    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A lightweight adapter helps.",
        mechanism="Insert a residual adapter.",
        decision_reason="Promote the strongest current route.",
    )
    worktree_root = Path(idea["worktree_root"])
    write_text(worktree_root / "status.md", "# Main experiment\n\nacc: 0.86\n")

    artifact.record_main_experiment(
        quest_root,
        run_id="main-graph-001",
        title="Graph main run",
        hypothesis="Adapter improves accuracy.",
        setup="Baseline recipe.",
        execution="Ran full validation.",
        results="Accuracy improved.",
        conclusion="Good enough for follow-up.",
        metric_rows=[{"metric_id": "acc", "value": 0.86}],
        evaluation_summary={
            "takeaway": "The graph test branch beats the baseline on accuracy.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}

    assert nodes["run/main-graph-001"]["breakthrough"] is True
    assert nodes["run/main-graph-001"]["breakthrough_level"] in {"minor", "major"}
    assert nodes["run/main-graph-001"]["latest_result"]["run_id"] == "main-graph-001"
    assert nodes["run/main-graph-001"]["latest_metric"]["delta_vs_baseline"] == pytest.approx(0.06)
    assert nodes["run/main-graph-001"]["latest_result"]["evaluation_summary"]["claim_update"] == "strengthens"

    timeline = app.handlers.metrics_timeline(quest_id)
    assert timeline["primary_metric_id"] == "acc"
    acc_series = next(item for item in timeline["series"] if item["metric_id"] == "acc")
    assert acc_series["points"][0]["value"] == 0.86
    assert acc_series["points"][0]["breakthrough"] is True
    assert acc_series["baselines"][0]["value"] == 0.8


def test_metrics_timeline_dedupes_mirrored_run_records_and_keeps_numeric_metric_rows() -> None:
    baseline_entry = {
        "baseline_id": "baseline-mirror",
        "metrics_summary": {"sigma_max": 0.6921, "raw_false": 0.2149},
        "primary_metric": {"name": "sigma_max", "value": 0.6921},
        "metric_contract": {
            "primary_metric_id": "sigma_max",
            "metrics": [
                {"metric_id": "sigma_max", "direction": "lower"},
                {"metric_id": "raw_false", "direction": "lower"},
            ],
        },
    }
    older = {
        "run_id": "mirror-001",
        "artifact_id": "artifact-old",
        "updated_at": "2026-01-01T00:00:00Z",
        "metrics_summary": {
            "headline": "Favorable overall.",
            "primary_metric": {"metric_id": "sigma_max", "value": 0.2477},
        },
        "metric_rows": [
            {"metric_id": "sigma_max", "value": 0.2477, "delta": -0.4444, "direction": "lower_better"},
        ],
        "metric_contract": {
            "primary_metric_id": "sigma_max",
            "metrics": [{"metric_id": "headline"}, {"metric_id": "sigma_max"}],
        },
        "baseline_comparisons": {
            "primary_metric_id": "sigma_max",
            "items": [{"metric_id": "sigma_max", "delta": -0.4444, "direction": "lower"}],
        },
        "progress_eval": {"primary_metric_id": "sigma_max"},
    }
    newer = {
        **older,
        "artifact_id": "artifact-new",
        "updated_at": "2026-01-02T00:00:00Z",
        "metric_rows": [
            {"metric_id": "sigma_max", "value": 0.2477, "delta": -0.4444, "direction": "lower_better"},
            {"metric_id": "raw_false", "value": 0.2063, "delta": -0.0086, "direction": "lower_better"},
        ],
        "baseline_comparisons": {
            "primary_metric_id": "sigma_max",
            "items": [
                {"metric_id": "sigma_max", "delta": -0.4444, "direction": "lower"},
                {"metric_id": "raw_false", "delta": -0.0086, "direction": "lower"},
            ],
        },
    }

    timeline = build_metrics_timeline(
        quest_id="quest-mirror",
        run_records=[older, newer],
        baseline_entry=baseline_entry,
        selected_variant_id=None,
    )

    assert timeline["total_runs"] == 1
    series_by_id = {item["metric_id"]: item for item in timeline["series"]}
    assert set(series_by_id.keys()) == {"sigma_max", "raw_false"}
    assert series_by_id["sigma_max"]["direction"] == "minimize"
    assert series_by_id["raw_false"]["direction"] == "minimize"
    assert series_by_id["sigma_max"]["points"][0]["artifact_id"] == "artifact-new"
    assert series_by_id["raw_false"]["points"][0]["value"] == pytest.approx(0.2063)


def test_git_branch_canvas_analysis_slice_exposes_metrics_from_metric_id_rows(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("analysis slice metric rows quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-analysis-metrics"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-analysis-metrics",
        summary="Baseline for analysis metric rows.",
        metrics_summary={"sigma_max": 0.6921, "acc": 0.8812, "raw_false": 0.2149},
        primary_metric={"metric_id": "sigma_max", "value": 0.6921},
        metric_contract={
            "primary_metric_id": "sigma_max",
            "metrics": [
                {"metric_id": "sigma_max", "direction": "lower_better"},
                {"metric_id": "acc", "direction": "higher_better"},
                {"metric_id": "raw_false", "direction": "lower_better"},
            ],
        },
    )

    artifact.submit_idea(
        quest_root,
        title="Metric row route",
        problem="Analysis nodes need their own durable metrics.",
        hypothesis="Normalized metric rows should survive into the branch canvas payload.",
        mechanism="Launch one main run and one follow-up slice.",
        expected_gain="Canvas can render every analysis metric selector option.",
        decision_reason="Prepare a durable parent run for analysis.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-analysis-metrics-001",
        title="Main analysis metric run",
        hypothesis="The main run establishes the analysis parent branch.",
        setup="Standard setup.",
        execution="Ran the main evaluation once.",
        results="Enough evidence exists for one follow-up slice.",
        conclusion="Launch one analysis slice.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2477, "direction": "lower_better"},
            {"metric_id": "acc", "value": 0.9103, "direction": "higher_better"},
            {"metric_id": "raw_false", "value": 0.2063, "direction": "lower_better"},
        ],
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Metric row analysis",
        campaign_goal="Verify analysis slice metrics appear in the branch payload.",
        slices=[
            {
                "slice_id": "ablation",
                "title": "Metric row ablation",
                "goal": "Record one completed analysis slice.",
                "required_changes": "Apply one isolated ablation only.",
                "metric_contract": "Keep the same evaluation protocol.",
            }
        ],
    )

    artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the target component only.",
        execution="Ran the ablation once.",
        results="The analysis slice produced comparable metrics.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2511, "direction": "lower_better"},
            {"metric_id": "acc", "value": 0.9051, "direction": "higher_better"},
            {"metric_id": "raw_false", "value": 0.2098, "direction": "lower_better"},
        ],
        evaluation_summary={
            "takeaway": "The ablation preserves most of the gain.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    analysis_branch = campaign["slices"][0]["branch"]
    nodes = {item["ref"]: item for item in branches["nodes"]}
    latest_result = nodes[analysis_branch]["latest_result"]

    assert latest_result["metrics_summary"] == {
        "sigma_max": 0.2511,
        "acc": 0.9051,
        "raw_false": 0.2098,
    }
    assert [item["metric_id"] for item in latest_result["metric_rows"]] == ["sigma_max", "acc", "raw_false"]
    assert latest_result["metric_rows"][0]["numeric_value"] == pytest.approx(0.2511)
    assert nodes[analysis_branch]["latest_metric"]["key"] == "sigma_max"
    assert nodes[analysis_branch]["latest_metric"]["value"] == pytest.approx(0.2511)
    assert nodes[analysis_branch]["latest_metric"]["direction"] == "minimize"


def test_git_branch_canvas_parents_follow_up_analysis_to_current_workspace_node(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("canvas current workspace parent quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root)

    parent = artifact.submit_idea(
        quest_root,
        title="Parent route",
        problem="Need a stable node for analysis.",
        hypothesis="This route will own the follow-up analysis branch.",
        mechanism="Create the first durable route.",
        expected_gain="A parent node for the canvas test.",
        decision_reason="Use this route first.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="run-parent",
        title="Parent run",
        hypothesis="The parent route is good enough.",
        setup="Standard setup.",
        execution="Executed the main run.",
        results="Needs one more follow-up experiment.",
        conclusion="Launch a child analysis branch from this node.",
        metrics_summary={"acc": 0.84},
        metric_rows=[{"metric_id": "acc", "value": 0.84}],
    )
    head = artifact.submit_idea(
        quest_root,
        title="Latest head route",
        problem="Create a newer head branch.",
        hypothesis="This becomes the head, but not the active canvas parent.",
        mechanism="Branch a newer route.",
        expected_gain="Separate current head from current workspace.",
        decision_reason="Advance the head branch.",
    )
    activated = artifact.activate_branch(quest_root, branch=parent["branch"])
    assert activated["branch"] == parent["branch"]

    app = DaemonApp(temp_home)
    before_campaign = app.handlers.git_branches(quest_id)
    before_nodes = {item["ref"]: item for item in before_campaign["nodes"]}
    assert before_campaign["active_workspace_ref"] == parent["branch"]
    assert before_campaign["research_head_ref"] == head["branch"]
    assert before_nodes[parent["branch"]]["active_workspace"] is True
    assert before_nodes[head["branch"]]["research_head"] is True

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Follow-up child branch",
        campaign_goal="Ensure the canvas edge comes from the current workspace node.",
        slices=[
            {
                "slice_id": "follow-up",
                "title": "Follow-up",
                "goal": "Create exactly one child analysis branch.",
                "required_changes": "One isolated follow-up change.",
                "metric_contract": "Keep the same evaluation contract.",
            }
        ],
    )
    analysis_branch = campaign["slices"][0]["branch"]

    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}

    assert head["branch"] != parent["branch"]
    assert branches["active_workspace_ref"] == analysis_branch
    assert branches["research_head_ref"] == head["branch"]
    assert nodes[analysis_branch]["active_workspace"] is True
    assert nodes[head["branch"]]["research_head"] is True
    assert nodes[analysis_branch]["parent_ref"] == "run/run-parent"
    assert nodes[analysis_branch]["parent_branch_recorded"] == "run/run-parent"
    assert nodes["run/run-parent"]["workflow_state"]["analysis_state"] == "active"
    assert nodes["run/run-parent"]["workflow_state"]["writing_state"] == "blocked_by_analysis"
    assert nodes["run/run-parent"]["workflow_state"]["next_pending_slice_id"] == "follow-up"
    assert nodes[analysis_branch]["workflow_state"]["analysis_state"] == "active"
    assert nodes[analysis_branch]["workflow_state"]["status_reason"] == "Analysis 0/1 done"
    assert nodes[head["branch"]]["workflow_state"]["writing_state"] == "not_ready"


def test_git_branch_canvas_marks_active_paper_branch_after_analysis_completion(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("canvas writing state quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-writing")
    artifact.submit_idea(
        quest_root,
        title="Writing route",
        problem="Need a truthful paper transition on the canvas.",
        hypothesis="A completed supplementary run should activate the paper branch only.",
        mechanism="Run one writing-facing supplementary slice.",
        decision_reason="Prepare the writing handoff.",
        next_target="experiment",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-writing-001",
        title="Writing main run",
        hypothesis="This route is strong enough for paper drafting.",
        setup="Use the confirmed baseline.",
        execution="Completed the main run.",
        results="The main run is ready for one last reviewer-style check.",
        conclusion="Run one analysis slice before writing.",
        metric_rows=[{"metric_id": "acc", "value": 0.92}],
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Writing Outline",
        detailed_outline={
            "title": "Writing Outline",
            "research_questions": ["RQ-writing"],
            "experimental_designs": ["Exp-writing"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use the first outline for the writing-state canvas test.",
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Writing-state campaign",
        campaign_goal="Complete the last supplementary slice before opening the paper branch.",
        selected_outline_ref="outline-001",
        research_questions=["RQ-writing"],
        experimental_designs=["Exp-writing"],
        todo_items=[
            {
                "exp_id": "EXP-WRITE-001",
                "todo_id": "todo-writing",
                "slice_id": "slice-writing",
                "title": "Writing slice",
                "research_question": "RQ-writing",
                "experimental_design": "Exp-writing",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "section_id": "writing-check",
                "item_id": "AN-WRITE-001",
                "claim_links": ["C-writing"],
                "completion_condition": "Finish the required supplementary experiment.",
            }
        ],
        slices=[
            {
                "slice_id": "slice-writing",
                "title": "Writing slice",
                "goal": "Complete the final writing-facing check.",
                "required_changes": "Keep the main claim comparable.",
                "metric_contract": "Use the same accuracy contract.",
                "section_id": "writing-check",
                "item_id": "AN-WRITE-001",
                "paper_role": "main_text",
                "claim_links": ["C-writing"],
            }
        ],
    )
    completed = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="slice-writing",
        setup="Lock the baseline and protocol.",
        execution="Ran the final writing-facing check.",
        results="The last check supports opening the paper branch.",
        metric_rows=[{"metric_id": "acc", "value": 0.925}],
        evaluation_summary={
            "takeaway": "The final supplementary check supports the main claim.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    paper_branch = str(completed["research_state"]["current_workspace_branch"] or "").strip()
    parent_branch = str(completed["research_state"]["paper_parent_branch"] or "").strip()

    assert completed["research_state"]["workspace_mode"] == "paper"
    assert branches["active_workspace_ref"] == paper_branch
    assert nodes[paper_branch]["workflow_state"]["writing_state"] == "active"
    assert nodes[paper_branch]["workflow_state"]["status_reason"] == "Writing workspace active."
    assert nodes[parent_branch]["workflow_state"]["writing_state"] == "ready"


def test_git_branch_canvas_parents_writing_facing_analysis_to_paper_line(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("canvas paper-line parent quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-paper-line")
    artifact.submit_idea(
        quest_root,
        title="Paper-line route",
        problem="Need supplementary slices to orbit an explicit paper line.",
        hypothesis="A writing-facing campaign should parent analysis to the paper branch.",
        mechanism="Open the paper line before launching the slice.",
        decision_reason="Exercise the paper-line-first canvas path.",
        next_target="experiment",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-paper-line-001",
        title="Paper-line main run",
        hypothesis="This route is strong enough to justify a paper line.",
        setup="Use the confirmed baseline.",
        execution="Completed the main run.",
        results="One supplementary check remains.",
        conclusion="Open a writing-facing campaign bound to the paper line.",
        metric_rows=[{"metric_id": "acc", "value": 0.93}],
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Paper Line Outline",
        detailed_outline={
            "title": "Paper Line Outline",
            "research_questions": ["RQ-paper-line"],
            "experimental_designs": ["Exp-paper-line"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use the first outline for the paper-line parent test.",
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Paper-line campaign",
        campaign_goal="Verify that the active slice hangs off the paper line.",
        selected_outline_ref="outline-001",
        research_questions=["RQ-paper-line"],
        experimental_designs=["Exp-paper-line"],
        todo_items=[
            {
                "exp_id": "EXP-PAPER-LINE-001",
                "todo_id": "todo-paper-line",
                "slice_id": "slice-paper-line",
                "title": "Paper-line slice",
                "research_question": "RQ-paper-line",
                "experimental_design": "Exp-paper-line",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "section_id": "paper-line-check",
                "item_id": "AN-PAPER-LINE-001",
                "claim_links": ["C-paper-line"],
                "completion_condition": "Finish the required paper-line slice.",
            }
        ],
        slices=[
            {
                "slice_id": "slice-paper-line",
                "title": "Paper-line slice",
                "goal": "Keep one paper-facing slice pending.",
                "required_changes": "Preserve the main comparison surface.",
                "metric_contract": "Use the same accuracy contract.",
                "section_id": "paper-line-check",
                "item_id": "AN-PAPER-LINE-001",
                "paper_role": "main_text",
                "claim_links": ["C-paper-line"],
            }
        ],
    )

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    nodes = {item["ref"]: item for item in branches["nodes"]}
    analysis_branch = campaign["slices"][0]["branch"]
    paper_branch = str(campaign["manifest"]["paper_line_branch"] or "").strip()

    assert paper_branch.startswith("paper/")
    assert branches["active_workspace_ref"] == analysis_branch
    assert nodes[analysis_branch]["parent_ref"] == paper_branch
    assert nodes[analysis_branch]["paper_line_branch"] == paper_branch
    assert nodes[paper_branch]["workflow_state"]["analysis_state"] == "active"
    assert nodes[paper_branch]["workflow_state"]["writing_state"] == "blocked_by_analysis"


def test_git_actions_keep_canvas_as_branch_graph_for_copilot(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("copilot git graph quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    quest_service.update_research_state(quest_root, workspace_mode="copilot")
    artifact = ArtifactService(temp_home)

    artifact.git_action(quest_root, action="branch", branch="feature/git-graph")
    artifact.git_action(quest_root, action="checkout", branch="feature/git-graph")
    write_text(quest_root / "git-graph.txt", "git graph\n")
    artifact.git_action(quest_root, action="commit", message="git graph commit", allow_empty=False)

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    refs = {item["ref"]: item for item in branches["nodes"]}

    assert set(refs) == {"main", "feature/git-graph"}
    assert refs["feature/git-graph"]["parent_ref"] == "main"
    assert refs["feature/git-graph"]["latest_summary"]
    assert "Committed" in str(refs["feature/git-graph"]["latest_summary"])


def test_git_branch_created_from_idea_branch_stays_connected_in_canvas(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("copilot git branch from idea quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])
    quest_service.update_research_state(quest_root, workspace_mode="copilot")
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root)

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Connected git branch idea",
        problem="Verify git branch lineage under an idea branch.",
        hypothesis="A git-created branch should remain attached to the active idea branch.",
        mechanism="Use artifact.git(branch=...) from the active idea workspace.",
        expected_gain="Canvas remains a graph rather than a detached chain.",
        next_target="experiment",
    )
    idea_branch = idea["branch"]

    artifact.git_action(quest_root, action="branch", branch="feature/from-idea")

    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest_id)
    refs = {item["ref"]: item for item in branches["nodes"]}

    assert idea_branch in refs
    assert "feature/from-idea" in refs
    assert refs["feature/from-idea"]["parent_ref"] == idea_branch
    assert refs["feature/from-idea"]["parent_branch_recorded"] == idea_branch
    assert refs["feature/from-idea"]["latest_summary"]
    assert "Created branch" in str(refs["feature/from-idea"]["latest_summary"])

    stage_view = app.handlers.stage_view(
        quest_id,
        body={
            "selection_type": "branch_node",
            "selection_ref": "feature/from-idea",
            "branch_name": "feature/from-idea",
            "compare_base": idea_branch,
            "compare_head": "feature/from-idea",
        },
    )
    history_titles = [str(item.get("title") or "") for item in stage_view["sections"]["history"]]
    assert any("Created branch" in title for title in history_titles)
