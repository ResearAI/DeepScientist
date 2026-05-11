from __future__ import annotations

from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.shared import read_json
from deepscientist.skills import SkillInstaller


def _quest(temp_home: Path) -> tuple[QuestService, dict, Path]:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("science artifact quest")
    return quest_service, quest, Path(quest["quest_root"])


def test_science_records_package_run_validation_and_claim(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    package_check = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.package_check",
        node_id="pkg_pyscf_check",
        title="PySCF environment check",
        status="passed",
        domain="quantum_chemistry",
        package_id="pyscf",
        key_results=[{"label": "import", "value": "passed"}],
        evidence_paths=["validation/environment/pyscf_doctor.json"],
    )

    assert package_check["ok"] is True
    assert package_check["recorded"] == "science.package_check"
    assert package_check["science"]["node_id"] == "pkg_pyscf_check"
    package_path = quest_root / "artifacts" / "science" / "pkg-pyscf-check.json"
    assert package_path.exists()
    assert read_json(package_path, {})["paths"]["evidence_1"] == "validation/environment/pyscf_doctor.json"

    run = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_water_hf_sto3g",
        title="Water HF/STO-3G energy",
        status="success",
        domain="quantum_chemistry",
        package_id="pyscf",
        task_type="scf_energy",
        key_results=[{"label": "Total energy", "value": -74.96, "unit": "Hartree"}],
        input_paths=["simulations/inputs/water.py"],
        log_paths=["simulations/logs/water.out"],
        output_paths=["simulations/outputs/water/energy.json"],
        parent_node_ids=["pkg_pyscf_check"],
        canvas={"focus": True, "open_detail": True},
    )

    assert run["ok"] is True
    assert run["science"]["node_type"] == "science.computational_run"
    assert run["ui_effects"][0]["name"] == "science:focus"
    run_record = read_json(Path(run["artifact_path"]), {})
    assert run_record["changed_files"] == [
        "simulations/inputs/water.py",
        "simulations/outputs/water/energy.json",
        "simulations/logs/water.out",
    ]

    validation = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.validation_result",
        node_id="val_water",
        title="SCF validation",
        status="passed",
        related_node_ids=["run_water_hf_sto3g"],
        validation_paths=["validation/runs/water.json"],
    )
    assert validation["ok"] is True

    claim = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.claim",
        node_id="claim_water_energy",
        title="Water energy was computed",
        status="active",
        claim_type="computed",
        trust="medium",
        related_node_ids=["run_water_hf_sto3g", "val_water"],
        evidence_paths=["simulations/outputs/water/energy.json", "validation/runs/water.json"],
        notify=True,
    )
    assert claim["ok"] is True
    assert claim["record"]["claim_type"] == "computed"

    status = artifact.science(quest_root, action="status")
    assert status["ok"] is True
    assert status["count"] == 4
    assert status["by_type"]["science.package_check"] == 1
    assert status["by_status"]["passed"] == 2


def test_science_rejects_claims_and_runs_without_required_evidence(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    claim = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.claim",
        node_id="claim_without_evidence",
        title="Unsupported computed claim",
        claim_type="computed",
    )

    assert claim["ok"] is False
    assert any("Computed science claim requires" in error for error in claim["errors"])

    run = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_without_paths",
        status="success",
    )
    assert run["ok"] is False
    assert any("Successful computational_run requires" in error for error in run["errors"])

    validation = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.validation_result",
        node_id="validation_without_related_node",
    )
    assert validation["ok"] is False
    assert any("validation_result must reference" in error for error in validation["errors"])


def test_science_update_and_link_are_append_only(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    base = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.dataset_analysis",
        node_id="analysis_cells",
        status="running",
        output_paths=["analyses/outputs/cells.partial.json"],
    )
    assert base["ok"] is True

    update = artifact.science(
        quest_root,
        action="update_node",
        node_type="science.dataset_analysis",
        node_id="analysis_cells",
        status="success",
        output_paths=["analyses/outputs/cells.final.json"],
    )
    assert update["ok"] is True
    assert update["artifact_id"] != base["artifact_id"]
    assert Path(base["artifact_path"]).exists()
    assert Path(update["artifact_path"]).exists()

    link = artifact.science(
        quest_root,
        action="link_nodes",
        node_id="analysis_cells_link",
        related_node_ids=["analysis_cells", "claim_cells"],
        relation_type="supports",
        relation_summary="Analysis supports the claim.",
    )
    assert link["ok"] is True
    assert link["record"]["action"] == "link_nodes"
    assert link["record"]["related_node_ids"] == ["analysis_cells", "claim_cells"]


def test_science_record_node_rejects_duplicate_node_id_without_overwriting_original(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    original = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_duplicate_guard",
        title="Original run evidence",
        status="success",
        input_paths=["simulations/inputs/original.py"],
        output_paths=["simulations/outputs/original.json"],
    )
    assert original["ok"] is True
    original_path = Path(original["artifact_path"])

    duplicate = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_duplicate_guard",
        title="Replacement run evidence",
        status="success",
        input_paths=["simulations/inputs/replacement.py"],
        output_paths=["simulations/outputs/replacement.json"],
    )

    assert duplicate["ok"] is False
    assert any("already exists" in error and "update_node" in error for error in duplicate["errors"])
    assert duplicate["science"]["existing_artifact_id"] == original["artifact_id"]
    preserved = read_json(original_path, {})
    assert preserved["title"] == "Original run evidence"
    assert preserved["input_paths"] == ["simulations/inputs/original.py"]
    assert preserved["output_paths"] == ["simulations/outputs/original.json"]


def test_science_record_node_rejects_slug_collision_without_overwriting_original(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    original = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run x",
        title="Original slug evidence",
        status="success",
        input_paths=["simulations/inputs/original_slug.py"],
        output_paths=["simulations/outputs/original_slug.json"],
    )
    assert original["ok"] is True
    original_path = Path(original["artifact_path"])
    assert original["artifact_id"] == "run-x"

    collision = artifact.science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run-x",
        title="Colliding slug evidence",
        status="success",
        input_paths=["simulations/inputs/collision.py"],
        output_paths=["simulations/outputs/collision.json"],
    )

    assert collision["ok"] is False
    assert any("artifact_id `run-x` already exists" in error for error in collision["errors"])
    assert collision["science"]["existing_node_id"] == "run x"
    preserved = read_json(original_path, {})
    assert preserved["title"] == "Original slug evidence"
    assert preserved["node_id"] == "run x"
    assert preserved["output_paths"] == ["simulations/outputs/original_slug.json"]


def test_science_status_and_focus_do_not_execute_or_create_artifacts(temp_home: Path) -> None:
    _, _, quest_root = _quest(temp_home)
    artifact = ArtifactService(temp_home)

    focus = artifact.science(
        quest_root,
        action="focus",
        node_id="run_water_hf_sto3g",
        canvas={"focus": True, "open_detail": True},
        notify=True,
    )
    assert focus["ok"] is True
    assert focus["action"] == "focus"
    assert focus["ui_effects"][0]["name"] == "science:focus"
    assert not (quest_root / "artifacts" / "science").exists()

    status = artifact.science(quest_root, action="status")
    assert status["ok"] is True
    assert status["count"] == 0
    assert not (quest_root / "artifacts" / "science").exists()
