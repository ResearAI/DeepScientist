from __future__ import annotations

import argparse
import json
from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller


FIXTURE_QUEST_ID = "e2e-lab-canvas"
FIXTURE_METRICS = ["sigma_max", "acc", "raw_false"]


def confirm_local_baseline(artifact: ArtifactService, quest_root: Path, baseline_id: str = "baseline-lab-e2e") -> None:
    baseline_root = quest_root / "baselines" / "local" / baseline_id
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id=baseline_id,
        summary="Baseline for lab canvas E2E coverage.",
        metrics_summary={"sigma_max": 0.6921, "acc": 0.8812, "raw_false": 0.2149},
        primary_metric={"metric_id": "sigma_max", "value": 0.6921},
        metric_contract={
            "primary_metric_id": "sigma_max",
            "metrics": [
                {"metric_id": "sigma_max", "label": "sigma_max", "direction": "lower_better"},
                {"metric_id": "acc", "label": "acc", "direction": "higher_better"},
                {"metric_id": "raw_false", "label": "raw_false", "direction": "lower_better"},
            ],
        },
    )


def build_fixture(home: Path) -> dict[str, object]:
    ensure_home_layout(home)
    config_manager = ConfigManager(home)
    config_manager.ensure_files()

    installer = SkillInstaller(repo_root(), home)
    quest_service = QuestService(home, skill_installer=installer)
    quest = quest_service.create("Lab canvas E2E fixture", quest_id=FIXTURE_QUEST_ID)
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(home)

    confirm_local_baseline(artifact, quest_root)

    stem_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Stem Route",
        problem="Need a stable parent route before branching.",
        hypothesis="One measured parent route can anchor both sibling and current paths.",
        mechanism="Establish a shared parent run, then branch intentionally.",
        decision_reason="Create a durable parent route for Canvas lineage filtering.",
        next_target="experiment",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-stem-001",
        title="Stem Route main run",
        hypothesis="The stem route establishes a meaningful parent run.",
        setup="Use the confirmed baseline protocol.",
        execution="Ran the shared parent experiment once.",
        results="The parent run is good enough to branch.",
        conclusion="Use this run as the parent foundation for both child routes.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2477, "direction": "lower_better"},
            {"metric_id": "acc", "value": 0.9103, "direction": "higher_better"},
            {"metric_id": "raw_false", "value": 0.2063, "direction": "lower_better"},
        ],
        evaluation_summary={
            "takeaway": "The stem route is strong enough to support follow-up branching.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "idea",
        },
    )

    artifact.activate_branch(quest_root, branch=stem_idea["branch"])
    sibling_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        lineage_intent="branch_alternative",
        title="Sibling Route",
        problem="Need a non-current sibling route to test path filtering.",
        hypothesis="An alternative sibling route should stay visible only in all-path mode.",
        mechanism="Branch an alternative child idea from the same parent foundation.",
        decision_reason="Create a sibling branch outside the active paper lineage.",
        draft_markdown="# Sibling Route\n\nThis path should be hidden in current-path mode.\n",
    )

    artifact.activate_branch(quest_root, branch=stem_idea["branch"])
    current_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        lineage_intent="continue_line",
        title="Current Route",
        problem="Need the active route to stay visible through analysis and writing.",
        hypothesis="The current route should become the active paper path.",
        mechanism="Continue the winning line and finish one writing-facing analysis slice.",
        decision_reason="Use this branch as the active Canvas route.",
        draft_markdown="# Current Route\n\nThis is the route the paper branch should follow.\n",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-current-001",
        title="Current Route main run",
        hypothesis="This route improves all tracked metrics enough for paper drafting.",
        setup="Use the confirmed baseline protocol.",
        execution="Ran the active route experiment once.",
        results="All tracked metrics improved enough to justify analysis and writing.",
        conclusion="Launch one writing-facing analysis slice, then open the paper branch.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2331, "direction": "lower_better"},
            {"metric_id": "acc", "value": 0.9194, "direction": "higher_better"},
            {"metric_id": "raw_false", "value": 0.1982, "direction": "lower_better"},
        ],
        evaluation_summary={
            "takeaway": "The current route wins on every tracked metric and is ready for one final analysis slice.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    candidate = artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Current Route Outline",
        detailed_outline={
            "title": "Current Route Outline",
            "research_questions": ["RQ-current"],
            "experimental_designs": ["Exp-current"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id=candidate["outline_id"],
        selected_reason="Bind the active route to a writing-facing outline before analysis.",
    )

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Current route analysis",
        campaign_goal="Complete one writing-facing check before drafting.",
        selected_outline_ref=candidate["outline_id"],
        research_questions=["RQ-current"],
        experimental_designs=["Exp-current"],
        todo_items=[
            {
                "exp_id": "EXP-CURRENT-001",
                "todo_id": "todo-current-001",
                "slice_id": "slice-current-001",
                "title": "Current route slice",
                "research_question": "RQ-current",
                "experimental_design": "Exp-current",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "section_id": "results-current",
                "item_id": "AN-CURRENT-001",
                "claim_links": ["C-current"],
                "completion_condition": "Finish the final writing-facing supplementary experiment.",
            }
        ],
        slices=[
            {
                "slice_id": "slice-current-001",
                "title": "Current route slice",
                "goal": "Verify the active route with one final writing-facing check.",
                "required_changes": "Keep the protocol comparable.",
                "metric_contract": "Use the same three tracked metrics.",
                "section_id": "results-current",
                "item_id": "AN-CURRENT-001",
                "paper_role": "main_text",
                "claim_links": ["C-current"],
            }
        ],
    )
    completed = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="slice-current-001",
        setup="Freeze the baseline and evaluation protocol.",
        execution="Ran the final writing-facing supplementary experiment once.",
        results="The active route remains strong and the paper branch should open.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2298, "direction": "lower_better"},
            {"metric_id": "acc", "value": 0.9215, "direction": "higher_better"},
            {"metric_id": "raw_false", "value": 0.1944, "direction": "lower_better"},
        ],
        claim_impact="The final writing-facing slice strengthens the active route.",
        evaluation_summary={
            "takeaway": "The final slice keeps all tracked metrics on the winning side.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )

    (quest_root / "validation" / "environment").mkdir(parents=True, exist_ok=True)
    (quest_root / "simulations" / "inputs").mkdir(parents=True, exist_ok=True)
    (quest_root / "simulations" / "logs").mkdir(parents=True, exist_ok=True)
    (quest_root / "simulations" / "outputs" / "water").mkdir(parents=True, exist_ok=True)
    (quest_root / "validation" / "runs").mkdir(parents=True, exist_ok=True)
    (quest_root / "validation" / "environment" / "pyscf_doctor.json").write_text(
        json.dumps({"import": "passed", "version": "2.x", "smoke_test": "passed"}, indent=2),
        encoding="utf-8",
    )
    (quest_root / "simulations" / "inputs" / "water.py").write_text(
        "print('water hf sto-3g fixture')\n",
        encoding="utf-8",
    )
    (quest_root / "simulations" / "logs" / "water.out").write_text(
        "SCF converged\nE = -74.96 Hartree\n",
        encoding="utf-8",
    )
    (quest_root / "simulations" / "outputs" / "water" / "energy.json").write_text(
        json.dumps({"total_energy": -74.96, "unit": "Hartree"}, indent=2),
        encoding="utf-8",
    )
    (quest_root / "validation" / "runs" / "water.json").write_text(
        json.dumps({"scf_converged": True, "charge": 0, "spin": 0, "unit": "Hartree"}, indent=2),
        encoding="utf-8",
    )

    artifact.science(
        quest_root,
        action="record_node",
        node_type="science.package_check",
        node_id="pkg_pyscf_check",
        title="PySCF environment check",
        status="passed",
        domain="quantum_chemistry",
        package_id="pyscf",
        key_results=[{"label": "import", "value": "passed"}, {"label": "version", "value": "2.x"}],
        evidence_paths=["validation/environment/pyscf_doctor.json"],
    )
    artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_water_hf_sto3g",
        title="Water HF/STO-3G energy",
        summary="Computed water molecule total energy using a fixture PySCF-style smoke run.",
        status="success",
        domain="quantum_chemistry",
        package_id="pyscf",
        task_type="scf_energy",
        key_results=[{"label": "Total energy", "value": -74.96, "unit": "Hartree"}],
        input_paths=["simulations/inputs/water.py"],
        log_paths=["simulations/logs/water.out"],
        output_paths=["simulations/outputs/water/energy.json"],
        evidence_paths=[
            "simulations/inputs/water.py",
            "simulations/logs/water.out",
            "simulations/outputs/water/energy.json",
        ],
        parent_node_ids=["pkg_pyscf_check"],
    )
    artifact.science(
        quest_root,
        action="record_node",
        node_type="science.validation_result",
        node_id="val_water_hf_sto3g",
        title="SCF validation",
        status="passed",
        domain="quantum_chemistry",
        package_id="pyscf",
        related_node_ids=["run_water_hf_sto3g"],
        validation_paths=["validation/runs/water.json"],
        key_results=[
            {"label": "SCF converged", "value": True},
            {"label": "charge", "value": 0},
            {"label": "spin", "value": 0},
        ],
    )
    artifact.science(
        quest_root,
        action="record_node",
        node_type="science.claim",
        node_id="claim_water_energy_computed",
        title="Water energy was computed",
        status="active",
        domain="quantum_chemistry",
        claim_type="computed",
        trust="medium",
        summary="The fixture run records a computed water HF/STO-3G total energy with linked validation evidence.",
        related_node_ids=["run_water_hf_sto3g", "val_water_hf_sto3g"],
        evidence_paths=[
            "simulations/outputs/water/energy.json",
            "validation/runs/water.json",
        ],
    )

    quest_service.update_lab_canvas_state(
        quest_root,
        layout_json={
            "branch": {},
            "event": {},
            "stage": {},
            "preferences": {
                "pathFilterMode": "current",
                "showAnalysis": True,
            },
        },
    )

    return {
        "quest_id": quest["quest_id"],
        "quest_root": str(quest_root),
        "current_title": "Current Route",
        "sibling_title": "Sibling Route",
        "paper_branch": str(completed["research_state"]["current_workspace_branch"] or ""),
        "metric_keys": FIXTURE_METRICS,
        "science_run_title": "Water HF/STO-3G energy",
        "science_claim_title": "Water energy was computed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated lab canvas E2E fixture quest.")
    parser.add_argument("--home", required=True, help="DeepScientist home for the temporary fixture runtime.")
    parser.add_argument("--output", required=True, help="Path to write the fixture JSON.")
    args = parser.parse_args()

    home = Path(args.home).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture(home)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixture, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
