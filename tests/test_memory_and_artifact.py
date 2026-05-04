from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.metrics import MetricContractValidationError
from deepscientist.connector.weixin_support import remember_weixin_context_token
from deepscientist.config import ConfigManager
from deepscientist.daemon.app import DaemonApp
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.memory import MemoryService
from deepscientist.memory.frontmatter import dump_markdown_document, load_markdown_document
from deepscientist.quest import QuestService
from deepscientist.registries import BaselineRegistry
from deepscientist.shared import ensure_dir, read_json, read_jsonl, read_yaml, write_json, write_yaml
from deepscientist.skills import SkillInstaller


def _assert_artifact_delta(
    delta: dict[str, Any],
    *,
    delta_kind: str,
    expected_labels: set[str],
) -> dict[str, Any]:
    assert delta["schema_version"] == 1
    assert delta["delta_kind"] == delta_kind
    assert delta["path_count"] >= len(expected_labels)
    assert delta["sidecar_rel_path"].startswith("paper/artifact_deltas/")
    sidecar = read_json(Path(delta["sidecar_path"]), {})
    assert sidecar["schema_version"] == 1
    assert sidecar["delta_id"] == delta["delta_id"]
    assert sidecar["delta_kind"] == delta_kind
    by_label = {item["label"]: item for item in sidecar["paths"]}
    assert expected_labels.issubset(by_label)
    assert all(by_label[label]["exists"] is True for label in expected_labels)
    return sidecar


def _detailed_metric_contract(
    metric_ids: list[str],
    *,
    primary_metric_id: str | None = None,
    directions: dict[str, str] | None = None,
    evaluation_protocol: dict[str, object] | None = None,
) -> dict:
    resolved_directions = directions or {}
    payload = {
        "primary_metric_id": primary_metric_id or (metric_ids[0] if metric_ids else None),
        "metrics": [
            {
                "metric_id": metric_id,
                "label": metric_id,
                "direction": resolved_directions.get(metric_id, "maximize"),
                "description": f"Canonical metric `{metric_id}`.",
                "derivation": f"Read `{metric_id}` from the canonical evaluation output.",
                "source_ref": "paper table + eval.py",
                "required": True,
            }
            for metric_id in metric_ids
        ],
    }
    if evaluation_protocol:
        payload["evaluation_protocol"] = evaluation_protocol
    return payload


def _confirm_local_baseline(artifact: ArtifactService, quest_root: Path, baseline_id: str = "baseline-local") -> dict:
    baseline_root = quest_root / "baselines" / "local" / baseline_id
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    return artifact.confirm_baseline(
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


def test_confirm_baseline_writes_metric_contract_json_and_exposes_path(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("baseline metric contract json quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-metric-contract")

    assert result["ok"] is True
    confirmed_ref = result["confirmed_baseline_ref"]
    assert confirmed_ref["metric_contract_json_rel_path"] == "baselines/local/baseline-metric-contract/json/metric_contract.json"
    metric_contract_json = quest_root / confirmed_ref["metric_contract_json_rel_path"]
    assert metric_contract_json.exists()
    payload = read_json(metric_contract_json, {})
    assert payload["kind"] == "baseline_metric_contract"
    assert payload["baseline_id"] == "baseline-metric-contract"
    assert payload["metric_contract"]["primary_metric_id"] == "acc"
    attachment = read_yaml(quest_root / "baselines" / "imported" / "baseline-metric-contract" / "attachment.yaml", {})
    assert attachment["confirmation"]["metric_contract_json_rel_path"] == confirmed_ref["metric_contract_json_rel_path"]


def test_confirm_baseline_strict_rejects_missing_metric_explanations(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("strict baseline validation quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-strict"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Strict baseline\n", encoding="utf-8")

    with pytest.raises(MetricContractValidationError) as exc_info:
        artifact.confirm_baseline(
            quest_root,
            baseline_path=str(baseline_root),
            baseline_id="baseline-strict",
            summary="Strict baseline should fail without explanations",
            metrics_summary={"acc": 0.91},
            primary_metric={"name": "acc", "value": 0.91},
            metric_contract={
                "primary_metric_id": "acc",
                "metrics": [{"metric_id": "acc", "direction": "higher"}],
            },
            strict_metric_contract=True,
        )

    exc = exc_info.value
    assert exc.error_code == "baseline_metric_explanations_missing"
    assert exc.details["validation_stage"] == "baseline"
    assert exc.details["baseline_metric_ids"] == ["acc"]
    assert exc.details["baseline_metric_details"][0]["metric_id"] == "acc"


def test_confirm_baseline_metric_directions_override_and_main_run_prefers_confirmed_contract_json(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("metric direction truth quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-direction"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Direction baseline\n", encoding="utf-8")

    confirmed = artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-direction",
        summary="Direction-sensitive baseline",
        metrics_summary={"sigma_max": 0.6921, "raw_false": 0.2149},
        primary_metric={"metric_id": "sigma_max", "value": 0.6921},
        metric_contract=_detailed_metric_contract(
            ["sigma_max", "raw_false"],
            primary_metric_id="sigma_max",
            directions={
                "sigma_max": "maximize",
                "raw_false": "maximize",
            },
            evaluation_protocol={
                "scope_id": "full",
                "code_paths": ["eval.py"],
            },
        ),
        metric_directions={
            "sigma_max": "lower_better",
            "raw_false": "lower_better",
        },
        strict_metric_contract=True,
    )

    metric_contract_json = read_json(Path(confirmed["metric_contract_json_path"]), {})
    directions_by_id = {
        item["metric_id"]: item["direction"]
        for item in metric_contract_json["metric_contract"]["metrics"]
    }
    assert directions_by_id["sigma_max"] == "minimize"
    assert directions_by_id["raw_false"] == "minimize"

    attachment_path = quest_root / "baselines" / "imported" / "baseline-direction" / "attachment.yaml"
    attachment = read_yaml(attachment_path, {})
    for metric in attachment["entry"]["metric_contract"]["metrics"]:
        if metric["metric_id"] in {"sigma_max", "raw_false"}:
            metric["direction"] = "maximize"
    write_yaml(attachment_path, attachment)

    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Direction-aware idea",
        problem="Need lower-is-better comparison to stay correct.",
        hypothesis="The confirmed contract JSON should stay authoritative.",
        mechanism="Recompute using the confirmed baseline metric contract JSON.",
        decision_reason="Launch the direction-sensitive run.",
        next_target="experiment",
    )

    result = artifact.record_main_experiment(
        quest_root,
        run_id="direction-main-001",
        title="Direction-sensitive run",
        hypothesis="Lower sigma_max should count as better.",
        setup="Reuse the confirmed baseline protocol.",
        execution="Ran the full evaluation.",
        results="Sigma max dropped substantially.",
        conclusion="This should beat the baseline under the confirmed metric direction.",
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2477},
            {"metric_id": "raw_false", "value": 0.2063},
        ],
        metric_contract={
            "primary_metric_id": "sigma_max",
            "metrics": [
                {"metric_id": "sigma_max", "direction": "maximize", "label": "Sigma max"},
                {"metric_id": "raw_false", "direction": "maximize", "label": "Raw false"},
            ],
        },
        strict_metric_contract=True,
        evaluation_summary={
            "takeaway": "The run improves the lower-is-better metrics.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    payload = read_json(Path(result["result_json_path"]), {})
    comparisons_by_id = {
        item["metric_id"]: item
        for item in payload["baseline_comparisons"]["items"]
    }
    assert comparisons_by_id["sigma_max"]["direction"] == "minimize"
    assert comparisons_by_id["sigma_max"]["better"] is True
    assert comparisons_by_id["raw_false"]["direction"] == "minimize"
    assert payload["progress_eval"]["direction"] == "minimize"
    assert payload["progress_eval"]["beats_baseline"] is True


def test_overwrite_baseline_refreshes_canonical_surfaces_and_invalidates_caches(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("overwrite baseline quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-overwrite"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Overwrite baseline\n", encoding="utf-8")

    initial = artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-overwrite",
        summary="Initial baseline",
        metrics_summary={"acc": 0.8},
        primary_metric={"metric_id": "acc", "value": 0.8},
        metric_contract=_detailed_metric_contract(
            ["acc"],
            primary_metric_id="acc",
            evaluation_protocol={"scope_id": "full"},
        ),
        strict_metric_contract=True,
    )
    assert initial["ok"] is True

    quest_service.metrics_timeline(quest["quest_id"])
    quest_service.baseline_compare(quest["quest_id"])
    assert (quest_root / ".ds" / "cache" / "metrics_timeline.v1.json").exists()
    assert (quest_root / ".ds" / "cache" / "baseline_compare.v1.json").exists()

    artifact._write_analysis_baseline_inventory(
        quest_root,
        {
            "entries": [
                {
                    "baseline_id": "baseline-overwrite",
                    "variant_id": None,
                    "status": "registered",
                    "baseline_root_rel_path": "baselines/local/baseline-overwrite",
                    "storage_mode": "local",
                    "metrics_summary": {"acc": 0.8},
                }
            ]
        },
    )

    result = artifact.overwrite_baseline(
        quest_root,
        baseline_id="baseline-overwrite",
        baseline_path=str(baseline_root),
        change_summary="Added canonical f1 and refreshed the verified baseline outputs.",
        metrics_summary={"acc": 0.82, "f1": 0.79},
        primary_metric={"metric_id": "acc", "value": 0.82},
        metric_contract=_detailed_metric_contract(
            ["acc", "f1"],
            primary_metric_id="acc",
            evaluation_protocol={"scope_id": "full"},
        ),
        strict_metric_contract=True,
    )

    assert result["ok"] is True
    assert result["overwrite_action"] == "in_place_refresh"
    assert result["compatibility_verdict"] == "metrics_only_safe"
    assert result["risk_level"] == "low"
    confirmed_ref = result["confirmed_baseline_ref"]
    assert confirmed_ref["baseline_id"] == "baseline-overwrite"
    assert confirmed_ref["overwrite"]["change_summary"] == "Added canonical f1 and refreshed the verified baseline outputs."
    assert confirmed_ref["metric_contract_json_rel_path"] == "baselines/local/baseline-overwrite/json/metric_contract.json"

    metric_contract_payload = read_json(Path(result["metric_contract_json_path"]), {})
    assert metric_contract_payload["metrics_summary"] == {"acc": 0.82, "f1": 0.79}
    assert metric_contract_payload["overwrite"]["compatibility_verdict"] == "metrics_only_safe"

    attachment = read_yaml(quest_root / "baselines" / "imported" / "baseline-overwrite" / "attachment.yaml", {})
    assert attachment["overwrite"]["change_summary"] == "Added canonical f1 and refreshed the verified baseline outputs."

    analysis_inventory = read_json(quest_root / "artifacts" / "baselines" / "analysis_inventory.json", {})
    refreshed_entry = next(item for item in analysis_inventory["entries"] if item["baseline_id"] == "baseline-overwrite")
    assert refreshed_entry["metrics_summary"] == {"acc": 0.82, "f1": 0.79}

    paper_inventory = read_json(quest_root / "paper" / "baseline_inventory.json", {})
    assert paper_inventory["canonical_baseline_ref"]["baseline_id"] == "baseline-overwrite"
    assert paper_inventory["canonical_baseline_ref"]["overwrite"]["compatibility_verdict"] == "metrics_only_safe"

    assert str(quest_root / ".ds" / "cache" / "metrics_timeline.v1.json") in result["invalidated_cache_paths"]
    assert str(quest_root / ".ds" / "cache" / "baseline_compare.v1.json") in result["invalidated_cache_paths"]
    assert not (quest_root / ".ds" / "cache" / "metrics_timeline.v1.json").exists()
    assert not (quest_root / ".ds" / "cache" / "baseline_compare.v1.json").exists()

    timeline = quest_service.metrics_timeline(quest["quest_id"])
    compare_payload = quest_service.baseline_compare(quest["quest_id"])
    assert timeline["baseline_ref"]["baseline_id"] == "baseline-overwrite"
    assert {item["metric_id"] for item in timeline["series"]} == {"acc", "f1"}
    acc_series = next(item for item in timeline["series"] if item["metric_id"] == "acc")
    assert acc_series["baselines"][0]["value"] == pytest.approx(0.82)
    assert compare_payload["baseline_ref"]["baseline_id"] == "baseline-overwrite"
    compare_acc_series = next(item for item in compare_payload["series"] if item["metric_id"] == "acc")
    compare_f1_series = next(item for item in compare_payload["series"] if item["metric_id"] == "f1")
    selected_acc = next(item for item in compare_acc_series["values"] if item["selected"] is True)
    selected_f1 = next(item for item in compare_f1_series["values"] if item["selected"] is True)
    assert selected_acc["value"] == pytest.approx(0.82)
    assert selected_f1["value"] == pytest.approx(0.79)
    outbox = read_jsonl(temp_home / "logs" / "connectors" / "local" / "outbox.jsonl")
    assert any("Baseline `baseline-overwrite` has been refreshed." in str(item.get("message") or "") for item in outbox)
    assert result["interaction"]["delivered"] is True
    assert len(list((quest_root / "artifacts" / "baselines").glob("*.json"))) >= 2


def test_overwrite_baseline_rejects_protocol_breaking_change_by_default(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("overwrite baseline reject quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-overwrite-reject"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Reject overwrite baseline\n", encoding="utf-8")

    confirmed = artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-overwrite-reject",
        summary="Initial reject baseline",
        metrics_summary={"acc": 0.8},
        primary_metric={"metric_id": "acc", "value": 0.8},
        metric_contract=_detailed_metric_contract(
            ["acc"],
            primary_metric_id="acc",
            evaluation_protocol={"scope_id": "full"},
        ),
        strict_metric_contract=True,
    )

    with pytest.raises(ValueError, match="protocol-breaking"):
        artifact.overwrite_baseline(
            quest_root,
            baseline_id="baseline-overwrite-reject",
            baseline_path=str(baseline_root),
            change_summary="Switch to a different primary metric and evaluation protocol.",
            metrics_summary={"loss": 0.2},
            primary_metric={"metric_id": "loss", "value": 0.2},
            metric_contract=_detailed_metric_contract(
                ["loss"],
                primary_metric_id="loss",
                directions={"loss": "minimize"},
                evaluation_protocol={"scope_id": "subset"},
            ),
            strict_metric_contract=True,
        )

    snapshot = quest_service.snapshot(quest["quest_id"])
    assert snapshot["confirmed_baseline_ref"]["baseline_id"] == "baseline-overwrite-reject"
    assert "overwrite" not in snapshot["confirmed_baseline_ref"]
    metric_contract_payload = read_json(Path(confirmed["metric_contract_json_path"]), {})
    assert metric_contract_payload["metric_contract"]["primary_metric_id"] == "acc"


def test_apply_start_setup_form_patch_persists_and_merges_suggested_form(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "start setup patch persistence quest",
        startup_contract={
            "workspace_mode": "copilot",
            "launch_mode": "custom",
            "custom_profile": "freeform",
            "start_setup_session": {
                "source": "benchstore",
                "locale": "zh",
                "suggested_form": {
                    "title": "Original setup title",
                    "runtime_constraints": "- Keep local only",
                },
            },
        },
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.apply_start_setup_form_patch(
        quest_root,
        form_patch={
            "goal": "Run the benchmark faithfully.",
            "runtime_constraints": "- Use only GPU 0 after confirmation",
        },
        session_patch={
            "recommended_workspace_mode": "copilot",
            "launch_readiness": "needs_confirmation",
            "missing_confirmations": ["Confirm whether external API keys may be used."],
            "fit_assessment": {
                "verdict": "copilot_recommended",
                "summary": "The task still needs repeated human guidance before autonomous launch is safe.",
            },
            "preview_plan": {
                "summary": "If launched, the system would first normalize the baseline, then evaluate whether a durable optimization loop is actually possible.",
            },
        },
        message="Prepared a merged setup draft.",
    )

    assert result["ok"] is True
    assert result["form_patch"]["goal"] == "Run the benchmark faithfully."
    assert result["suggested_form"]["title"] == "Original setup title"
    assert result["suggested_form"]["goal"] == "Run the benchmark faithfully."
    assert result["suggested_form"]["runtime_constraints"] == "- Use only GPU 0 after confirmation"
    assert result["session_patch"]["recommended_workspace_mode"] == "copilot"

    persisted = quest_service.read_quest_yaml(quest_root)
    startup_contract = persisted.get("startup_contract") if isinstance(persisted.get("startup_contract"), dict) else {}
    start_setup_session = (
        startup_contract.get("start_setup_session")
        if isinstance(startup_contract, dict) and isinstance(startup_contract.get("start_setup_session"), dict)
        else {}
    )
    suggested_form = start_setup_session.get("suggested_form") if isinstance(start_setup_session, dict) else {}
    assert suggested_form["title"] == "Original setup title"
    assert suggested_form["goal"] == "Run the benchmark faithfully."
    assert suggested_form["runtime_constraints"] == "- Use only GPU 0 after confirmation"
    assert start_setup_session["recommended_workspace_mode"] == "copilot"
    assert start_setup_session["launch_readiness"] == "needs_confirmation"
    assert start_setup_session["missing_confirmations"] == ["Confirm whether external API keys may be used."]
    assert start_setup_session["fit_assessment"]["verdict"] == "copilot_recommended"
    assert "normalize the baseline" in str(start_setup_session["preview_plan"]["summary"])


def test_apply_start_setup_form_patch_allows_session_patch_without_form_changes(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "start setup session-only patch quest",
        startup_contract={
            "workspace_mode": "copilot",
            "start_setup_session": {
                "source": "manual",
                "locale": "zh",
                "suggested_form": {
                    "title": "Session-only test",
                },
            },
        },
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.apply_start_setup_form_patch(
        quest_root,
        session_patch={
            "recommended_workspace_mode": "copilot",
            "launch_readiness": "not_ready",
            "missing_confirmations": ["Need a clearer task boundary."],
        },
    )

    assert result["ok"] is True
    assert result["form_patch"] == {}
    assert result["suggested_form"]["title"] == "Session-only test"
    assert result["session_patch"]["launch_readiness"] == "not_ready"


def test_confirm_baseline_strict_flattens_canonical_metric_summary(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("flatten canonical baseline quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-flat"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Flat baseline\n", encoding="utf-8")

    result = artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-flat",
        summary="Canonical baseline should be flat.",
        metrics_summary={
            "global_sigma": {"sigma_max": 0.5751, "sigma_GS": 0.3347},
            "overall_false_ratios": {"raw_false": 0.2348},
        },
        primary_metric={"name": "sigma_max", "value": 0.5751, "direction": "lower_better"},
        metric_contract={
            "primary_metric_id": "sigma_max",
            "metrics": [
                {
                    "metric_id": "sigma_max",
                    "direction": "lower",
                    "description": "Maximum sigma.",
                    "origin_path": "global_sigma.sigma_max",
                    "source_ref": "paper table + eval.py",
                },
                {
                    "metric_id": "sigma_GS",
                    "direction": "lower",
                    "description": "GS sigma.",
                    "origin_path": "global_sigma.sigma_GS",
                    "source_ref": "paper table + eval.py",
                },
                {
                    "metric_id": "raw_false",
                    "direction": "lower",
                    "description": "Raw false ratio.",
                    "origin_path": "overall_false_ratios.raw_false",
                    "source_ref": "paper table + eval.py",
                },
            ],
        },
        strict_metric_contract=True,
    )

    assert result["ok"] is True
    payload = read_json(Path(result["confirmed_baseline_ref"]["metric_contract_json_path"]), {})
    assert payload["metrics_summary"] == {
        "sigma_max": pytest.approx(0.5751),
        "sigma_GS": pytest.approx(0.3347),
        "raw_false": pytest.approx(0.2348),
    }
    assert "metric_note_path" not in result
    assert "metric_note_path" not in result["confirmed_baseline_ref"]
    assert result["metric_details"][0]["metric_id"] == "sigma_max"


def test_record_main_experiment_strict_rejects_missing_required_baseline_metric(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("strict main experiment metric validation quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-main-strict"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Strict main baseline\n", encoding="utf-8")

    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-main-strict",
        summary="Strict baseline for main-experiment validation.",
        metrics_summary={"acc": 0.9, "f1": 0.87},
        primary_metric={"metric_id": "acc", "value": 0.9, "direction": "maximize"},
        metric_contract=_detailed_metric_contract(
            ["acc", "f1"],
            primary_metric_id="acc",
            evaluation_protocol={
                "scope_id": "full",
                "code_paths": ["eval.py"],
            },
        ),
        strict_metric_contract=True,
    )

    with pytest.raises(MetricContractValidationError) as exc_info:
        artifact.record_main_experiment(
            quest_root,
            run_id="main-strict-001",
            title="Missing F1 main run",
            hypothesis="The adapter improves only one reported metric.",
            setup="Reuse the accepted baseline pipeline.",
            execution="Ran the main evaluation once.",
            results="Accuracy is present but F1 is missing.",
            conclusion="This should fail strict metric validation.",
            metric_rows=[{"metric_id": "acc", "value": 0.92, "scope_id": "full"}],
            strict_metric_contract=True,
        )

    exc = exc_info.value
    assert exc.error_code == "main_experiment_metric_validation_failed"
    assert exc.details["validation_stage"] == "main_experiment"
    assert exc.details["baseline_metric_ids"] == ["acc", "f1"]
    assert exc.details["missing_metric_ids"] == ["f1"]
    assert exc.details["extra_metric_ids"] == []


class _FakeHeaders:
    def __init__(self, charset: str = "utf-8") -> None:
        self._charset = charset

    def get_content_charset(self) -> str:
        return self._charset


class _FakeUrlopenResponse:
    def __init__(self, body: str, *, charset: str = "utf-8") -> None:
        self._body = body.encode(charset)
        self.headers = _FakeHeaders(charset)

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_memory_documents_and_promotion(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("memory quest")
    quest_root = Path(quest["quest_root"])
    memory = MemoryService(temp_home)

    card = memory.write_card(
        scope="quest",
        kind="ideas",
        title="Reusable idea",
        body="A compact durable note.",
        quest_root=quest_root,
        quest_id=quest["quest_id"],
        tags=["test"],
    )
    assert Path(card["path"]).exists()

    documents = quest_service.list_documents(quest["quest_id"])
    memory_doc = next(item for item in documents if item["document_id"].startswith("memory::"))
    opened = quest_service.open_document(quest["quest_id"], memory_doc["document_id"])
    assert opened["writable"] is True
    assert "A compact durable note." in opened["content"]

    promoted = memory.promote_to_global(path=card["path"], quest_root=quest_root)
    assert Path(promoted["path"]).exists()
    assert promoted["scope"] == "global"

    skill_doc = next(item for item in documents if item["document_id"].startswith("skill::"))
    skill_opened = quest_service.open_document(quest["quest_id"], skill_doc["document_id"])
    assert skill_opened["writable"] is False


def test_memory_list_recent_and_search_prefer_latest_updates(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("memory ordering quest")
    quest_root = Path(quest["quest_root"])
    memory = MemoryService(temp_home)

    older = memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Older lesson",
        body="adapter metric contract",
        quest_root=quest_root,
        quest_id=quest["quest_id"],
    )
    newer = memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Newer lesson",
        body="adapter metric contract with better evidence",
        quest_root=quest_root,
        quest_id=quest["quest_id"],
    )

    for card, updated_at in (
        (older, "2026-03-11T10:00:00+00:00"),
        (newer, "2026-03-11T11:00:00+00:00"),
    ):
        path = Path(card["path"])
        metadata, body = load_markdown_document(path)
        metadata["created_at"] = updated_at
        metadata["updated_at"] = updated_at
        path.write_text(dump_markdown_document(metadata, body), encoding="utf-8")

    recent = memory.list_recent(scope="quest", quest_root=quest_root, kind="knowledge", limit=2)
    assert [item["title"] for item in recent] == [newer["title"], older["title"]]

    search = memory.search(
        "adapter metric contract",
        scope="quest",
        quest_root=quest_root,
        kind="knowledge",
        limit=2,
    )
    assert [item["title"] for item in search] == [newer["title"], older["title"]]


def test_shared_memory_visibility_reads_other_quests_but_opens_them_read_only(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    config_manager = ConfigManager(temp_home)
    config_manager.ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_local = quest_service.create("shared visibility local quest")
    quest_remote = quest_service.create("shared visibility remote quest")
    local_root = Path(quest_local["quest_root"])
    remote_root = Path(quest_remote["quest_root"])
    memory = MemoryService(temp_home)

    local_card = memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Local durable note",
        body="local-only durable note",
        quest_root=local_root,
        quest_id=quest_local["quest_id"],
    )
    remote_card = memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Remote durable note",
        body="cross quest shared evidence",
        quest_root=remote_root,
        quest_id=quest_remote["quest_id"],
    )

    default_visible = memory.list_visible_quest_cards(
        active_quest_root=local_root,
        active_quest_id=quest_local["quest_id"],
        limit=10,
    )
    assert any(item["title"] == "Local durable note" for item in default_visible)
    assert all(item.get("source_quest_id") != quest_remote["quest_id"] for item in default_visible)

    config = config_manager.load_runtime_config()
    config["memory"] = {"read_visibility_mode": "shared_across_quests"}
    config_manager.save_named_payload("config", config)

    visible = memory.list_visible_quest_cards(
        active_quest_root=local_root,
        active_quest_id=quest_local["quest_id"],
        limit=10,
    )
    visible_titles = [item["title"] for item in visible]
    assert "Local durable note" in visible_titles
    assert "Remote durable note" in visible_titles
    assert visible_titles.index("Local durable note") < visible_titles.index("Remote durable note")
    shared_card = next(item for item in visible if item["title"] == "Remote durable note")
    assert shared_card["source_quest_id"] == quest_remote["quest_id"]
    assert shared_card["shared"] is True
    assert shared_card["writable"] is False
    assert shared_card["document_id"] == f"sharedmemory::{quest_remote['quest_id']}::knowledge/remote-durable-note.md"

    shared_search = memory.search_visible_quest_cards(
        "cross quest shared evidence",
        active_quest_root=local_root,
        active_quest_id=quest_local["quest_id"],
        limit=10,
    )
    assert [item["title"] for item in shared_search] == ["Remote durable note"]

    opened = quest_service.open_document(quest_local["quest_id"], shared_card["document_id"])
    assert opened["writable"] is False
    assert opened["scope"] == "shared_quest_memory"
    assert opened["source_quest_id"] == quest_remote["quest_id"]
    assert "cross quest shared evidence" in opened["content"]

    app = DaemonApp(temp_home)
    api_cards = app.handlers.quest_memory(quest_local["quest_id"])
    local_relative = Path(local_card["path"]).relative_to(local_root / "memory").as_posix()
    local_document_id = f"memory::{local_relative}"
    assert any(item["document_id"] == local_document_id for item in api_cards)
    assert any(item["document_id"] == shared_card["document_id"] for item in api_cards)
    api_shared_card = next(item for item in api_cards if item["document_id"] == shared_card["document_id"])
    assert api_shared_card["writable"] is False
    assert Path(remote_card["path"]).exists()


def test_memory_read_resolves_sharedmemory_document_id_from_other_quest(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_local = quest_service.create("shared memory read local")
    quest_remote = quest_service.create("shared memory read remote")
    local_root = Path(quest_local["quest_root"])
    remote_root = Path(quest_remote["quest_root"])
    memory = MemoryService(temp_home)

    remote_card = memory.write_card(
        scope="quest",
        kind="knowledge",
        title="Cross quest checkpoint",
        body="checkpoint body for cross-quest read",
        quest_root=remote_root,
        quest_id=quest_remote["quest_id"],
    )
    relative = Path(remote_card["path"]).relative_to(remote_root / "memory").as_posix()
    document_id = f"sharedmemory::{quest_remote['quest_id']}::{relative}"

    opened = memory.read_card(path=document_id, scope="quest", quest_root=local_root)
    assert opened["path"] == str(Path(remote_card["path"]))
    assert opened["body"].strip() == "checkpoint body for cross-quest read"

    with pytest.raises(FileNotFoundError):
        memory.read_card(
            path=f"sharedmemory::{quest_remote['quest_id']}::knowledge/missing-card.md",
            scope="quest",
            quest_root=local_root,
        )


def test_memory_document_open_uses_quest_root_when_active_workspace_is_worktree(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("memory worktree open contract")
    quest_root = Path(quest["quest_root"])
    memory = MemoryService(temp_home)

    card = memory.write_card(
        scope="quest",
        kind="papers",
        title="Closest prior work cluster",
        body="Memory content should still resolve from quest root.",
        quest_root=quest_root,
        quest_id=quest["quest_id"],
    )

    worktree_root = quest_root / ".ds" / "worktrees" / "idea-branch-001"
    worktree_root.mkdir(parents=True, exist_ok=True)
    (worktree_root / "brief.md").write_text("# Worktree brief\n", encoding="utf-8")
    quest_service.update_research_state(
        quest_root,
        current_workspace_root=str(worktree_root),
        research_head_worktree_root=str(worktree_root),
    )

    relative_memory_path = Path(card["path"]).relative_to(quest_root / "memory").as_posix()
    opened = quest_service.open_document(quest["quest_id"], f"memory::{relative_memory_path}")

    assert opened["writable"] is True
    assert opened["path"] == str(Path(card["path"]))
    assert "Memory content should still resolve from quest root." in opened["content"]


def test_refresh_summary_mirrors_to_quest_root_when_active_workspace_is_worktree(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("refresh summary worktree mirror")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    worktree_root = quest_root / ".ds" / "worktrees" / "idea-branch-mirror"
    worktree_root.mkdir(parents=True, exist_ok=True)
    quest_service.update_research_state(
        quest_root,
        current_workspace_root=str(worktree_root),
        research_head_worktree_root=str(worktree_root),
    )

    result = artifact.refresh_summary(quest_root, reason="mirror to quest root")
    assert result["ok"] is True

    workspace_summary = Path(result["summary_path"])
    quest_root_summary = Path(result["quest_root_summary_path"])
    assert workspace_summary == worktree_root / "SUMMARY.md"
    assert quest_root_summary == quest_root / "SUMMARY.md"
    assert workspace_summary.exists()
    assert quest_root_summary.exists()
    assert workspace_summary.read_text(encoding="utf-8") == quest_root_summary.read_text(encoding="utf-8")
    assert "mirror to quest root" in quest_root_summary.read_text(encoding="utf-8")


def test_refresh_summary_writes_once_when_workspace_equals_quest_root(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("refresh summary no worktree")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.refresh_summary(quest_root, reason="no worktree")
    assert result["ok"] is True
    assert Path(result["summary_path"]) == quest_root / "SUMMARY.md"
    assert Path(result["quest_root_summary_path"]) == quest_root / "SUMMARY.md"
    assert (quest_root / "SUMMARY.md").exists()


def test_record_auto_refreshes_quest_root_summary_without_extra_artifact(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("auto refresh on record")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    summary_path = quest_root / "SUMMARY.md"
    assert summary_path.read_text(encoding="utf-8").strip() != "" or not summary_path.exists()
    pre_summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""

    result = artifact.record(
        quest_root,
        {
            "kind": "report",
            "status": "completed",
            "report_id": "report-auto-1",
            "summary": "first user-driven artifact",
            "reason": "exercise auto-refresh hook",
            "source": {"kind": "agent"},
        },
    )
    assert result["ok"] is True

    post_summary = summary_path.read_text(encoding="utf-8")
    assert post_summary != pre_summary
    assert "auto after report" in post_summary
    assert result["artifact_id"] in post_summary

    summary_refresh_artifacts = [
        item for item in artifact.recent(quest_root, limit=20)
        if item.get("kind") == "reports"
    ]
    summary_refresh_payloads = []
    for item in summary_refresh_artifacts:
        payload = read_json(Path(item["path"]), {})
        if payload.get("report_type") == "summary_refresh":
            summary_refresh_payloads.append(payload)
    assert summary_refresh_payloads == []


def test_record_skips_auto_refresh_when_record_is_summary_refresh(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("no recursion")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    explicit = artifact.refresh_summary(quest_root, reason="explicit user-driven refresh")
    assert explicit["ok"] is True
    assert explicit["artifact"] is not None

    summary_refresh_payloads = []
    for item in artifact.recent(quest_root, limit=20):
        if item.get("kind") != "reports":
            continue
        payload = read_json(Path(item["path"]), {})
        if payload.get("report_type") == "summary_refresh":
            summary_refresh_payloads.append(payload)
    assert len(summary_refresh_payloads) == 1


def test_artifact_interact_and_prepare_branch(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.append_message(quest["quest_id"], role="user", content="请先告诉我 baseline 情况。", source="web")
    result = artifact.interact(
        quest_root,
        kind="progress",
        message="Baseline is ready; I am summarizing the current metrics.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=True,
    )
    assert result["status"] == "ok"
    assert result["delivered"] is True
    assert result["recent_inbound_messages"]

    outbox = temp_home / "logs" / "connectors" / "local" / "outbox.jsonl"
    assert outbox.exists()
    records = [json.loads(line) for line in outbox.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("Baseline is ready" in (item.get("message") or "") for item in records)

    branch = artifact.prepare_branch(quest_root, run_id="run-main-001")
    assert branch["ok"] is True
    assert branch["branch"] == "run/run-main-001"
    assert Path(branch["worktree_root"]).exists()


def test_artifact_mailbox_preserves_user_message_attachments(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact attachment mailbox quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="Please inspect the attached PDF.",
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
    result = artifact.interact(
        quest_root,
        kind="progress",
        message="I am picking up the latest inbound request.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert result["recent_inbound_messages"]
    latest = result["recent_inbound_messages"][-1]
    assert latest["conversation_id"] == "qq:direct:openid-123"
    assert latest["attachments"][0]["name"] == "report.pdf"
    assert latest["attachments"][0]["extracted_text_path"] == "attachments/report.txt"
    assert "用户刚刚发送了附件" in result["agent_instruction"]
    assert "attachments/report.txt" in result["agent_instruction"]


def test_artifact_managed_git_flow_updates_research_state_and_mirrors_analysis(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact flow quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root)

    created = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A lightweight adapter improves generalization.",
        mechanism="Insert a small residual adapter before the head.",
        decision_reason="This is the strongest next idea.",
        next_target="experiment",
        draft_markdown="# Adapter route draft\n\n## Code-Level Change Plan\n\nPatch the adapter path.\n",
    )
    idea_worktree = Path(created["worktree_root"])
    idea_md_path = Path(created["idea_md_path"])
    idea_draft_path = Path(created["idea_draft_path"])
    assert created["branch"].startswith(f"idea/{quest['quest_id']}-")
    assert idea_worktree.exists()
    assert idea_md_path.exists()
    assert idea_draft_path.exists()
    assert "Adapter route draft" in idea_draft_path.read_text(encoding="utf-8")
    assert created["guidance"]
    assert created["recommended_skill_reads"] == ["experiment"]
    assert created["suggested_artifact_calls"]
    assert created["next_instruction"]
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "experiment"

    revised = artifact.submit_idea(
        quest_root,
        mode="revise",
        idea_id=created["idea_id"],
        title="Adapter route v2",
        problem="Baseline still underfits hard examples.",
        hypothesis="A tuned adapter improves hard-example recall.",
        mechanism="Tune the adapter depth and placement.",
        decision_reason="Refine the same active route before coding.",
        next_target="experiment",
        draft_markdown="# Adapter route v2 draft\n\n## Risks / Caveats / Implementation Notes\n\nMind the hard examples.\n",
    )
    assert revised["worktree_root"] == created["worktree_root"]
    assert "Adapter route v2" in idea_md_path.read_text(encoding="utf-8")
    assert "Adapter route v2 draft" in idea_draft_path.read_text(encoding="utf-8")
    assert revised["guidance"]
    assert revised["recommended_skill_reads"] == ["experiment"]
    assert revised["suggested_artifact_calls"]
    assert revised["next_instruction"]

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Ablation suite",
        campaign_goal="Stress-test the promoted idea.",
        slices=[
            {
                "slice_id": "ablation",
                "title": "Adapter ablation",
                "goal": "Remove the adapter and compare.",
                "required_changes": "Disable the adapter path only.",
                "metric_contract": "Report full validation metrics.",
                "required_baselines": [
                    {
                        "baseline_id": "adapter-ablation-baseline",
                        "reason": "Need a clean comparator for the ablation slice.",
                        "benchmark": "val",
                        "split": "full",
                    }
                ],
            },
            {
                "slice_id": "robustness",
                "title": "Robustness check",
                "goal": "Run the intended robustness configuration.",
                "required_changes": "Apply the robustness config only.",
                "metric_contract": "Report the same full evaluation metrics.",
            },
        ],
    )
    assert campaign["ok"] is True
    assert campaign["campaign_id"]
    assert len(campaign["slices"]) == 2
    assert campaign["guidance"]

    assert campaign["recommended_skill_reads"]
    assert campaign["suggested_artifact_calls"]
    assert campaign["next_instruction"]
    first_slice = campaign["slices"][0]
    second_slice = campaign["slices"][1]
    assert first_slice["required_baselines"][0]["baseline_id"] == "adapter-ablation-baseline"
    assert Path(first_slice["worktree_root"]).exists()
    assert Path(second_slice["worktree_root"]).exists()
    analysis_inventory_path = quest_root / "artifacts" / "baselines" / "analysis_inventory.json"
    analysis_inventory = read_json(analysis_inventory_path, {})
    assert analysis_inventory_path.exists()
    assert analysis_inventory["entries"][0]["baseline_id"] == "adapter-ablation-baseline"
    assert analysis_inventory["entries"][0]["status"] == "required"

    state_after_campaign = quest_service.read_research_state(quest_root)
    assert state_after_campaign["active_analysis_campaign_id"] == campaign["campaign_id"]
    assert state_after_campaign["current_workspace_root"] == first_slice["worktree_root"]
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "analysis-campaign"

    analysis_baseline_root = quest_root / "baselines" / "local" / "adapter-ablation-baseline"
    analysis_baseline_root.mkdir(parents=True, exist_ok=True)
    (analysis_baseline_root / "README.md").write_text("# Analysis baseline\n", encoding="utf-8")

    first_record = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the adapter path only.",
        execution="Ran the full validation sweep.",
        results="Accuracy dropped as expected.",
        evidence_paths=["experiments/analysis/ablation/result.json"],
        metric_rows=[{"metric_id": "acc", "value": 0.84, "direction": "higher_better"}],
        comparison_baselines=[
            {
                "baseline_id": "adapter-ablation-baseline",
                "baseline_root_rel_path": "baselines/local/adapter-ablation-baseline",
                "benchmark": "val",
                "split": "full",
                "metrics_summary": {"acc": 0.8},
                "published": True,
            }
        ],
    )
    assert first_record["ok"] is True
    assert first_record["completed"] is False
    assert first_record["next_slice"]["slice_id"] == "robustness"
    assert Path(first_record["mirror_path"]).exists()
    assert Path(first_record["result_json_path"]).exists()
    slice_result_payload = read_json(first_record["result_json_path"], {})
    assert slice_result_payload["metrics_summary"] == {"acc": 0.84}
    assert slice_result_payload["metric_rows"][0]["metric_id"] == "acc"
    assert slice_result_payload["metric_rows"][0]["numeric_value"] == pytest.approx(0.84)
    assert slice_result_payload["metric_contract"]["primary_metric_id"] == "acc"
    assert slice_result_payload["comparison_baselines"][0]["baseline_id"] == "adapter-ablation-baseline"
    analysis_inventory = read_json(analysis_inventory_path, {})
    registered_entry = next(
        item for item in analysis_inventory["entries"] if item["baseline_id"] == "adapter-ablation-baseline"
    )
    assert registered_entry["status"] == "registered"
    assert registered_entry["baseline_root_rel_path"] == "baselines/local/adapter-ablation-baseline"

    second_record = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="robustness",
        setup="Apply the robustness configuration only.",
        execution="Ran the full robustness sweep.",
        results="The method stayed stable under the robustness setting.",
        evidence_paths=["experiments/analysis/robustness/result.json"],
        metric_rows=[{"metric_id": "acc", "value": 0.86, "direction": "higher_better"}],
    )
    assert second_record["ok"] is True
    assert second_record["completed"] is True
    assert second_record["returned_to_branch"] == created["branch"]
    assert Path(second_record["summary_path"]).exists()

    final_state = quest_service.read_research_state(quest_root)
    assert final_state["active_analysis_campaign_id"] is None
    assert final_state["current_workspace_branch"] == second_record["writing_branch"]
    assert final_state["current_workspace_root"] == second_record["writing_worktree_root"]
    assert final_state["paper_parent_branch"] == created["branch"]
    assert final_state["paper_parent_worktree_root"] == str(idea_worktree)
    assert final_state["workspace_mode"] == "paper"
    assert final_state["research_head_branch"] == created["branch"]
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "write"

    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    campaign_event = next(
        item
        for item in reversed(events)
        if item.get("type") == "artifact.recorded"
        and item.get("flow_type") == "analysis_campaign"
        and item.get("protocol_step") == "complete"
    )
    assert campaign_event["workspace_root"] == str(idea_worktree)
    assert campaign_event["details"]["slice_count"] == 2


def test_submit_idea_candidate_mode_records_branchless_candidate_then_allows_promotion(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("idea candidate quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-candidate")

    baseline_snapshot = quest_service.snapshot(quest["quest_id"])
    assert baseline_snapshot["active_anchor"] == "idea"

    candidate = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="candidate",
        title="Candidate route",
        problem="Baseline saturates on rare cases.",
        hypothesis="A candidate adapter path may improve the long tail.",
        mechanism="Try a narrow adapter before the head.",
        method_brief="Target the rare-case bottleneck while keeping the baseline comparison surface unchanged.",
        selection_scores={"utility": 0.82, "distinctness": 0.61},
        mechanism_family="adapter",
        change_layer="Tier2",
        source_lens="baseline_refinement",
        decision_reason="Record this candidate before ranking and promotion.",
        next_target="optimize",
        draft_markdown="# Candidate route draft\n\n## Code-Level Change Plan\n\nTry the narrow adapter.\n",
    )

    assert candidate["ok"] is True
    assert candidate["submission_mode"] == "candidate"
    assert candidate["promotable"] is True
    assert candidate["method_brief"] == "Target the rare-case bottleneck while keeping the baseline comparison surface unchanged."
    assert candidate["selection_scores"] == {"utility": 0.82, "distinctness": 0.61}
    assert candidate["mechanism_family"] == "adapter"
    assert candidate["change_layer"] == "Tier2"
    assert candidate["source_lens"] == "baseline_refinement"
    assert "branch" not in candidate
    assert Path(candidate["candidate_root"]).exists()
    assert Path(candidate["idea_md_path"]).exists()
    assert Path(candidate["idea_draft_path"]).exists()

    candidate_metadata, _ = load_markdown_document(Path(candidate["idea_md_path"]))
    assert candidate_metadata["submission_mode"] == "candidate"
    assert candidate_metadata["kind"] == "idea_candidate"
    assert candidate_metadata["method_brief"] == candidate["method_brief"]
    assert candidate_metadata["selection_scores"] == candidate["selection_scores"]
    assert candidate_metadata["mechanism_family"] == candidate["mechanism_family"]
    assert candidate_metadata["change_layer"] == candidate["change_layer"]
    assert candidate_metadata["source_lens"] == candidate["source_lens"]

    candidate_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": candidate["idea_id"],
            "selection_type": "idea_candidate",
            "branch_name": candidate["parent_branch"],
            "stage_key": "idea",
        },
    )
    assert candidate_view["title"] == "Candidate Brief · Candidate route"
    assert candidate_view["details"]["idea"]["method_brief"] == candidate["method_brief"]
    assert candidate_view["details"]["idea"]["selection_scores"] == candidate["selection_scores"]
    assert candidate_view["details"]["idea"]["candidate_root"] == "memory/ideas/_candidates/" + candidate["idea_id"]

    after_candidate_snapshot = quest_service.snapshot(quest["quest_id"])
    assert after_candidate_snapshot["active_anchor"] == "idea"

    branches = artifact.list_research_branches(quest_root)
    assert branches["ok"] is True
    assert all(item.get("idea_id") != candidate["idea_id"] for item in branches["branches"])

    promoted = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="line",
        source_candidate_id=candidate["idea_id"],
        title="Promoted route",
        problem="Promote the candidate into a real branch.",
        hypothesis="The candidate is now strong enough for a durable line.",
        mechanism="Carry the adapter plan into a branch-backed implementation line.",
        method_brief="Promote the narrow adapter route into a durable optimization line.",
        selection_scores={"utility": 0.9, "distinctness": 0.58},
        mechanism_family="adapter",
        change_layer="Tier2",
        source_lens="baseline_refinement",
        decision_reason="Promote the candidate into the active optimization line.",
        next_target="optimize",
    )

    assert promoted["ok"] is True
    assert promoted["submission_mode"] == "line"
    assert promoted["source_candidate_id"] == candidate["idea_id"]
    assert promoted["method_brief"] == "Promote the narrow adapter route into a durable optimization line."
    assert promoted["selection_scores"] == {"utility": 0.9, "distinctness": 0.58}
    assert promoted["mechanism_family"] == "adapter"
    assert promoted["change_layer"] == "Tier2"
    assert promoted["source_lens"] == "baseline_refinement"
    assert promoted["branch"].startswith(f"idea/{quest['quest_id']}-")
    assert Path(promoted["worktree_root"]).exists()
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "optimize"

    branch_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": promoted["branch"],
            "selection_type": "branch_node",
            "branch_name": promoted["branch"],
            "stage_key": "idea",
        },
    )
    assert branch_view["details"]["branch"]["method_brief"] == promoted["method_brief"]
    assert branch_view["details"]["branch"]["selection_scores"] == promoted["selection_scores"]
    assert branch_view["details"]["branch"]["mechanism_family"] == promoted["mechanism_family"]
    assert branch_view["details"]["branch"]["change_layer"] == promoted["change_layer"]
    assert branch_view["details"]["branch"]["source_lens"] == promoted["source_lens"]


def test_get_optimization_frontier_summarizes_briefs_lines_candidates_and_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "optimization frontier quest",
        startup_contract={"need_research_paper": False},
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-frontier")

    candidate = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="candidate",
        title="Frontier candidate",
        problem="Need a branchless direction for later promotion.",
        hypothesis="A branchless brief captures a possible new route.",
        mechanism="Delay branch creation until ranking is finished.",
        method_brief="Keep the direction branchless until ranking is complete.",
        selection_scores={"utility": 0.73, "distinctness": 0.67},
        mechanism_family="ranking_gate",
        change_layer="Tier1",
        source_lens="search_widening",
        decision_reason="Keep this direction in the candidate pool.",
        next_target="optimize",
    )

    first_line = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="line",
        title="Leading line",
        problem="Baseline saturates on hard examples.",
        hypothesis="A stronger adapter route should improve hard-example recall.",
        mechanism="Insert a residual adapter before the head.",
        decision_reason="Promote the strongest current line.",
        next_target="optimize",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-frontier-001",
        title="Leading line main run",
        hypothesis="The leading line helps.",
        setup="Use the baseline recipe.",
        execution="Ran validation.",
        results="Accuracy improved.",
        conclusion="Use this result as the current incumbent.",
        metric_rows=[{"metric_id": "acc", "value": 0.87}],
    )

    second_line = artifact.submit_idea(
        quest_root,
        mode="create",
        submission_mode="line",
        lineage_intent="branch_alternative",
        title="Trailing line",
        problem="Try an alternative mechanism from the same family.",
        hypothesis="A sibling route may still be worth comparing.",
        mechanism="Change the intervention point while keeping the same parent foundation.",
        decision_reason="Keep one alternative line alive.",
        next_target="optimize",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-frontier-002",
        title="Trailing line main run",
        hypothesis="The trailing line is weaker.",
        setup="Use the same protocol.",
        execution="Ran validation.",
        results="Accuracy dropped slightly.",
        conclusion="This line is weaker than the current incumbent.",
        metric_rows=[{"metric_id": "acc", "value": 0.79}],
    )

    artifact.record(
        quest_root,
        {
            "kind": "report",
            "status": "proposed",
            "report_type": "optimization_candidate",
            "candidate_id": "cand-frontier-001",
            "idea_id": first_line["idea_id"],
            "branch": first_line["branch"],
            "strategy": "exploit",
            "summary": "Candidate patch queued for smoke.",
            "details": {
                "candidate_id": "cand-frontier-001",
                "change_plan": "Tighten the adapter bottleneck.",
                "expected_gain": "Better tail accuracy.",
            },
        },
        workspace_root=Path(first_line["worktree_root"]),
    )

    frontier = artifact.get_optimization_frontier(quest_root)

    assert frontier["ok"] is True
    payload = frontier["optimization_frontier"]
    assert payload["mode"] == "exploit"
    assert payload["best_branch"]["branch_name"] == "run/main-frontier-001"
    assert payload["best_run"]["run_id"] == "main-frontier-001"
    assert payload["candidate_backlog"]["candidate_brief_count"] == 1
    assert payload["candidate_backlog"]["implementation_candidate_count"] == 1
    assert payload["candidate_backlog"]["active_implementation_candidate_count"] == 1
    assert payload["candidate_briefs"][0]["idea_id"] == candidate["idea_id"]
    assert payload["candidate_briefs"][0]["method_brief"] == "Keep the direction branchless until ranking is complete."
    assert payload["candidate_briefs"][0]["selection_scores"] == {"utility": 0.73, "distinctness": 0.67}
    assert payload["candidate_briefs"][0]["mechanism_family"] == "ranking_gate"
    assert payload["candidate_briefs"][0]["change_layer"] == "Tier1"
    assert payload["candidate_briefs"][0]["source_lens"] == "search_widening"
    assert payload["implementation_candidates"][0]["candidate_id"] == "cand-frontier-001"
    assert payload["best_branch_recent_candidates"][0]["candidate_id"] == "cand-frontier-001"
    assert len(payload["top_branches"]) >= 2
    assert payload["recommended_next_actions"]


def test_algorithm_first_baseline_gate_advances_into_optimize_anchor(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "algorithm-first baseline gate quest",
        startup_contract={"need_research_paper": False},
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-algorithm-first")

    assert result["ok"] is True
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "optimize"


def test_paper_outline_flow_and_outline_bound_analysis_campaign(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper outline quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    baseline_root = quest_root / "baselines" / "local" / "baseline-outline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/local/baseline-outline",
        baseline_id="baseline-outline",
        summary="Baseline confirmed for outline-bound analysis.",
        metrics_summary={"acc": 0.88},
        metric_contract={"primary_metric_id": "acc", "direction": "maximize"},
        primary_metric={"metric_id": "acc", "value": 0.88},
    )
    created = artifact.submit_idea(
        quest_root,
        title="Outline-aware idea",
        problem="Need a stronger analysis plan.",
        hypothesis="Outline-driven analysis improves research discipline.",
        mechanism="Bind analysis tasks to paper questions and experiment designs.",
        expected_gain="Cleaner downstream writing.",
        decision_reason="Promote this line for paper-oriented experimentation.",
    )
    assert created["ok"] is True

    candidate_1 = artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Outline A",
        note="First draft outline.",
        story="Tell the motivation-first story.",
        ten_questions=["Why now?", "Why this baseline?"],
        detailed_outline={
            "title": "Outline A",
            "abstract": "Abstract A",
            "research_questions": ["RQ1"],
            "methodology": "Method A",
            "experimental_designs": ["Exp-A"],
            "contributions": ["C1"],
        },
        review_result="candidate",
    )
    candidate_2 = artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Outline B",
        note="Second draft outline.",
        story="Tell the evidence-first story.",
        ten_questions=["What changed?", "Why does it matter?"],
        detailed_outline={
            "title": "Outline B",
            "abstract": "Abstract B",
            "research_questions": ["RQ-main"],
            "methodology": "Method B",
            "experimental_designs": ["Exp-main"],
            "contributions": ["C-main"],
        },
        review_result="preferred",
    )
    candidate_3 = artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Outline C",
        note="Third draft outline.",
        story="Tell the robustness-first story.",
        ten_questions=["What might fail?", "How do we know?"],
        detailed_outline={
            "title": "Outline C",
            "abstract": "Abstract C",
            "research_questions": ["RQ-aux"],
            "methodology": "Method C",
            "experimental_designs": ["Exp-aux"],
            "contributions": ["C-aux"],
        },
        review_result="backup",
    )
    assert candidate_1["outline_id"] == "outline-001"
    assert candidate_2["outline_id"] == "outline-002"
    assert candidate_3["outline_id"] == "outline-003"
    candidate_delta = _assert_artifact_delta(
        candidate_1["artifact_delta"],
        delta_kind="paper_outline_candidate",
        expected_labels={"outline_json", "artifact_json"},
    )
    assert candidate_delta["metadata"]["outline_id"] == "outline-001"

    selected = artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-002",
        selected_reason="This version best matches the intended main claim and experiment design.",
    )
    assert selected["ok"] is True
    assert Path(selected["selected_outline_path"]).exists()
    assert Path(selected["outline_manifest_path"]).exists()
    assert Path(selected["paper_line_state_path"]).exists()
    assert Path(selected["outline_selection_path"]).exists()
    selected_delta = _assert_artifact_delta(
        selected["artifact_delta"],
        delta_kind="paper_outline_selected",
        expected_labels={
            "selected_outline_json",
            "outline_manifest_json",
            "outline_selection_md",
            "paper_line_state_json",
            "artifact_json",
        },
    )
    assert selected_delta["metadata"]["outline_id"] == "outline-002"
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "write"

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Outline-bound analysis",
        campaign_goal="Answer the selected paper questions cleanly.",
        selected_outline_ref="outline-002",
        research_questions=["RQ-main"],
        experimental_designs=["Exp-main"],
        todo_items=[
            {
                "exp_id": "EXP-001",
                "todo_id": "todo-001",
                "slice_id": "ablation",
                "title": "Ablation for RQ-main",
                "research_question": "RQ-main",
                "experimental_design": "Exp-main",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "analysis_role": "ablation",
                "target_display": "Main ablation",
                "section_id": "analysis-main",
                "item_id": "AN-001",
                "claim_links": ["C1"],
                "completion_condition": "Show whether the core module is necessary.",
            }
        ],
        slices=[
            {
                "slice_id": "ablation",
                "title": "Ablation",
                "goal": "Disable the core module and compare.",
                "hypothesis": "Performance will drop without the core module.",
                "required_changes": "Disable the core module only.",
                "metric_contract": "Report full validation metrics.",
                "section_id": "analysis-main",
                "item_id": "AN-001",
                "paper_role": "main_text",
                "claim_links": ["C1"],
            }
        ],
    )
    assert campaign["ok"] is True
    assert Path(campaign["todo_manifest_path"]).exists()
    manifest = read_json(quest_root / ".ds" / "analysis_campaigns" / f"{campaign['campaign_id']}.json", {})
    assert manifest["selected_outline_ref"] == "outline-002"
    assert manifest["todo_items"][0]["slice_id"] == "ablation"
    assert manifest["todo_items"][0]["item_id"] == "AN-001"
    assert manifest["paper_line_branch"]
    assert manifest["paper_line_root"]
    assert manifest["slices"][0]["research_question"] == "RQ-main"
    assert manifest["slices"][0]["experimental_design"] == "Exp-main"
    assert manifest["slices"][0]["section_id"] == "analysis-main"
    outline_result_table = read_json(
        Path(selected["outline_manifest_path"]).parent / "sections" / "analysis-main" / "result_table.json",
        {},
    )
    assert outline_result_table["rows"][0]["item_id"] == "AN-001"
    experiment_matrix = read_json(quest_root / "paper" / "paper_experiment_matrix.json", {})
    assert any(row["item_id"] == "AN-001" for row in experiment_matrix["rows"])

    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": f"stage:{created['branch']}:analysis-campaign",
            "selection_type": "stage_node",
            "branch_name": created["branch"],
            "stage_key": "analysis-campaign",
        },
    )
    assert stage_view["stage_key"] == "analysis"
    assert stage_view["details"]["analysis"]["selected_outline_ref"] == "outline-002"
    assert stage_view["details"]["analysis"]["todo_items"][0]["slice_id"] == "ablation"


def test_writing_facing_analysis_campaign_requires_selected_outline_and_todo_mapping(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("writing-facing analysis gate quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-outline-gate")
    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Outline-gated route",
        problem="Writing-facing analysis should not start free-floating.",
        hypothesis="The campaign must bind to a selected outline first.",
        mechanism="Require outline-bound todo metadata.",
        decision_reason="Prepare the writing-facing route.",
        next_target="experiment",
    )

    with pytest.raises(ValueError) as exc_info:
        artifact.create_analysis_campaign(
            quest_root,
            campaign_title="Missing outline gate",
            campaign_goal="This campaign should be rejected before writing begins.",
            research_questions=["RQ-main"],
            experimental_designs=["Exp-main"],
            todo_items=[
                {
                    "todo_id": "todo-001",
                    "slice_id": "ablation",
                    "title": "Ablation for RQ-main",
                    "research_question": "RQ-main",
                    "experimental_design": "Exp-main",
                    "completion_condition": "Run the ablation fully.",
                }
            ],
            slices=[
                {
                    "slice_id": "ablation",
                    "title": "Ablation",
                    "goal": "Disable the core module and compare.",
                }
            ],
        )

        assert "selected_outline_ref" in str(exc_info.value)
        assert "submit_paper_outline" in str(exc_info.value)
        assert "analysis-lite" in str(exc_info.value)


def test_artifact_stage_milestones_emit_semantic_connector_messages(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    def fake_qq_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_qq_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("semantic connector milestones quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    quest_service.bind_source(quest["quest_id"], "qq:direct:semantic-user")

    long_problem = (
        "The baseline saturates too early during the full evaluation sweep and leaves the hard examples unresolved.\n\n"
        "This second paragraph must remain visible in the connector milestone so the user receives the full rationale instead of a clipped notification."
    )
    long_hypothesis = (
        "A compact adapter should preserve the gain while keeping the intervention auditable.\n\n"
        "The connector update should keep both paragraphs intact, because this is the user-facing stage summary."
    )
    long_mechanism = (
        "Insert a compact residual adapter in the main path and keep the rest of the protocol fixed.\n\n"
        "The message should show the exact mechanism without collapsing it into an ellipsis."
    )
    long_takeaway = (
        "The compact adapter improves the primary metric against the confirmed baseline under the full validation recipe.\n\n"
        "This second paragraph must also survive delivery so the milestone preserves the real conclusion."
    )
    long_claim_impact = (
        "The ablation strengthens the central mechanism claim because the gain disappears when the adapter is removed.\n\n"
        "This follow-up paragraph should remain visible in the connector milestone."
    )
    long_bundle_summary = (
        "The draft, manifest, and PDF reference are ready for final review on the paper branch.\n\n"
        "This second paragraph should also be delivered in full so writing completion does not degrade into a clipped notification."
    )

    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-semantic")
    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Semantic route",
        problem=long_problem,
        hypothesis=long_hypothesis,
        mechanism=long_mechanism,
        decision_reason="Promote the route with the clearest mechanism.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="semantic-main-001",
        title="Semantic main run",
        hypothesis="The compact adapter improves the primary metric.",
        setup="Use the full baseline recipe.",
        execution="Ran the full validation sweep once.",
        results="Accuracy improved over the confirmed baseline.",
        conclusion="The gain is strong enough to justify analysis and writing.",
        metric_rows=[{"metric_id": "acc", "value": 0.87}],
        evaluation_summary={
            "takeaway": long_takeaway,
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
        title="Semantic outline",
        note="Promote the evidence-first version.",
        story="Tell the evidence-first story with one main ablation.",
        ten_questions=["What changed?", "Why is the gain real?"],
        detailed_outline={
            "title": "Semantic outline",
            "research_questions": ["RQ-semantic"],
            "experimental_designs": ["Ablation-semantic"],
            "contributions": ["C-semantic"],
        },
        review_result="preferred",
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id=candidate["outline_id"],
        selected_reason="This outline matches the main claim and the evidence plan.",
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Semantic analysis",
        campaign_goal="Verify the core claim with one decisive ablation.",
        selected_outline_ref=candidate["outline_id"],
        research_questions=["RQ-semantic"],
        experimental_designs=["Ablation-semantic"],
        todo_items=[
            {
                "exp_id": "EXP-SEM-001",
                "todo_id": "todo-semantic-001",
                "slice_id": "ablation",
                "title": "Core ablation",
                "research_question": "RQ-semantic",
                "experimental_design": "Ablation-semantic",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "section_id": "analysis-semantic",
                "item_id": "AN-SEM-001",
                "claim_links": ["C-semantic"],
                "completion_condition": "Show whether the adapter is necessary.",
            }
        ],
        slices=[
            {
                "slice_id": "ablation",
                "title": "Core ablation",
                "goal": "Disable the adapter only.",
                "hypothesis": "The gain disappears without the adapter.",
                "required_changes": "Disable adapter only.",
                "metric_contract": "Keep the full validation protocol.",
                "section_id": "analysis-semantic",
                "item_id": "AN-SEM-001",
                "paper_role": "main_text",
                "claim_links": ["C-semantic"],
            }
        ],
    )
    artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the adapter only.",
        execution="Ran the full validation sweep.",
        results="The gain disappears when the adapter is removed.",
        metric_rows=[{"metric_id": "acc", "value": 0.81}],
        evidence_paths=["experiments/analysis/ablation/result.json"],
        evaluation_summary={
            "takeaway": "The ablation shows the adapter is necessary for the measured gain.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
        claim_impact=long_claim_impact,
    )
    bundle = artifact.submit_paper_bundle(
        quest_root,
        title="Semantic Paper",
        summary=long_bundle_summary,
        pdf_path="paper/paper.pdf",
    )

    qq_records = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    texts = [str(item.get("text") or "") for item in qq_records]
    idea_text = next(text for text in texts if "Semantic route" in text)
    main_text = next(text for text in texts if text.startswith("Main experiment `semantic-main-001`"))
    outline_text = next(text for text in texts if text.startswith("Paper outline `"))
    analysis_text = next(
        text
        for text in texts
        if text.startswith(f"Analysis campaign `{campaign['campaign_id']}` is complete.")
    )
    bundle_text = next(text for text in texts if text.startswith("Paper draft checkpoint `Semantic Paper`"))
    assert "Semantic route" in idea_text
    assert "Insert a compact residual adapter in the main path and keep the rest of the protocol fixed." in idea_text
    assert "The message should show the exact mechanism without collapsing it into an ellipsis." in idea_text
    assert ("下一步：Experiment" in idea_text) or ("Next step: Experiment" in idea_text)
    assert "…" not in idea_text

    assert "Outcome:\n- Metric: acc=0.87" in main_text
    assert "Evaluation summary:\n- Takeaway: The compact adapter improves the primary metric against the confirmed baseline under the full validation recipe." in main_text
    assert "This second paragraph must also survive delivery so the milestone preserves the real conclusion." in main_text
    assert "…" not in main_text

    assert "Paper outline" in outline_text
    assert "Research questions:\n- RQ-semantic" in outline_text
    assert "Experimental designs:\n- Ablation-semantic" in outline_text

    assert "Overview:\n- Completed slices: 1" in analysis_text
    assert "Completed slices:\n- `ablation`: Core ablation" in analysis_text
    assert "Claim impact: The ablation strengthens the central mechanism claim because the gain disappears when the adapter is removed." in analysis_text
    assert "This follow-up paragraph should remain visible in the connector milestone." in analysis_text
    assert "…" not in analysis_text

    assert bundle["interaction"]["status"] == "ok"
    assert "Summary:\nThe draft, manifest, and PDF reference are ready for final review on the paper branch." in bundle_text
    assert "This second paragraph should also be delivered in full" in bundle_text
    assert "Files:\n- Bundle manifest:" in bundle_text
    assert "- PDF: `paper/paper.pdf`" in bundle_text
    assert (
        "Next route:\nContinue writing/review unless manuscript coverage and submission readiness are both explicit;"
        in bundle_text
    )
    assert "…" not in bundle_text


def test_stage_view_branch_node_routes_to_experiment_and_analysis_content(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("branch node stage routing quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-stage-routing")

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Routing route",
        problem="Need the branch node to open real stage content.",
        hypothesis="The tab should show the durable experiment narrative.",
        mechanism="Route branch-node selections into stage-specific views.",
        decision_reason="Promote the route for canvas rendering.",
    )
    main_run = artifact.record_main_experiment(
        quest_root,
        run_id="routing-main-001",
        title="Routing main run",
        hypothesis="The routing fix should expose the actual experiment record.",
        setup="Standard validation recipe.",
        execution="Ran the main experiment once.",
        results="The main experiment record exists.",
        conclusion="Use the durable record directly in the stage tab.",
        metric_rows=[{"metric_id": "acc", "value": 0.86}],
        evaluation_summary={
            "takeaway": "The durable main experiment record exists and should render inline.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Routing analysis",
        campaign_goal="Ensure branch-node analysis selections open the campaign content.",
        slices=[
            {
                "slice_id": "ablation",
                "title": "Routing ablation",
                "goal": "Disable the new path and compare.",
                "hypothesis": "The gain disappears without the new path.",
                "required_changes": "One isolated ablation.",
                "metric_contract": "Keep the full evaluation protocol.",
            }
        ],
    )
    artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the new path only.",
        execution="Ran the campaign slice once.",
        results="The campaign slice produced a durable result.",
        metric_rows=[{"metric_id": "acc", "value": 0.82}],
        evaluation_summary={
            "takeaway": "The analysis slice now has durable inline content.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )

    experiment_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": main_run["branch"],
            "selection_type": "branch_node",
            "branch_name": main_run["branch"],
            "stage_key": "experiment",
        },
    )
    assert experiment_view["stage_key"] == "experiment"
    assert "The routing fix should expose the actual experiment record." in str(
        experiment_view["details"]["experiment"]["result_payload"]["hypothesis"]
    )
    assert "Use the durable record directly in the stage tab." in str(
        experiment_view["details"]["experiment"]["run_markdown"]
    )

    inferred_branch_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": main_run["branch"],
            "selection_type": "branch_node",
            "stage_key": "experiment",
        },
    )
    assert inferred_branch_view["details"]["experiment"]["result_payload"]["run_id"] == "routing-main-001"

    analysis_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": campaign["slices"][0]["branch"],
            "selection_type": "branch_node",
            "branch_name": campaign["slices"][0]["branch"],
            "stage_key": "analysis-campaign",
        },
    )
    assert analysis_view["stage_key"] == "analysis"
    assert "Ensure branch-node analysis selections open the campaign content." in str(
        analysis_view["details"]["analysis"]["goal"]
    )
    assert "The analysis slice now has durable inline content." in str(
        analysis_view["details"]["analysis"]["slices"][0]["evaluation_summary"]["takeaway"]
    )
    assert "Disable the new path only." in str(analysis_view["details"]["analysis"]["slices"][0]["result_markdown"])


def test_stage_view_general_stage_nodes_resolve_to_canonical_stage_content(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("general stage routing quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-general-routing")

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="General idea route",
        problem="Need the general stage node to stop falling into paper drafting.",
        hypothesis="Resolve stage nodes from the branch identity when the trace only says general.",
        mechanism="Infer the canonical stage from the branch namespace and durable artifacts.",
        decision_reason="General stage selections should still open the correct stage page.",
    )
    main_run = artifact.record_main_experiment(
        quest_root,
        run_id="general-main-001",
        title="General main run",
        hypothesis="The experiment stage should open the durable run payload.",
        setup="Standard comparable setup.",
        execution="Ran the main experiment once.",
        results="The main experiment payload is available.",
        conclusion="Keep the experiment page aligned with the recorded artifact.",
        metric_rows=[{"metric_id": "acc", "value": 0.84}],
    )
    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="General analysis",
        campaign_goal="Ensure general analysis stage nodes still open the campaign content.",
        slices=[
            {
                "slice_id": "ablation",
                "title": "General ablation",
                "goal": "Check the analysis branch routing.",
                "hypothesis": "The analysis stage stays available through general stage nodes.",
                "required_changes": "One ablation only.",
                "metric_contract": "Reuse the full evaluation protocol.",
            }
        ],
    )
    artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="ablation",
        setup="Disable the routed feature.",
        execution="Ran the analysis slice once.",
        results="The analysis slice artifact exists.",
        metric_rows=[{"metric_id": "acc", "value": 0.81}],
    )

    idea_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": f"stage:{idea['branch']}:general",
            "selection_type": "stage_node",
            "branch_name": idea["branch"],
            "stage_key": "general",
        },
    )
    assert idea_view["stage_key"] == "idea"
    assert idea_view["details"]["latest_artifact"]["payload"]["kind"] == "idea"
    assert "Need the general stage node" in str(idea_view["details"]["idea"]["problem"])

    experiment_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": f"stage:{main_run['branch']}:general",
            "selection_type": "stage_node",
            "branch_name": main_run["branch"],
            "stage_key": "general",
        },
    )
    assert experiment_view["stage_key"] == "experiment"
    assert experiment_view["details"]["latest_artifact"]["payload"]["run_kind"] == "main_experiment"
    assert "The experiment stage should open the durable run payload." in str(
        experiment_view["details"]["experiment"]["result_payload"]["hypothesis"]
    )

    analysis_branch = campaign["slices"][0]["branch"]
    analysis_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": f"stage:{analysis_branch}:general",
            "selection_type": "stage_node",
            "branch_name": analysis_branch,
            "stage_key": "general",
        },
    )
    assert analysis_view["stage_key"] == "analysis"
    assert analysis_view["details"]["latest_artifact"]["payload"]["flow_type"] in {"analysis_campaign", "analysis_slice"}
    assert "Ensure general analysis stage nodes" in str(analysis_view["details"]["analysis"]["goal"])


def test_supplementary_experiment_protocol_supports_runtime_ref_queries_and_unified_fields(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("supplementary protocol quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-supplementary")
    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Runtime-ref idea",
        problem="Need a unified route for all extra experiments.",
        hypothesis="A single campaign protocol reduces ambiguity.",
        mechanism="Use one campaign surface for all supplementary work.",
        decision_reason="Promote the unified protocol route.",
        next_target="experiment",
    )
    main_run = artifact.record_main_experiment(
        quest_root,
        run_id="main-supp-001",
        title="Unified protocol main run",
        hypothesis="The unified protocol is workable.",
        setup="Use the accepted baseline setup.",
        execution="Completed the main run.",
        results="Main result is ready for extra evidence work.",
        conclusion="Needs one follow-up reviewer-linked run.",
        metric_rows=[{"metric_id": "acc", "value": 0.91}],
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Supplementary Outline",
        detailed_outline={
            "title": "Supplementary Outline",
            "research_questions": ["RQ-supp"],
            "experimental_designs": ["Exp-supp"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Bind the next supplementary run to the selected outline.",
    )

    refs = artifact.resolve_runtime_refs(quest_root)
    assert refs["active_idea_id"] == idea["idea_id"]
    assert refs["latest_main_run_id"] == "main-supp-001"
    assert refs["selected_outline_ref"] == "outline-001"

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Reviewer-linked supplementary run",
        campaign_goal="Answer the remaining reviewer concern with one clean slice.",
        campaign_origin={
            "kind": "rebuttal",
            "reason": "Reviewer requested one additional controlled comparison.",
            "reviewer_item_ids": ["R1-C1"],
        },
        selected_outline_ref="outline-001",
        research_questions=["RQ-supp"],
        experimental_designs=["Exp-supp"],
        todo_items=[
            {
                "exp_id": "EXP-R1-C1",
                "todo_id": "todo-r1-c1",
                "slice_id": "reviewer-check",
                "title": "Reviewer check",
                "research_question": "RQ-supp",
                "experimental_design": "Exp-supp",
                "tier": "main_required",
                "paper_placement": "main_text",
                "paper_role": "main_text",
                "section_id": "reviewer-response",
                "item_id": "AN-R1-C1",
                "claim_links": ["C-review"],
                "completion_condition": "Answer whether the claim survives the requested check.",
                "why_now": "This is the only remaining blocker before revision.",
                "success_criteria": "Produce a fair comparison and a usable manuscript update.",
                "abandonment_criteria": "Stop only if the metric contract becomes invalid.",
                "reviewer_item_ids": ["R1-C1"],
                "manuscript_targets": ["Results", "Rebuttal response"],
            }
        ],
        slices=[
            {
                "slice_id": "reviewer-check",
                "title": "Reviewer-linked check",
                "goal": "Run the requested controlled comparison.",
                "why_now": "Needed for the current revision package.",
                "required_changes": "Modify only the requested comparison factor.",
                "success_criteria": "Return a clean comparable result.",
                "abandonment_criteria": "Abort if the comparison breaks the metric contract.",
                "reviewer_item_ids": ["R1-C1"],
                "manuscript_targets": ["Results", "Response letter"],
                "section_id": "reviewer-response",
                "item_id": "AN-R1-C1",
                "paper_role": "main_text",
                "claim_links": ["C-review"],
            }
        ],
    )
    active_campaign = artifact.get_analysis_campaign(quest_root, campaign_id="active")
    assert active_campaign["campaign_id"] == campaign["campaign_id"]
    assert active_campaign["campaign_origin"]["kind"] == "rebuttal"
    assert active_campaign["todo_items"][0]["reviewer_item_ids"] == ["R1-C1"]
    assert active_campaign["next_pending_slice_id"] == "reviewer-check"

    outlines = artifact.list_paper_outlines(quest_root)
    assert outlines["selected_outline_ref"] == "outline-001"
    assert any(item["outline_id"] == "outline-001" for item in outlines["outlines"])

    completed = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="reviewer-check",
        setup="Keep the baseline contract fixed.",
        execution="Ran the requested controlled comparison.",
        results="The claim remains supported under the requested check.",
        metric_rows=[{"metric_id": "acc", "value": 0.905}],
        claim_impact="Strengthens confidence in the main claim.",
        reviewer_resolution="Addresses reviewer item R1-C1 directly.",
        manuscript_update_hint="Update the rebuttal response and the main results paragraph.",
        next_recommendation="Return to the parent branch and revise the manuscript.",
        evaluation_summary={
            "takeaway": "The reviewer-linked check supports the original claim.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "write",
        },
    )
    assert completed["ok"] is True
    evidence_ledger = read_json(quest_root / "paper" / "evidence_ledger.json", {})
    ledger_item = next(item for item in evidence_ledger["items"] if item["item_id"] == "AN-R1-C1")
    assert ledger_item["section_id"] == "reviewer-response"
    selected_outline = read_json(quest_root / "paper" / "selected_outline.json", {})
    reviewer_section = next(item for item in selected_outline["sections"] if item["section_id"] == "reviewer-response")
    assert reviewer_section["status"] == "ready"
    assert reviewer_section["result_table"][0]["item_id"] == "AN-R1-C1"
    experiment_matrix_json = read_json(quest_root / "paper" / "paper_experiment_matrix.json", {})
    matrix_item_ids = {str(row.get("item_id") or "").strip() for row in experiment_matrix_json.get("rows") or []}
    assert "AN-R1-C1" in matrix_item_ids
    assert "main-supp-001" in matrix_item_ids
    assert Path(quest_root / "paper" / "paper_experiment_matrix.md").exists()
    paper_contract = artifact.get_paper_contract(quest_root)
    assert paper_contract["ok"] is True
    assert paper_contract["detail"] == "full"
    bundle = paper_contract["paper_contract_bundle"]
    assert bundle["paper_contract"]["selected_outline_ref"] == "outline-001"
    contract_item_ids = {
        str(row.get("item_id") or "").strip()
        for row in (bundle["paper_experiment_matrix"].get("rows") or [])
        if isinstance(row, dict)
    }
    assert "AN-R1-C1" in contract_item_ids
    assert "main-supp-001" in contract_item_ids
    result_text = Path(completed["result_path"]).read_text(encoding="utf-8")
    assert "## Claim Impact" in result_text
    assert "Strengthens confidence in the main claim." in result_text
    manifest_after = artifact.get_analysis_campaign(quest_root, campaign_id=campaign["campaign_id"])
    assert manifest_after["slices"][0]["claim_impact"] == "Strengthens confidence in the main claim."
    assert main_run["run_id"] == "main-supp-001"
    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": f"stage:{idea['branch']}:analysis-campaign",
            "selection_type": "stage_node",
            "branch_name": idea["branch"],
            "stage_key": "analysis-campaign",
        },
    )
    analysis_details = stage_view["details"]["analysis"]
    assert analysis_details["campaign_origin"]["kind"] == "rebuttal"
    assert analysis_details["todo_items"][0]["success_criteria"] == "Produce a fair comparison and a usable manuscript update."
    assert analysis_details["slices"][0]["claim_impact"] == "Strengthens confidence in the main claim."
    assert analysis_details["slices"][0]["evaluation_summary"]["claim_update"] == "strengthens"
    app = DaemonApp(temp_home)
    branches = app.handlers.git_branches(quest["quest_id"])
    by_ref = {item["ref"]: item for item in branches["nodes"]}
    paper_branch = str(completed["research_state"]["current_workspace_branch"] or "").strip()
    assert completed["research_state"]["workspace_mode"] == "paper"
    assert by_ref[paper_branch]["workflow_state"]["writing_state"] == "active"
    assert by_ref[paper_branch]["workflow_state"]["status_reason"] == "Writing workspace active."
    assert by_ref[manifest_after["parent_branch"]]["workflow_state"]["writing_state"] == "ready"


def test_submit_paper_bundle_writes_draft_checkpoint_without_finalize(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper bundle quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Bundle Outline",
        note="Candidate for bundle test.",
        detailed_outline={
            "title": "Bundle Outline",
            "research_questions": ["RQ-bundle"],
            "experimental_designs": ["Exp-bundle"],
            "contributions": ["C-bundle"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for bundle generation.",
    )
    paper_workspace = quest_service.active_workspace_root(quest_root)
    paper_root = paper_workspace / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "draft.md").write_text("# Draft\n", encoding="utf-8")
    (paper_root / "writing_plan.md").write_text("# Plan\n", encoding="utf-8")
    (paper_root / "references.bib").write_text("@article{demo, title={Demo}}\n", encoding="utf-8")
    (paper_root / "build").mkdir(parents=True, exist_ok=True)
    write_json(paper_root / "build" / "compile_report.json", {"ok": True})
    (paper_root / "paper.pdf").write_bytes(b"%PDF-1.4\n%paper\n")

    result = artifact.submit_paper_bundle(
        quest_root,
        title="Bundle Paper",
        summary="Paper bundle is ready for final review.",
        pdf_path="paper/paper.pdf",
    )
    assert result["ok"] is True
    assert result["interaction"]["status"] == "ok"
    assert Path(result["manifest_path"]).exists()
    assert Path(result["baseline_inventory_path"]).exists()
    assert Path(result["evidence_ledger_path"]).exists()
    assert Path(result["paper_line_state_path"]).exists()
    assert result["open_source_manifest_path"] is None
    bundle_delta = _assert_artifact_delta(
        result["artifact_delta"],
        delta_kind="draft_checkpoint",
        expected_labels={
            "paper_bundle_manifest_json",
            "baseline_inventory_json",
            "evidence_ledger_json",
            "paper_line_state_json",
            "manuscript_coverage_json",
            "artifact_json",
        },
    )
    assert bundle_delta["metadata"]["package_type"] == "draft_checkpoint"
    baseline_inventory = read_json(Path(result["baseline_inventory_path"]), {})
    assert baseline_inventory["schema_version"] == 1
    manifest = read_json(Path(result["manifest_path"]), {})
    assert manifest["package_type"] == "draft_checkpoint"
    assert manifest["prepare_open_source"] is False
    assert manifest["open_source_manifest_path"] is None
    assert manifest["open_source_cleanup_plan_path"] is None
    snapshot = quest_service.snapshot(quest["quest_id"])
    assert snapshot["active_anchor"] == "write"
    assert snapshot["continuation_policy"] == "wait_for_user_or_resume"
    assert snapshot["continuation_anchor"] == "decision"
    assert snapshot["continuation_reason"] == "paper_draft_checkpoint_submitted"
    assert snapshot["paper_contract_health"]["closure_state"] == "draft_checkpoint_continue_writing"
    assert snapshot["paper_contract_health"]["delivery_state"] == "draft_checkpoint_ready"
    assert snapshot["paper_contract_health"]["draft_checkpoint_ready"] is True
    assert snapshot["paper_contract_health"]["finalize_ready"] is False
    assert snapshot["paper_contract_health"]["submission_ready"] is False
    assert Path(result["manuscript_coverage_path"]).exists()
    assert snapshot["paper_evidence"]["item_count"] == 0
    assert snapshot["paper_lines"][0]["paper_line_id"] == result["paper_line_state"]["paper_line_id"]

    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": "stage:main:write",
            "selection_type": "stage_node",
            "branch_name": "main",
            "stage_key": "write",
        },
    )
    assert stage_view["stage_key"] == "paper"
    assert any(item["label"] == "Bundle Manifest" for item in stage_view["sections"]["key_files"])


def test_validate_manuscript_coverage_blocks_short_memo_as_full_paper(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper coverage quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Coverage Outline",
        detailed_outline={
            "title": "Coverage Outline",
            "research_questions": ["RQ-coverage"],
            "experimental_designs": ["Exp-coverage"],
            "contributions": ["C-coverage"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for coverage validation.",
    )
    paper_root = quest_service.active_workspace_root(quest_root) / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "draft.md").write_text("# Short Memo\n\nOne paragraph.\n", encoding="utf-8")

    coverage_result = artifact.validate_manuscript_coverage(quest_root, detail="full")
    coverage = coverage_result["manuscript_coverage"]

    assert coverage["draft_checkpoint_ready"] is True
    assert coverage["manuscript_ready"] is False
    assert coverage["submission_ready"] is False
    assert coverage["one_section_only"] is True
    assert any("fewer than 5 section" in item for item in coverage["manuscript_blockers"])


def test_validate_academic_outline_surfaces_quality_reminders_without_blocking(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper outline reminder quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Reminder Outline",
        detailed_outline={
            "paper_view": {
                "paper_type": "full_empirical",
                "outline_maturity": "mature",
                "working_title": "Reminder Outline",
                "narrative_strategy": {
                    "central_thesis": "The method improves the target setting under a controlled comparison.",
                },
                "story_spine": {
                    "problem": "The target setting needs a more reliable comparison protocol.",
                    "gap": "Existing runs do not isolate the relevant support signal.",
                    "method": "The method adds a controlled support pass.",
                    "main_result": "The measured main result improves over the accepted baseline.",
                    "scope_limit": "The claim is limited to this benchmark and evidence budget.",
                },
                "core_claims": [
                    {
                        "claim_id": "C1",
                        "claim": "The controlled support pass improves the target metric.",
                        "scope": "Accepted baseline and target benchmark only.",
                        "evidence_needed": ["main-result"],
                        "what_would_falsify_it": "No gain under the same comparison budget.",
                    }
                ],
                "method_abstraction": {
                    "intuition": "A separate support pass reduces unsupported updates.",
                    "mechanism_steps": ["collect support", "score candidates", "update only supported decisions"],
                },
                "evaluation_plan": {
                    "setting": "Accepted benchmark protocol.",
                    "datasets_or_benchmarks": ["TargetBench"],
                    "baselines": ["accepted-baseline"],
                    "metrics": ["score"],
                },
                "analysis_plan": [
                    {
                        "analysis_id": "A1",
                        "title": "Single ablation",
                        "analysis_role": "component ablation",
                        "reviewer_question": "Does the support pass matter?",
                        "claim_links": ["C1"],
                        "target_display": "Ablation table",
                        "main_or_appendix": "main_text",
                    }
                ],
                "evidence_grounding": {
                    "observed_facts": ["main-result improved the target metric"],
                    "allowed_interpretations": ["the support pass may be useful in this setting"],
                    "must_not_claim": ["general improvement across unrelated benchmarks"],
                },
            }
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for outline reminder validation.",
    )

    result = artifact.validate_academic_outline(quest_root, detail="full")
    validation = result["academic_outline_validation"]

    assert result["ok"] is True
    assert validation["analysis_plan_ready"] is True
    assert validation["analysis_count"] == 1
    assert any("central_insight" in item for item in validation["warnings"])
    assert any("fewer than 4" in item for item in validation["warnings"])
    assert any("reviewer_objections" in item for item in validation["warnings"])


def test_paper_experiment_matrix_preserves_same_item_analysis_rows(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper matrix duplicate quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Matrix Outline",
        detailed_outline={
            "title": "Matrix Outline",
            "sections": [
                {
                    "section_id": "analysis",
                    "title": "Analysis",
                    "paper_role": "main_text",
                    "required_items": ["shared-item"],
                    "result_table": [
                        {
                            "item_id": "shared-item",
                            "kind": "analysis_slice",
                            "campaign_id": "analysis-a",
                            "slice_id": "robustness",
                            "status": "completed",
                            "result_summary": "Robustness check passed.",
                        },
                        {
                            "item_id": "shared-item",
                            "kind": "analysis_slice",
                            "campaign_id": "analysis-b",
                            "slice_id": "failure",
                            "status": "completed",
                            "result_summary": "Failure modes identified.",
                        },
                    ],
                }
            ],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for matrix validation.",
    )

    matrix = read_json(quest_service.active_workspace_root(quest_root) / "paper" / "paper_experiment_matrix.json", {})
    shared_rows = [row for row in matrix["rows"] if row["item_id"] == "shared-item"]
    assert len(shared_rows) == 2
    assert {row["slice_id"] for row in shared_rows} == {"robustness", "failure"}


def test_submit_paper_bundle_can_prepare_open_source_when_enabled(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper bundle open source quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Bundle Outline",
        detailed_outline={
            "title": "Bundle Outline",
            "research_questions": ["RQ-bundle"],
            "experimental_designs": ["Exp-bundle"],
            "contributions": ["C-bundle"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for bundle generation.",
    )
    paper_workspace = quest_service.active_workspace_root(quest_root)
    paper_root = paper_workspace / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "draft.md").write_text("# Draft\n", encoding="utf-8")
    (paper_root / "writing_plan.md").write_text("# Plan\n", encoding="utf-8")
    (paper_root / "references.bib").write_text("@article{demo, title={Demo}}\n", encoding="utf-8")
    (paper_root / "build").mkdir(parents=True, exist_ok=True)
    write_json(paper_root / "build" / "compile_report.json", {"ok": True})
    (paper_root / "paper.pdf").write_bytes(b"%PDF-1.4\n%paper\n")

    result = artifact.submit_paper_bundle(
        quest_root,
        title="Bundle Paper",
        summary="Paper bundle is ready for final review.",
        pdf_path="paper/paper.pdf",
        prepare_open_source=True,
    )

    assert result["ok"] is True
    assert result["open_source_manifest_path"] is not None
    assert Path(result["open_source_manifest_path"]).exists()
    manifest = read_json(Path(result["manifest_path"]), {})
    assert manifest["prepare_open_source"] is True
    expected_bundle_rel = Path(result["manifest_path"]).relative_to(quest_root).as_posix()
    open_source_manifest = read_json(Path(result["open_source_manifest_path"]), {})
    assert open_source_manifest["source_bundle_manifest_path"] == expected_bundle_rel


def test_submit_paper_bundle_blocks_unmapped_completed_analysis(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper bundle gate quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Gate Outline",
        detailed_outline={
            "title": "Gate Outline",
            "research_questions": ["RQ-gate"],
            "experimental_designs": ["Exp-gate"],
            "sections": [
                {
                    "section_id": "results-gate",
                    "title": "Gate Results",
                    "paper_role": "main_text",
                    "claims": ["C1"],
                    "required_items": [],
                    "optional_items": [],
                }
            ],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use the gate outline for bundle validation.",
    )
    paper_workspace = quest_service.active_workspace_root(quest_root)
    paper_root = paper_workspace / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)
    (paper_root / "draft.md").write_text("# Draft\n", encoding="utf-8")
    (paper_root / "writing_plan.md").write_text("# Plan\n", encoding="utf-8")
    (paper_root / "references.bib").write_text("@article{demo, title={Demo}}\n", encoding="utf-8")
    (paper_root / "build").mkdir(parents=True, exist_ok=True)
    write_json(paper_root / "build" / "compile_report.json", {"ok": True})
    (paper_root / "paper.pdf").write_bytes(b"%PDF-1.4\n%paper\n")

    write_json(
        quest_root / ".ds" / "analysis_campaigns" / "analysis-gate.json",
        {
            "campaign_id": "analysis-gate",
            "selected_outline_ref": "outline-001",
            "slices": [
                {
                    "slice_id": "ablation",
                    "title": "Gate ablation",
                    "status": "completed",
                }
            ],
        },
    )

    with pytest.raises(ValueError) as exc_info:
        artifact.submit_paper_bundle(
            quest_root,
            title="Blocked Paper",
            summary="This bundle should be blocked by unmapped analysis.",
            pdf_path="paper/paper.pdf",
        )

    assert "unmapped" in str(exc_info.value)


def test_submit_paper_bundle_normalizes_latex_root_from_main_tex_path(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper bundle latex root quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.submit_paper_outline(
        quest_root,
        mode="candidate",
        title="Bundle Outline",
        note="Candidate for latex bundle normalization.",
        detailed_outline={
            "title": "Bundle Outline",
            "research_questions": ["RQ-latex"],
            "experimental_designs": ["Exp-latex"],
            "contributions": ["C-latex"],
        },
    )
    artifact.submit_paper_outline(
        quest_root,
        mode="select",
        outline_id="outline-001",
        selected_reason="Use this for latex root normalization.",
    )
    paper_workspace = quest_service.active_workspace_root(quest_root)
    paper_root = paper_workspace / "paper"
    latex_root = paper_root / "latex"
    latex_root.mkdir(parents=True, exist_ok=True)
    main_tex = latex_root / "main.tex"
    main_tex.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\begin{document}",
                "Bundle",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (paper_root / "draft.md").write_text("# Draft\n", encoding="utf-8")
    (paper_root / "writing_plan.md").write_text("# Plan\n", encoding="utf-8")
    (paper_root / "references.bib").write_text("@article{demo, title={Demo}}\n", encoding="utf-8")
    (paper_root / "build").mkdir(parents=True, exist_ok=True)
    write_json(
        paper_root / "build" / "compile_report.json",
        {
            "ok": True,
            "main_file_path": "paper/latex/main.tex",
        },
    )

    result = artifact.submit_paper_bundle(
        quest_root,
        title="Bundle Paper",
        summary="Paper bundle keeps latex roots normalized.",
        latex_root_path="paper/latex/main.tex",
    )
    manifest = read_json(Path(result["manifest_path"]), {})
    assert manifest["latex_root_path"] == "paper/latex"

    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": "stage:main:write",
            "selection_type": "stage_node",
            "branch_name": "main",
            "stage_key": "write",
        },
    )
    assert stage_view["details"]["paper"]["build"]["latex_root_path"] == "paper/latex"
    assert stage_view["details"]["paper"]["build"]["main_tex_path"] == "paper/latex/main.tex"
    latex_sources = next(
        item for item in stage_view["sections"]["key_files"] if item["label"] == "LaTeX Sources"
    )
    assert latex_sources["kind"] == "directory"
    assert latex_sources["path"] == "paper/latex"


def test_record_main_experiment_writes_result_and_baseline_comparison(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("main experiment result quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-main"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Main baseline\n", encoding="utf-8")

    artifact.record(
        quest_root,
        {
            "kind": "baseline",
            "publish_global": True,
            "baseline_id": "baseline-main",
            "name": "Main baseline",
            "primary_metric": {"name": "acc", "value": 0.84},
            "metrics_summary": {"acc": 0.84, "f1": 0.8},
            "baseline_variants": [
                {"variant_id": "main", "label": "Main", "metrics_summary": {"acc": 0.84, "f1": 0.8}}
            ],
            "default_variant_id": "main",
        },
    )
    artifact.attach_baseline(quest_root, "baseline-main", "main")
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/imported/baseline-main",
        baseline_id="baseline-main",
        variant_id="main",
        summary="Baseline main confirmed",
    )

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates.",
        hypothesis="A small adapter improves the main score.",
        mechanism="Insert a light residual adapter.",
        decision_reason="Best next route.",
        next_target="experiment",
    )
    worktree_root = Path(idea["worktree_root"])
    (worktree_root / "src").mkdir(exist_ok=True)
    (worktree_root / "src" / "model.py").write_text("print('adapter')\n", encoding="utf-8")

    result = artifact.record_main_experiment(
        quest_root,
        run_id="main-001",
        title="Adapter main run",
        hypothesis="Adapter improves validation accuracy.",
        setup="Use the attached baseline training recipe.",
        execution="Ran the full validation sweep.",
        results="Accuracy improved.",
        conclusion="The adapter is promising enough for follow-up analysis.",
        metric_rows=[
            {"metric_id": "acc", "value": 0.89, "split": "val"},
            {"metric_id": "f1", "value": 0.85, "split": "val"},
        ],
        evidence_paths=["outputs/main-001/metrics.json"],
        config_paths=["configs/adapter.yaml"],
        evaluation_summary={
            "takeaway": "The adapter clears the baseline on the main validation metric.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    assert result["ok"] is True
    assert result["guidance"]
    assert result["recommended_skill_reads"] == ["decision"]
    assert result["suggested_artifact_calls"]
    assert result["next_instruction"]
    run_md = Path(result["run_md_path"])
    result_json = Path(result["result_json_path"])
    assert run_md.exists()
    assert result_json.exists()

    payload = read_json(result_json, {})
    assert payload["result_kind"] == "main_experiment"
    assert payload["baseline_ref"]["baseline_id"] == "baseline-main"
    assert payload["baseline_ref"]["metric_contract_json_rel_path"] == "baselines/imported/baseline-main/json/metric_contract.json"
    assert payload["metrics_summary"]["acc"] == 0.89
    assert payload["baseline_comparisons"]["primary_metric_id"] == "acc"
    assert payload["evaluation_summary"]["claim_update"] == "strengthens"
    primary = next(item for item in payload["baseline_comparisons"]["items"] if item["metric_id"] == "acc")
    assert primary["delta"] == pytest.approx(0.05)
    assert payload["progress_eval"]["breakthrough"] is True
    assert payload["progress_eval"]["breakthrough_level"] in {"minor", "major"}
    assert result["evaluation_summary"]["next_action"] == "analysis_campaign"

    snapshot = quest_service.snapshot(quest["quest_id"])
    assert snapshot["summary"]["latest_metric"]["key"] == "acc"
    assert snapshot["summary"]["latest_metric"]["delta_vs_baseline"] == pytest.approx(0.05)
    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": "stage:run/main-001:experiment",
            "selection_type": "stage_node",
            "branch_name": "run/main-001",
            "stage_key": "experiment",
        },
    )
    assert stage_view["details"]["experiment"]["evaluation_summary"]["baseline_relation"] == "better"


def test_record_main_experiment_prefers_metric_rows_for_nested_metric_summaries(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("nested metric summary quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    baseline_root = quest_root / "baselines" / "local" / "baseline-nested"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Nested baseline\n", encoding="utf-8")

    artifact.record(
        quest_root,
        {
            "kind": "baseline",
            "publish_global": True,
            "baseline_id": "baseline-nested",
            "name": "Nested baseline",
            "primary_metric": {"name": "sigma_max", "value": 0.6921},
            "metrics_summary": {"sigma_max": 0.6921, "raw_false": 0.2149},
            "baseline_variants": [
                {
                    "variant_id": "main",
                    "label": "Main",
                    "metrics_summary": {"sigma_max": 0.6921, "raw_false": 0.2149},
                }
            ],
            "default_variant_id": "main",
            "metric_contract": {
                "primary_metric_id": "sigma_max",
                "metrics": [
                    {"metric_id": "sigma_max", "direction": "lower"},
                    {"metric_id": "raw_false", "direction": "lower"},
                ],
            },
        },
    )
    artifact.attach_baseline(quest_root, "baseline-nested", "main")
    artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/imported/baseline-nested",
        baseline_id="baseline-nested",
        variant_id="main",
        summary="Baseline nested confirmed",
    )

    artifact.submit_idea(
        quest_root,
        mode="create",
        title="Ledger route",
        problem="Need a more robust guidance controller.",
        hypothesis="Ledgering reduces maximal reality shift.",
        mechanism="Carry structured correction state across steps.",
        decision_reason="Best follow-up route.",
        next_target="experiment",
    )

    result = artifact.record_main_experiment(
        quest_root,
        run_id="nested-001",
        title="Nested metric run",
        hypothesis="Ledgering improves the lower-is-better metrics.",
        setup="Three-task pooled evaluation.",
        execution="Ran the pooled comparison sweep.",
        results="The pooled result is favorable overall.",
        conclusion="Promising enough for analysis.",
        metrics_summary={
            "headline": "Full pooled comparison is favorable.",
            "primary_metric": {"metric_id": "sigma_max", "value": 0.2477},
            "supporting_metrics": {"raw_false": {"value": 0.2063}},
            "per_task_read": {"sports_understanding": "favorable"},
        },
        metric_rows=[
            {"metric_id": "sigma_max", "value": 0.2477, "delta": -0.4444, "direction": "lower_better"},
            {"metric_id": "raw_false", "value": 0.2063, "delta": -0.0086, "direction": "lower_better"},
        ],
        evaluation_summary={
            "takeaway": "The pooled run beats the baseline on the key lower-is-better metrics.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    payload = read_json(Path(result["result_json_path"]), {})
    comparison_ids = {item["metric_id"] for item in payload["baseline_comparisons"]["items"]}
    assert comparison_ids == {"sigma_max", "raw_false"}
    assert payload["baseline_comparisons"]["primary_metric_id"] == "sigma_max"
    assert payload["progress_eval"]["direction"] == "minimize"
    assert payload["progress_eval"]["delta_vs_baseline"] == pytest.approx(-0.4444)

    snapshot = quest_service.snapshot(quest["quest_id"])
    assert snapshot["summary"]["latest_metric"]["key"] == "sigma_max"
    assert snapshot["summary"]["latest_metric"]["value"] == pytest.approx(0.2477)
    assert snapshot["summary"]["latest_metric"]["delta_vs_baseline"] == pytest.approx(-0.4444)

    timeline = quest_service.metrics_timeline(quest["quest_id"])
    series_by_id = {item["metric_id"]: item for item in timeline["series"]}
    assert set(series_by_id.keys()) == {"sigma_max", "raw_false"}
    assert series_by_id["sigma_max"]["points"][0]["value"] == pytest.approx(0.2477)
    assert series_by_id["raw_false"]["points"][0]["value"] == pytest.approx(0.2063)


def test_submit_idea_supports_foundation_selection_and_branch_listing(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("idea foundation quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-foundation")

    first_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Adapter route",
        problem="Baseline saturates on difficult cases.",
        hypothesis="A small adapter improves the main score.",
        mechanism="Insert a light residual adapter.",
        decision_reason="Best next route from the current head.",
        next_target="experiment",
    )
    assert first_idea["branch_no"] == "001"
    first_metadata, _ = load_markdown_document(Path(first_idea["idea_md_path"]))
    assert first_metadata["foundation_ref"]["kind"] == "current_head"
    assert first_metadata["foundation_ref"]["branch"] == first_idea["parent_branch"]

    revised_first_idea = artifact.submit_idea(
        quest_root,
        mode="revise",
        idea_id=first_idea["idea_id"],
        title="Adapter route refined",
        problem="Baseline still misses difficult cases.",
        hypothesis="A tuned adapter improves the main score.",
        mechanism="Tune adapter placement and depth.",
        decision_reason="Refine the same branch before the main run.",
        next_target="experiment",
    )
    assert revised_first_idea["branch"] == first_idea["branch"]

    artifact.record_main_experiment(
        quest_root,
        run_id="main-001",
        title="Adapter main run",
        hypothesis="Adapter improves validation accuracy.",
        setup="Use the attached baseline training recipe.",
        execution="Ran the full validation sweep.",
        results="Accuracy improved.",
        conclusion="The adapter is promising enough for follow-up analysis.",
        metric_rows=[
            {"metric_id": "acc", "value": 0.88, "split": "val"},
        ],
        evidence_paths=["outputs/main-001/metrics.json"],
    )

    second_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Run-informed route",
        problem="Need a follow-up idea grounded in the measured win.",
        hypothesis="The measured gain suggests a stronger route.",
        mechanism="Extend the winning adapter logic into the next branch.",
        decision_reason="Use the best measured branch as the next foundation.",
        foundation_ref={"kind": "run", "ref": "main-001"},
        foundation_reason="Build on the best measured main run.",
        next_target="experiment",
    )
    assert second_idea["branch_no"] == "002"
    second_metadata, _ = load_markdown_document(Path(second_idea["idea_md_path"]))
    assert second_metadata["foundation_ref"]["kind"] == "run"
    assert second_metadata["foundation_ref"]["ref"] == "main-001"
    assert second_metadata["foundation_ref"]["branch"] == "run/main-001"
    assert second_metadata["foundation_reason"] == "Build on the best measured main run."

    third_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Baseline reset route",
        problem="Need a clean restart from the confirmed baseline.",
        hypothesis="A fresh line from baseline may unlock a cleaner improvement.",
        mechanism="Restart from the baseline branch with a different modification point.",
        decision_reason="Try a fresh route from the baseline instead of compounding changes.",
        foundation_ref={"kind": "baseline", "ref": "baseline-foundation"},
        foundation_reason="Restart from the confirmed baseline branch.",
        next_target="experiment",
    )
    assert third_idea["branch_no"] == "003"
    third_metadata, _ = load_markdown_document(Path(third_idea["idea_md_path"]))
    assert third_metadata["foundation_ref"]["kind"] == "baseline"
    assert third_metadata["foundation_ref"]["ref"] == "baseline-foundation"
    assert third_metadata["foundation_reason"] == "Restart from the confirmed baseline branch."

    branches = artifact.list_research_branches(quest_root)
    assert branches["ok"] is True
    assert branches["count"] == 4
    assert branches["active_head_branch"] == third_idea["branch"]

    by_branch = {item["branch_name"]: item for item in branches["branches"]}
    first_branch = by_branch[first_idea["branch"]]
    assert first_branch["branch_no"] == "001"
    assert first_branch["idea_title"] == "Adapter route refined"
    assert first_branch["parent_branch"] == "main"
    assert first_branch["foundation_ref"]["kind"] == "current_head"
    assert first_branch["latest_main_experiment"] is None
    assert first_branch["experiment_count"] == 0
    assert first_branch["has_main_result"] is False
    assert first_branch["round_state"] == "pre_result"

    run_branch = by_branch["run/main-001"]
    assert run_branch["parent_branch"] == first_idea["branch"]
    assert run_branch["latest_main_experiment"]["run_id"] == "main-001"
    assert run_branch["latest_main_experiment"]["primary_metric_id"] == "acc"
    assert run_branch["latest_main_experiment"]["primary_value"] == pytest.approx(0.88)
    assert run_branch["experiment_count"] == 1
    assert [item["run_id"] for item in run_branch["experiments"]] == ["main-001"]
    assert run_branch["has_main_result"] is True
    assert run_branch["round_state"] == "post_result"

    second_branch = by_branch[second_idea["branch"]]
    assert second_branch["branch_no"] == "002"
    assert second_branch["idea_title"] == "Run-informed route"
    assert second_branch["parent_branch"] == "run/main-001"
    assert second_branch["foundation_ref"]["kind"] == "run"
    assert second_branch["foundation_ref"]["ref"] == "main-001"
    assert second_branch["foundation_reason"] == "Build on the best measured main run."
    assert second_branch["latest_main_experiment"] is None
    assert second_branch["has_main_result"] is False
    assert second_branch["round_state"] == "pre_result"

    third_branch = by_branch[third_idea["branch"]]
    assert third_branch["branch_no"] == "003"
    assert third_branch["idea_title"] == "Baseline reset route"
    assert third_branch["parent_branch"] == "main"
    assert third_branch["foundation_ref"]["kind"] == "baseline"
    assert third_branch["foundation_ref"]["ref"] == "baseline-foundation"
    assert third_branch["foundation_reason"] == "Restart from the confirmed baseline branch."
    assert branches["branches"][0]["branch_name"] == third_idea["branch"]

    artifact_listing = quest_service.artifacts(quest["quest_id"])
    mirrored_main_runs = [
        item
        for item in artifact_listing["items"]
        if str((item.get("kind") or "")) == "runs"
        and str(((item.get("payload") or {}).get("run_id")) or "") == "main-001"
    ]
    assert len(mirrored_main_runs) == 1

    branch_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": second_idea["branch"],
            "selection_type": "branch_node",
            "branch_name": second_idea["branch"],
            "stage_key": "idea",
            "compare_base": first_idea["branch"],
            "compare_head": second_idea["branch"],
        },
    )
    assert branch_view["branch_no"] == "002"
    assert branch_view["title"] == "Branch #002 · Run-informed route"
    assert branch_view["foundation_label"] == "run · main-001"
    assert branch_view["parent_branch"] == "run/main-001"
    assert branch_view["compare_base"] == first_idea["branch"]
    assert branch_view["compare_head"] == second_idea["branch"]
    assert branch_view["lineage_intent"] == "continue_line"
    assert branch_view["draft_available"] is True
    assert branch_view["idea_draft_path"].endswith("/draft.md")
    assert "draft" in branch_view["subviews"]
    assert any(item["label"] == "Idea Markdown" for item in branch_view["sections"]["key_files"])
    assert any(item["label"] == "Idea Draft" for item in branch_view["sections"]["key_files"])


def test_collect_artifacts_uses_projection_when_fresh(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    artifact = ArtifactService(temp_home)
    quest = quest_service.create("artifact projection cache quest")
    quest_root = Path(quest["quest_root"])

    artifact.record(
        quest_root,
        {
            "kind": "milestone",
            "summary": "Projection-ready artifact.",
            "message": "Projection-ready artifact.",
        },
        checkpoint=False,
    )

    first = quest_service._collect_artifacts(quest_root)
    projection_path = quest_service._artifact_projection_path(quest_root)
    projection = read_json(projection_path, {})
    assert projection["schema_version"] == 2
    assert projection["state_kind"] in {"index", "raw"}
    assert any(str((item.get("payload") or {}).get("kind") or "") == "milestone" for item in first)

    def _fail_raw(_quest_root: Path) -> list[dict[str, Any]]:
        raise AssertionError("raw artifact scan should not run when the projection is fresh")

    monkeypatch.setattr(quest_service, "_collect_artifacts_raw", _fail_raw)

    second = quest_service._collect_artifacts(quest_root)
    assert [item.get("path") for item in second] == [item.get("path") for item in first]


def test_collect_artifacts_auto_backfills_legacy_quest_without_index(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("legacy artifact backfill quest")
    quest_root = Path(quest["quest_root"])

    legacy_path = quest_root / "artifacts" / "milestones" / "legacy-milestone.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        legacy_path,
        {
            "kind": "milestone",
            "artifact_id": "legacy-milestone",
            "summary": "Legacy artifact without an index line.",
            "updated_at": "2026-03-30T00:00:00+00:00",
            "workspace_root": str(quest_root),
        },
    )

    artifacts = quest_service._collect_artifacts(quest_root)
    assert len(artifacts) == 1
    assert artifacts[0]["payload"]["artifact_id"] == "legacy-milestone"

    projection = read_json(quest_service._artifact_projection_path(quest_root), {})
    assert projection["schema_version"] == 2
    assert projection["state_kind"] == "raw"


def test_artifact_record_updates_projection_incrementally(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    artifact = ArtifactService(temp_home)
    quest = quest_service.create("artifact projection incremental update quest")
    quest_root = Path(quest["quest_root"])

    first_result = artifact.record(
        quest_root,
        {
            "kind": "milestone",
            "summary": "First projected artifact.",
            "message": "First projected artifact.",
        },
        checkpoint=False,
    )
    quest_service._collect_artifacts(quest_root)

    def _fail_raw(_quest_root: Path) -> list[dict[str, Any]]:
        raise AssertionError("raw artifact scan should not run after an incremental projection update")

    monkeypatch.setattr(quest_service, "_collect_artifacts_raw", _fail_raw)

    second_result = artifact.record(
        quest_root,
        {
            "kind": "milestone",
            "summary": "Second projected artifact.",
            "message": "Second projected artifact.",
        },
        checkpoint=False,
    )

    artifacts = quest_service._collect_artifacts(quest_root)
    artifact_ids = {
        str((item.get("payload") or {}).get("artifact_id") or "")
        for item in artifacts
    }
    assert first_result["artifact_id"] in artifact_ids
    assert second_result["artifact_id"] in artifact_ids


def test_idea_interaction_message_stays_concise_and_design_focused(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    artifact = ArtifactService(temp_home)
    quest = quest_service.create("concise idea interaction quest")
    quest_root = Path(quest["quest_root"])

    message = artifact._build_idea_interaction_message(
        quest_root=quest_root,
        action="create",
        idea_id="idea-001",
        title="Sparse routing adapter",
        mechanism="Add a sparse routing adapter on top of the baseline encoder.",
        method_brief="Insert a lightweight router that only activates a small expert subset.",
        foundation_label="baseline model",
        branch_name="idea/quest-idea-001",
        change_layer="adapter block",
        source_lens="conditional routing",
        expected_gain="improve calibration without widening the whole model",
        next_target="experiment",
    )

    assert ("Innovation:" in message) or ("创新点：" in message)
    assert ("Compared with baseline model:" in message) or ("相对 baseline model：" in message)
    assert "Problem" not in message
    assert "Hypothesis" not in message
    assert "Idea doc" not in message
    assert "Draft" not in message
    assert len(message.splitlines()) <= 4


def test_idea_interaction_message_keeps_full_text_without_inline_truncation(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    artifact = ArtifactService(temp_home)
    quest = quest_service.create("full idea interaction quest")
    quest_root = Path(quest["quest_root"])

    long_tail = "final detail token for the user-facing idea message"
    message = artifact._build_idea_interaction_message(
        quest_root=quest_root,
        action="create",
        idea_id="idea-002",
        title="Long-form routing adapter",
        mechanism=f"Add a routing adapter that keeps the quantized path stable and preserves {long_tail}.",
        method_brief=f"Use a staged router with explicit fallback control and preserve {long_tail}.",
        foundation_label="baseline model",
        branch_name="idea/quest-idea-002",
        change_layer="adapter block and scheduling policy",
        source_lens="conditional routing with explicit fallback stability constraints",
        expected_gain=f"improve calibration and preserve {long_tail}",
        next_target="experiment",
    )

    assert long_tail in message
    assert "…" not in message


def test_submit_idea_lineage_intent_creates_child_and_sibling_like_nodes(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("idea lineage quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-lineage")

    first_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="First route",
        problem="Baseline saturates.",
        hypothesis="A first improvement path exists.",
        mechanism="Add a small adapter.",
        decision_reason="Open the first durable idea line.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="main-lineage-001",
        title="First route main run",
        hypothesis="The first route helps.",
        setup="Use baseline recipe.",
        execution="Ran validation.",
        results="Improved accuracy.",
        conclusion="Use the measured result to continue branching.",
        metric_rows=[{"metric_id": "acc", "value": 0.87}],
    )
    assert quest_service.snapshot(quest["quest_id"])["active_anchor"] == "decision"

    child_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        lineage_intent="continue_line",
        title="Child route",
        problem="Extend the winning line.",
        hypothesis="The measured win supports a stronger child route.",
        mechanism="Deepen the adapter path.",
        decision_reason="Continue the active line from the measured result.",
        draft_markdown="# Child route draft\n\n## Selected Claim\n\nDeepen the adapter path.\n",
    )
    sibling_like_idea = artifact.submit_idea(
        quest_root,
        mode="create",
        lineage_intent="branch_alternative",
        title="Sibling-like route",
        problem="Try an alternative from the same parent foundation.",
        hypothesis="A sibling route may outperform the direct continuation.",
        mechanism="Change the intervention point while keeping the same parent foundation.",
        decision_reason="Branch an alternative from the parent foundation.",
        draft_markdown="# Sibling route draft\n\n## Selected Claim\n\nChange the intervention point.\n",
    )

    child_metadata, _ = load_markdown_document(Path(child_idea["idea_md_path"]))
    sibling_metadata, _ = load_markdown_document(Path(sibling_like_idea["idea_md_path"]))

    assert child_idea["lineage_intent"] == "continue_line"
    assert child_idea["parent_branch"] == "run/main-lineage-001"
    assert child_idea["foundation_ref"]["kind"] == "run"
    assert child_idea["foundation_ref"]["ref"] == "main-lineage-001"
    assert child_metadata["lineage_intent"] == "continue_line"

    assert sibling_like_idea["lineage_intent"] == "branch_alternative"
    assert sibling_like_idea["parent_branch"] == "run/main-lineage-001"
    assert sibling_like_idea["foundation_ref"]["kind"] == "run"
    assert sibling_like_idea["foundation_ref"]["ref"] == "main-lineage-001"
    assert sibling_metadata["lineage_intent"] == "branch_alternative"

    branches = artifact.list_research_branches(quest_root)
    by_branch = {item["branch_name"]: item for item in branches["branches"]}
    assert by_branch[child_idea["branch"]]["lineage_intent"] == "continue_line"
    assert by_branch[child_idea["branch"]]["parent_branch"] == "run/main-lineage-001"
    assert by_branch[child_idea["branch"]]["idea_draft_path"].endswith("/draft.md")
    assert by_branch[sibling_like_idea["branch"]]["lineage_intent"] == "branch_alternative"
    assert by_branch[sibling_like_idea["branch"]]["parent_branch"] == "run/main-lineage-001"
    assert by_branch[sibling_like_idea["branch"]]["idea_draft_path"].endswith("/draft.md")


def test_stage_view_exposes_idea_draft_content_and_subviews(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("idea draft stage view quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    _confirm_local_baseline(artifact, quest_root, baseline_id="baseline-draft")

    idea = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Drafted route",
        problem="Baseline saturates early.",
        hypothesis="A clearer route helps later execution.",
        mechanism="Introduce a compact adapter.",
        decision_reason="Record the chosen route with a durable draft.",
        draft_markdown="# Drafted route\n\n## Theory and Method\n\nUse a compact adapter.\n",
    )

    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": idea["branch"],
            "selection_type": "branch_node",
            "branch_name": idea["branch"],
            "stage_key": "idea",
            "compare_base": "main",
            "compare_head": idea["branch"],
        },
    )

    assert stage_view["draft_available"] is True
    assert stage_view["idea_draft_path"].endswith("/draft.md")
    assert stage_view["subviews"] == ["overview", "details", "draft"]
    assert "Use a compact adapter." in stage_view["details"]["branch"]["idea_draft_markdown"]


def test_attach_baseline_fails_when_registry_source_is_not_materializable(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("broken baseline attach quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    artifact.baselines.publish(
        {
            "baseline_id": "broken-baseline",
            "summary": "Broken baseline entry",
            "path": str(temp_home / "missing-baseline-root"),
        }
    )

    result = artifact.attach_baseline(quest_root, "broken-baseline")

    assert result["ok"] is False
    assert "could not be materialized" in str(result["message"])
    attachment = read_yaml(quest_root / "baselines" / "imported" / "broken-baseline" / "attachment.yaml", {})
    assert attachment["materialization"]["status"] == "error"
    assert list((quest_root / "artifacts" / "reports").glob("*.json")) == []


def test_baseline_registry_backfills_confirmed_legacy_quests(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("legacy confirmed baseline quest")
    quest_root = Path(quest["quest_root"])
    baseline_root = quest_root / "baselines" / "local" / "legacy-baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Legacy baseline\n", encoding="utf-8")

    quest_service.update_baseline_state(
        quest_root,
        baseline_gate="confirmed",
        confirmed_baseline_ref={
            "baseline_id": "legacy-baseline",
            "variant_id": None,
            "baseline_path": str(baseline_root),
            "baseline_root_rel_path": "baselines/local/legacy-baseline",
            "source_mode": "local",
            "confirmed_at": "2026-03-12T00:00:00Z",
        },
        active_anchor="idea",
    )

    registry = BaselineRegistry(temp_home)
    entries = registry.list_entries()
    entry = next(item for item in entries if item["baseline_id"] == "legacy-baseline")

    assert entry["status"] == "quest_confirmed"
    assert entry["source_quest_id"] == quest["quest_id"]
    assert entry["source_baseline_path"] == str(baseline_root)
    assert entry["materializable"] is True
    assert entry["availability"] == "ready"


def test_artifact_arxiv_overview_falls_back_to_arxiv_abstract(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    artifact = ArtifactService(temp_home)

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            raise TimeoutError("api timed out")
        if url.endswith("/overview/2010.11929.md"):
            raise TimeoutError("overview timed out")
        if url.endswith("/abs/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <meta name="citation_title" content="An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale" />
                    <meta name="citation_author" content="Dosovitskiy, Alexey" />
                  </head>
                  <body>
                    <blockquote class="abstract mathjax">
                      <span class="descriptor">Abstract:</span>
                      Vision Transformers apply pure transformer layers directly to image patches.
                    </blockquote>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    result = artifact.arxiv("2010.11929")

    assert result["ok"] is True
    assert result["source"] == "arxiv_abstract"
    assert result["content_mode"] == "abstract"
    assert "An Image is Worth 16x16 Words" in result["content"]
    assert "Vision Transformers apply pure transformer layers" in result["content"]
    assert result["attempts"][0]["source"] == "arxiv_api"
    assert result["attempts"][0]["ok"] is False
    assert result["attempts"][1]["source"] == "arxiv_abstract"
    assert result["attempts"][1]["ok"] is True


def test_artifact_arxiv_full_text_falls_back_to_html(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    artifact = ArtifactService(temp_home)

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            return _FakeUrlopenResponse(
                """
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2010.11929</id>
                    <published>2020-10-23T17:54:00Z</published>
                    <title>An Image is Worth 16x16 Words</title>
                    <summary>Vision Transformers apply pure transformer layers directly to image patches.</summary>
                    <author><name>Dosovitskiy, Alexey</name></author>
                    <arxiv:primary_category term="cs.CV" />
                    <category term="cs.CV" />
                  </entry>
                </feed>
                """
            )
        if url.endswith("/abs/2010.11929.md"):
            raise HTTPError(url, 404, "not found", hdrs=None, fp=None)
        if url.endswith("/html/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <title>An Image is Worth 16x16 Words</title>
                  </head>
                  <body>
                    <article>
                      <h1>An Image is Worth 16x16 Words</h1>
                      <p>Introduction.</p>
                      <p>Methods.</p>
                    </article>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    result = artifact.arxiv("2010.11929", full_text=True)

    assert result["ok"] is True
    assert result["source"] == "arxiv_html"
    assert result["content_mode"] == "full_text"
    assert "Introduction." in result["content"]
    assert "Methods." in result["content"]
    assert result["attempts"][0]["source"] == "arxiv_api"
    assert result["attempts"][0]["ok"] is True
    assert result["attempts"][1]["source"] == "alphaxiv_full_text"
    assert result["attempts"][1]["ok"] is False


def test_artifact_arxiv_read_mode_persists_quest_library_and_lists_saved_items(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("persist arxiv quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            return _FakeUrlopenResponse(
                """
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2010.11929</id>
                    <published>2020-10-23T17:54:00Z</published>
                    <title>Vision Transformers</title>
                    <summary>Vision Transformers apply pure transformer layers directly to image patches.</summary>
                    <author><name>Dosovitskiy, Alexey</name></author>
                    <arxiv:primary_category term="cs.CV" />
                    <category term="cs.CV" />
                  </entry>
                </feed>
                """
            )
        if url.endswith("/overview/2010.11929.md"):
            return _FakeUrlopenResponse(
                "# Vision Transformers\n\nVision Transformers apply pure transformer layers directly to image patches and remain competitive with CNNs."
            )
        if url.endswith("/pdf/2010.11929.pdf"):
            return _FakeUrlopenResponse("%PDF-1.7\nfake pdf body")
        if url.endswith("/abs/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <meta name="citation_title" content="Vision Transformers" />
                    <meta name="citation_author" content="Dosovitskiy, Alexey" />
                  </head>
                  <body>
                    <blockquote class="abstract mathjax">
                      <span class="descriptor">Abstract:</span>
                      Vision Transformers apply pure transformer layers directly to image patches.
                    </blockquote>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    monkeypatch.setattr("deepscientist.arxiv_library.urlopen", fake_urlopen)

    result = artifact.arxiv("2010.11929", mode="read", quest_root=quest_root)

    assert result["ok"] is True
    assert result["mode"] == "read"
    assert result["paper_id"] == "2010.11929"
    assert result["summary_source"] == "alphaxiv_overview"
    assert result["metadata_source"] == "arxiv_api"
    assert result["overview_markdown"].startswith("# Vision Transformers")
    assert result["status"] in {"processing", "ready"}

    pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2010.11929.pdf"
    for _ in range(40):
        if pdf_path.exists():
            break
        time.sleep(0.05)
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")

    manifest = {}
    for _ in range(40):
        manifest = read_json(quest_root / "literature" / "arxiv" / "index.json", {})
        items = manifest.get("items") or []
        if items and items[0].get("status") == "ready":
            break
        time.sleep(0.05)
    assert manifest["schema_version"] == 2
    saved = manifest["items"][0]
    assert saved["arxiv_id"] == "2010.11929"
    assert saved["title"] == "Vision Transformers"
    assert "transformer layers directly to image patches" in saved["abstract"]
    assert saved["pdf_rel_path"] == "literature/arxiv/pdfs/2010.11929.pdf"
    assert saved["status"] == "ready"
    assert saved["metadata_source"] == "arxiv_api"
    assert saved["summary_source"] == "alphaxiv_overview"
    assert saved["overview_markdown"].startswith("# Vision Transformers")
    assert saved["bibtex"].startswith("@misc{")

    listed = artifact.arxiv(mode="list", quest_root=quest_root)
    assert listed["ok"] is True
    assert listed["mode"] == "list"
    assert listed["count"] == 1
    assert listed["items"][0]["arxiv_id"] == "2010.11929"
    assert listed["items"][0]["overview_markdown"].startswith("# Vision Transformers")
    assert listed["items"][0]["document_id"] == "questpath::literature/arxiv/pdfs/2010.11929.pdf"


def test_artifact_arxiv_list_refreshes_legacy_summary_markdown(
    temp_home: Path, monkeypatch
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("legacy arxiv summary quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            return _FakeUrlopenResponse(
                """
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2010.11929</id>
                    <published>2020-10-23T17:54:00Z</published>
                    <title>Vision Transformers</title>
                    <summary>Vision Transformers apply pure transformer layers directly to image patches.</summary>
                    <author><name>Dosovitskiy, Alexey</name></author>
                    <arxiv:primary_category term="cs.CV" />
                    <category term="cs.CV" />
                  </entry>
                </feed>
                """
            )
        if url.endswith("/overview/2010.11929.md"):
            return _FakeUrlopenResponse("# Vision Transformers\n\nA concise AlphaXiv summary.")
        if url.endswith("/abs/2010.11929"):
            return _FakeUrlopenResponse(
                """
                <html>
                  <head>
                    <meta name="citation_title" content="Vision Transformers" />
                    <meta name="citation_author" content="Dosovitskiy, Alexey" />
                  </head>
                  <body>
                    <blockquote class="abstract mathjax">
                      <span class="descriptor">Abstract:</span>
                      Vision Transformers apply pure transformer layers directly to image patches.
                    </blockquote>
                  </body>
                </html>
                """
            )
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    monkeypatch.setattr("deepscientist.arxiv_library.urlopen", fake_urlopen)

    artifact.arxiv_library.upsert_item(
        quest_root,
        {
            "arxiv_id": "2010.11929",
            "title": "Vision Transformers",
            "display_name": "Vision Transformers",
            "authors": ["Dosovitskiy, Alexey"],
            "categories": ["cs.CV"],
            "abstract": "Vision Transformers apply pure transformer layers directly to image patches.",
            "published_at": "2020-10-23T17:54:00Z",
            "metadata_source": "arxiv_api",
            "metadata_status": "ready",
            "summary_source": "arxiv_api",
            "bibtex": "@misc{vit,title={Vision Transformers}}",
            "status": "ready",
            "pdf_rel_path": "literature/arxiv/pdfs/2010.11929.pdf",
        },
    )

    listed = artifact.arxiv(mode="list", quest_root=quest_root)

    assert listed["ok"] is True
    assert listed["items"][0]["summary_source"] == "alphaxiv_overview"
    assert listed["items"][0]["overview_markdown"].startswith("# Vision Transformers")
    assert listed["items"][0]["overview_source"] == "alphaxiv_overview"


def test_artifact_arxiv_read_mode_preserves_placeholder_when_metadata_times_out(
    temp_home: Path, monkeypatch
) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("pending arxiv quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    def fake_urlopen(request, timeout=8):  # noqa: ANN001
        url = request.full_url
        if "export.arxiv.org/api/query" in url:
            raise TimeoutError("metadata timed out")
        if url.endswith("/abs/2509.26603"):
            raise TimeoutError("abstract timed out")
        if url.endswith("/pdf/2509.26603.pdf"):
            return _FakeUrlopenResponse("%PDF-1.7\nfake pdf body")
        raise AssertionError(url)

    monkeypatch.setattr("deepscientist.artifact.arxiv.urlopen", fake_urlopen)
    monkeypatch.setattr("deepscientist.arxiv_library.urlopen", fake_urlopen)

    result = artifact.arxiv("2509.26603", mode="read", quest_root=quest_root)

    assert result["ok"] is True
    assert result["metadata_pending"] is True
    assert result["metadata_status"] == "pending"
    assert result["abs_url"] == "https://arxiv.org/abs/2509.26603"
    assert result["title"] == "2509.26603"

    pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2509.26603.pdf"
    for _ in range(40):
        if pdf_path.exists():
            break
        time.sleep(0.05)
    assert pdf_path.exists()

    listed = artifact.arxiv(mode="list", quest_root=quest_root)
    assert listed["items"][0]["metadata_status"] == "pending"


def test_open_document_supports_legacy_path_arxiv_ids_from_worktree(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("legacy arxiv path quest")
    quest_root = Path(quest["quest_root"])
    pdf_path = quest_root / "literature" / "arxiv" / "pdfs" / "2010.11929.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7\nlegacy arxiv path")

    worktree_root = quest_root / ".ds" / "worktrees" / "analysis-test"
    worktree_root.mkdir(parents=True, exist_ok=True)
    quest_service.update_research_state(quest_root, current_workspace_root=str(worktree_root))

    payload = quest_service.open_document(quest["quest_id"], "path::literature/arxiv/pdfs/2010.11929.pdf")

    assert payload["title"] == "2010.11929.pdf"
    assert payload["path"] == str(pdf_path)
    assert payload["mime_type"] == "application/pdf"


def test_artifact_interact_respects_primary_connector_policy(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    config["connectors"]["system_enabled"]["slack"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["telegram"]["enabled"] = True
    connectors["slack"]["enabled"] = True
    connectors["_routing"]["primary_connector"] = "telegram"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_plus_local"
    write_yaml(manager.path_for("connectors"), connectors)

    def fake_telegram_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "transport": "telegram-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.TelegramConnectorBridge.deliver", fake_telegram_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact routing quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.bind_source(quest["quest_id"], "web")
    quest_service.bind_source(quest["quest_id"], "telegram:direct:tg-user-1")
    quest_service.bind_source(quest["quest_id"], "slack:direct:slack-user-1")

    result = artifact.interact(
        quest_root,
        kind="milestone",
        message="Primary connector routing test.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"
    assert result["delivery_policy"] == "primary_plus_local"
    assert result["preferred_connector"] == "telegram"
    assert result["delivery_targets"] == ["local:default", "telegram:direct:tg-user-1"]

    local_records = read_jsonl(temp_home / "logs" / "connectors" / "local" / "outbox.jsonl")
    telegram_records = read_jsonl(temp_home / "logs" / "connectors" / "telegram" / "outbox.jsonl")
    slack_outbox = temp_home / "logs" / "connectors" / "slack" / "outbox.jsonl"

    assert any("Primary connector routing test." in str(item.get("message") or "") for item in local_records)
    assert any("Primary connector routing test." in str(item.get("text") or "") for item in telegram_records)
    assert not slack_outbox.exists()


def test_artifact_interact_fans_out_to_all_bound_connectors_without_primary(
    temp_home: Path,
    monkeypatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["telegram"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["telegram"]["enabled"] = True
    connectors["_routing"]["primary_connector"] = None
    connectors["_routing"]["artifact_delivery_policy"] = "primary_plus_local"
    write_yaml(manager.path_for("connectors"), connectors)

    deliveries: list[str] = []

    def fake_qq_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(str(payload.get("conversation_id") or ""))
        return {"ok": True, "transport": "qq-http"}

    def fake_telegram_deliver(_self, payload, _config):  # noqa: ANN001
        deliveries.append(str(payload.get("conversation_id") or ""))
        return {"ok": True, "transport": "telegram-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_qq_deliver)
    monkeypatch.setattr("deepscientist.bridges.connectors.TelegramConnectorBridge.deliver", fake_telegram_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact fanout quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.bind_source(quest["quest_id"], "local:default")
    quest_service.bind_source(quest["quest_id"], "qq:direct:qq-user-1")
    quest_service.bind_source(quest["quest_id"], "telegram:direct:tg-user-1")

    result = artifact.interact(
        quest_root,
        kind="milestone",
        message="Fanout all bound connectors.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"
    assert result["delivery_policy"] == "primary_plus_local"
    assert result["preferred_connector"] is None
    assert result["delivery_targets"] == [
        "local:default",
        "qq:direct:qq-user-1",
        "telegram:direct:tg-user-1",
    ]
    assert "qq:direct:qq-user-1" in deliveries
    assert "telegram:direct:tg-user-1" in deliveries

    qq_records = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    telegram_records = read_jsonl(temp_home / "logs" / "connectors" / "telegram" / "outbox.jsonl")

    assert qq_records[-1]["delivery"]["ok"] is True
    assert telegram_records[-1]["delivery"]["ok"] is True


def test_artifact_interact_auto_uses_single_enabled_connector_for_primary_only(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["connectors"]["system_enabled"]["whatsapp"] = True
    write_yaml(manager.path_for("config"), config)
    connectors = manager.load_named("connectors")
    connectors["whatsapp"]["enabled"] = True
    connectors["_routing"]["primary_connector"] = None
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("single connector routing quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.bind_source(quest["quest_id"], "web")
    quest_service.bind_source(quest["quest_id"], "whatsapp:direct:+15550001111")

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="Single connector auto-selection test.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["preferred_connector"] == "whatsapp"
    assert result["delivery_policy"] == "primary_only"
    assert result["delivery_targets"] == ["whatsapp:direct:+15550001111"]

    whatsapp_records = read_jsonl(temp_home / "logs" / "connectors" / "whatsapp" / "outbox.jsonl")
    local_outbox = temp_home / "logs" / "connectors" / "local" / "outbox.jsonl"

    assert any("Single connector auto-selection test." in str(item.get("text") or "") for item in whatsapp_records)
    assert not local_outbox.exists()


def test_artifact_interact_routes_to_weixin_connector(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["weixin"]["enabled"] = True
    connectors["weixin"]["bot_token"] = "wx-token"
    connectors["weixin"]["account_id"] = "wx-bot-1@im.bot"
    connectors["weixin"]["login_user_id"] = "wx-owner@im.wechat"
    connectors["_routing"]["primary_connector"] = "weixin"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact weixin routing quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.bind_source(quest["quest_id"], "web")
    quest_service.bind_source(quest["quest_id"], "weixin:direct:wx-user-1@im.wechat")
    remember_weixin_context_token(
        temp_home / "logs" / "connectors" / "weixin",
        user_id="wx-user-1@im.wechat",
        context_token="ctx-token-1",
        account_id="wx-bot-1@im.bot",
    )

    sends: list[dict] = []

    def fake_send_weixin_message(*, base_url, token, body, route_tag=None, timeout_ms=15_000):  # noqa: ANN001
        sends.append(
            {
                "base_url": base_url,
                "token": token,
                "body": body,
                "route_tag": route_tag,
                "timeout_ms": timeout_ms,
            }
        )
        return {}

    monkeypatch.setattr("deepscientist.bridges.connectors.send_weixin_message", fake_send_weixin_message)

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="Weixin artifact interaction test.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"
    assert result["preferred_connector"] == "weixin"
    assert result["delivery_policy"] == "primary_only"
    assert result["delivery_targets"] == ["weixin:direct:wx-user-1@im.wechat"]
    assert len(sends) == 1
    assert sends[0]["token"] == "wx-token"
    assert sends[0]["body"]["msg"]["to_user_id"] == "wx-user-1@im.wechat"
    assert sends[0]["body"]["msg"]["context_token"] == "ctx-token-1"
    assert sends[0]["body"]["msg"]["item_list"][0]["text_item"]["text"] == "Weixin artifact interaction test."

    weixin_records = read_jsonl(temp_home / "logs" / "connectors" / "weixin" / "outbox.jsonl")
    assert any("Weixin artifact interaction test." in str(item.get("text") or "") for item in weixin_records)


def test_artifact_interact_persists_surface_actions_and_connector_payload(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    def fake_qq_deliver(_self, _payload, _config):  # noqa: ANN001
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_qq_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact surface actions quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    quest_service.bind_source(quest["quest_id"], "qq:direct:qq-user-surface")

    surface_actions = [
        {
            "type": "send_notification",
            "title": "Checkpoint reached",
            "body": "Main baseline audit completed.",
        }
    ]
    result = artifact.interact(
        quest_root,
        kind="milestone",
        message="Surface action delivery test.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
        surface_actions=surface_actions,
    )

    assert result["status"] == "ok"
    assert result["surface_actions"] == surface_actions
    assert result["delivery_targets"] == ["qq:direct:qq-user-surface"]

    qq_records = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    assert qq_records
    assert qq_records[-1]["surface_actions"] == surface_actions

    interaction_records = quest_service.latest_artifact_interaction_records(quest_root, limit=5)
    assert interaction_records
    assert interaction_records[-1]["surface_actions"] == surface_actions

    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    outbound = [item for item in events if item.get("type") == "connector.outbound"]
    assert outbound
    assert outbound[-1]["surface_actions"] == surface_actions


def test_artifact_interact_normalizes_attachment_paths_and_returns_delivery_results(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    captured: list[dict] = []

    def fake_qq_deliver(_self, payload, _config):  # noqa: ANN001
        captured.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_qq_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact attachment normalize quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    quest_service.bind_source(quest["quest_id"], "qq:direct:qq-user-absolute")

    relative_path = Path("artifacts") / "reports" / "summary.png"
    absolute_path = quest_root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(b"fake-image")

    result = artifact.interact(
        quest_root,
        kind="milestone",
        message="Attachment normalization test.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
        attachments=[
            {
                "kind": "path",
                "path": str(relative_path),
                "label": "summary",
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["attachment_issues"] == []
    assert result["normalized_attachments"][0]["path"] == str(absolute_path.resolve())
    assert result["delivery_results"]
    assert result["delivery_results"][0]["ok"] is True
    assert result["delivery_results"][0]["conversation_id"] == "qq:direct:qq-user-absolute"
    assert captured
    assert captured[-1]["attachments"][0]["path"] == str(absolute_path.resolve())


def test_record_main_experiment_auto_generates_and_sends_metric_charts_to_bound_qq(
    temp_home: Path,
    monkeypatch,
) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    write_yaml(manager.path_for("connectors"), connectors)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("main experiment chart delivery quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    quest_service.bind_source(quest["quest_id"], "qq:direct:qq-user-chart")

    baseline_root = quest_root / "baselines" / "local" / "baseline-chart"
    baseline_root.mkdir(parents=True, exist_ok=True)
    (baseline_root / "README.md").write_text("# Baseline\n", encoding="utf-8")
    artifact.confirm_baseline(
        quest_root,
        baseline_path=str(baseline_root),
        baseline_id="baseline-chart",
        summary="Baseline with two chartable metrics.",
        metrics_summary={"acc": 0.8, "loss": 0.42},
        primary_metric={"metric_id": "acc", "value": 0.8},
        metric_contract={
            "primary_metric_id": "acc",
            "metrics": [
                {
                    "metric_id": "acc",
                    "direction": "higher",
                    "description": "Accuracy.",
                    "derivation": "Read from evaluation output.",
                    "source_ref": "eval.py",
                },
                {
                    "metric_id": "loss",
                    "direction": "lower",
                    "description": "Loss.",
                    "derivation": "Read from evaluation output.",
                    "source_ref": "eval.py",
                },
            ],
        },
    )
    artifact.submit_idea(
        quest_root,
        title="Chart route",
        problem="Need chart delivery after the main run.",
        hypothesis="The route should notify bound connectors with metric charts.",
        mechanism="Hook chart generation into the main experiment completion flow.",
        decision_reason="Exercise automatic connector chart delivery.",
    )

    deliveries: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def fake_deliver(channel_name, payload, *, connectors):  # noqa: ANN001
        deliveries.append(
            {
                "channel": channel_name,
                "payload": payload,
            }
        )
        return {"ok": True, "transport": f"{channel_name}-mock"}

    monkeypatch.setattr(artifact, "_deliver_to_channel", fake_deliver)
    monkeypatch.setattr("deepscientist.artifact.service.time.sleep", lambda seconds: sleeps.append(float(seconds)))

    result = artifact.record_main_experiment(
        quest_root,
        run_id="main-chart-001",
        title="Charted main run",
        hypothesis="The charted run should beat the baseline.",
        setup="Use the confirmed baseline contract.",
        execution="Ran the main experiment once.",
        results="Both metrics improved in the expected directions.",
        conclusion="Charts should be generated and sent automatically.",
        metric_rows=[
            {"metric_id": "acc", "value": 0.91, "direction": "higher"},
            {"metric_id": "loss", "value": 0.31, "direction": "lower"},
        ],
        evaluation_summary={
            "takeaway": "The main run improves both tracked metrics.",
            "claim_update": "strengthens",
            "baseline_relation": "better",
            "comparability": "high",
            "failure_mode": "none",
            "next_action": "analysis_campaign",
        },
    )

    chart_deliveries = [
        item for item in deliveries if str((item.get("payload") or {}).get("kind") or "") == "main_experiment_metric_chart"
    ]
    assert result["connector_metric_charts"]
    assert len(result["connector_metric_charts"]) == 2
    assert all(Path(item["path"]).exists() for item in result["connector_metric_charts"])
    assert result["connector_metric_chart_delivery"]["enabled"] is True
    assert result["connector_metric_chart_delivery"]["chart_count"] == 2
    assert len(chart_deliveries) == 2
    assert [item["channel"] for item in chart_deliveries] == ["qq", "qq"]
    assert chart_deliveries[0]["payload"]["attachments"][0]["connector_delivery"]["qq"]["allow_internal_auto_media"] is True
    assert chart_deliveries[0]["payload"]["attachments"][0]["connector_delivery"]["qq"]["media_kind"] == "image"
    assert chart_deliveries[0]["payload"]["attachments"][0]["connector_delivery"]["weixin"]["media_kind"] == "image"
    assert sleeps == [2.0]


def test_artifact_interact_reports_missing_attachment_path_to_agent(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("artifact attachment error quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="Missing attachment path test.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        attachments=[
            {
                "kind": "path",
                "path": "artifacts/reports/missing.png",
                "label": "missing",
                "connector_delivery": {"qq": {"media_kind": "image"}},
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["attachment_issues"]
    assert result["attachment_issues"][0]["error"] == "attachment path does not exist"
    assert result["normalized_attachments"][0]["path"].endswith("/artifacts/reports/missing.png")


def test_explorer_lists_real_files_and_path_documents_can_be_saved(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("explorer quest")
    quest_root = Path(quest["quest_root"])

    note_path = quest_root / "literature" / "notes.md"
    note_path.write_text("# Notes\n\nInitial baseline scouting.", encoding="utf-8")

    explorer = quest_service.explorer(quest["quest_id"])
    assert explorer["quest_root"] == str(quest_root.resolve())
    research = next(section for section in explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    note_node = next(node for node in research_nodes if node.get("path") == "literature/notes.md")
    assert note_node["document_id"] == "path::literature/notes.md"
    assert note_node["writable"] is True

    opened = quest_service.open_document(quest["quest_id"], note_node["document_id"])
    assert "Initial baseline scouting." in opened["content"]

    saved = quest_service.save_document(
        quest["quest_id"],
        note_node["document_id"],
        "# Notes\n\nUpdated from explorer.",
        previous_revision=opened["revision"],
    )
    assert saved["ok"] is True

    reopened = quest_service.open_document(quest["quest_id"], note_node["document_id"])
    assert "Updated from explorer." in reopened["content"]


def test_explorer_search_finds_paths_and_normalizes_legacy_glob_wrappers(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("explorer search quest")
    quest_root = Path(quest["quest_root"])

    script_path = quest_root / "experiments" / "analysis" / "new-slice" / "scripts" / "run_probe.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("print('analysis runner')\n", encoding="utf-8")

    path_result = quest_service.search_files(quest["quest_id"], "run_probe", limit=10)
    assert any(item["path"] == "experiments/analysis/new-slice/scripts/run_probe.py" for item in path_result["items"])

    wrapped_result = quest_service.search_files(quest["quest_id"], "*analysis runner*", limit=10)
    assert any(item["path"] == "experiments/analysis/new-slice/scripts/run_probe.py" for item in wrapped_result["items"])


def test_explorer_search_skips_heavy_runtime_mirrors_by_default(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("explorer search runtime hygiene quest")
    quest_root = Path(quest["quest_root"])

    note_path = quest_root / "notes" / "runtime-note.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("needle-runtime-hygiene in user content\n", encoding="utf-8")
    terminal_log = quest_root / ".ds" / "bash_exec" / "bash-001" / "terminal.log"
    terminal_log.parent.mkdir(parents=True, exist_ok=True)
    terminal_log.write_text("needle-runtime-hygiene in heavy runtime mirror\n", encoding="utf-8")
    run_prompt = quest_root / ".ds" / "runs" / "run-001" / "prompt.md"
    run_prompt.parent.mkdir(parents=True, exist_ok=True)
    run_prompt.write_text("needle-runtime-hygiene in runner prompt mirror\n", encoding="utf-8")

    result = quest_service.search_files(quest["quest_id"], "needle-runtime-hygiene", limit=10)

    paths = {item["path"] for item in result["items"]}
    assert "notes/runtime-note.md" in paths
    assert ".ds/bash_exec/bash-001/terminal.log" not in paths
    assert ".ds/runs/run-001/prompt.md" not in paths


def test_explorer_opens_image_files_as_assets(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("image explorer quest")
    quest_root = Path(quest["quest_root"])

    figure_path = quest_root / "literature" / "figure.png"
    figure_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png")

    explorer = quest_service.explorer(quest["quest_id"])
    research = next(section for section in explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    figure_node = next(node for node in research_nodes if node.get("path") == "literature/figure.png")

    opened = quest_service.open_document(quest["quest_id"], figure_node["document_id"])
    assert opened["meta"]["renderer_hint"] == "image"
    assert opened["mime_type"] == "image/png"
    assert opened["content"] == ""
    assert "documents/asset" in opened["asset_url"]


def test_explorer_marks_paper_latex_folder_for_workspace_opening(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper latex explorer quest")
    quest_root = Path(quest["quest_root"])

    latex_root = quest_root / "paper" / "latex"
    latex_root.mkdir(parents=True, exist_ok=True)
    (latex_root / "main.tex").write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\begin{document}",
                "Hello",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    explorer = quest_service.explorer(quest["quest_id"])
    research = next(section for section in explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    latex_node = next(node for node in research_nodes if node.get("path") == "paper/latex")
    assert latex_node["kind"] == "directory"
    assert latex_node["folder_kind"] == "latex"


def test_explorer_marks_paper_latex_folder_for_snapshot_opening(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("paper latex snapshot explorer quest")
    quest_root = Path(quest["quest_root"])

    latex_root = quest_root / "paper" / "latex"
    latex_root.mkdir(parents=True, exist_ok=True)
    (latex_root / "main.tex").write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\begin{document}",
                "Snapshot",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    from deepscientist.gitops import checkpoint_repo

    checkpoint_repo(quest_root, "Add latex sources", allow_empty=False)
    explorer = quest_service.explorer(quest["quest_id"], revision="HEAD", mode="ref")
    research = next(section for section in explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    latex_node = next(node for node in research_nodes if node.get("path") == "paper/latex")
    assert latex_node["kind"] == "directory"
    assert latex_node["folder_kind"] == "latex"


def test_markdown_asset_upload_uses_sibling_assets_folder(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("markdown asset upload quest")
    quest_root = Path(quest["quest_root"])

    uploaded = quest_service.save_document_asset(
        quest["quest_id"],
        "brief.md",
        file_name="diagram.png",
        mime_type="image/png",
        content=b"\x89PNG\r\n\x1a\nquest-markdown-asset",
        kind="image",
    )

    assert uploaded["ok"] is True
    assert uploaded["relative_path"].startswith("brief.assets/")
    asset_path = quest_root / uploaded["relative_path"]
    assert asset_path.exists()
    assert asset_path.read_bytes().startswith(b"\x89PNG")

    opened = quest_service.open_document(quest["quest_id"], uploaded["asset_document_id"])
    assert opened["meta"]["renderer_hint"] == "image"


def test_workspace_file_mutations_can_create_folder_and_upload_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("workspace file mutation quest")

    created_folder = quest_service.create_workspace_folder(
        quest["quest_id"],
        name="datasets",
        parent_path="literature",
    )
    assert created_folder["ok"] is True
    assert created_folder["item"]["kind"] == "directory"
    assert created_folder["item"]["path"] == "literature/datasets"

    uploaded = quest_service.upload_workspace_file(
        quest["quest_id"],
        parent_path="literature/datasets",
        file_name="notes.txt",
        mime_type="text/plain",
        content=b"baseline notes\n",
    )
    assert uploaded["ok"] is True
    assert uploaded["item"]["kind"] == "file"
    assert uploaded["item"]["path"] == "literature/datasets/notes.txt"
    assert uploaded["item"]["document_id"] == "path::literature/datasets/notes.txt"

    opened = quest_service.open_document(
        quest["quest_id"],
        "path::literature/datasets/notes.txt",
    )
    assert opened["content"] == "baseline notes\n"

    explorer = quest_service.explorer(quest["quest_id"])
    research = next(section for section in explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    assert any(node.get("path") == "literature/datasets" and node.get("kind") == "directory" for node in research_nodes)
    assert any(node.get("path") == "literature/datasets/notes.txt" and node.get("kind") == "file" for node in research_nodes)


def test_workspace_file_mutations_can_rename_move_and_delete_entries(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("workspace rename move delete quest")
    quest_root = Path(quest["quest_root"])

    source_dir = quest_root / "literature" / "notes"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "draft.md"
    source_file.write_text("# Draft\n", encoding="utf-8")

    renamed = quest_service.rename_workspace_entry(
        quest["quest_id"],
        path="literature/notes/draft.md",
        new_name="summary.md",
    )
    assert renamed["ok"] is True
    assert renamed["item"]["path"] == "literature/notes/summary.md"
    assert not source_file.exists()
    assert (source_dir / "summary.md").exists()

    moved = quest_service.move_workspace_entries(
        quest["quest_id"],
        paths=["literature/notes/summary.md"],
        target_parent_path="artifacts",
    )
    assert moved["ok"] is True
    assert moved["items"][0]["path"] == "artifacts/summary.md"
    assert not (source_dir / "summary.md").exists()
    assert (quest_root / "artifacts" / "summary.md").exists()

    deleted = quest_service.delete_workspace_entries(
        quest["quest_id"],
        paths=["artifacts/summary.md", "literature/notes"],
    )
    assert deleted["ok"] is True
    assert sorted(item["path"] for item in deleted["items"]) == [
        "artifacts/summary.md",
        "literature/notes",
    ]
    assert not (quest_root / "artifacts" / "summary.md").exists()
    assert not source_dir.exists()


def test_snapshot_unknown_quest_does_not_materialize_runtime_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))

    with pytest.raises(FileNotFoundError):
        quest_service.snapshot("046")

    ghost_root = temp_home / "quests" / "046"
    assert not ghost_root.exists()


def test_repair_orphaned_quest_scaffold_restores_minimal_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest_root = temp_home / "quests" / "046"
    ensure_dir(quest_root / ".ds")

    repaired = quest_service.repair_orphaned_quest_scaffold("046")

    assert repaired["quest_id"] == "046"
    for relative in ("quest.yaml", "brief.md", "plan.md", "status.md", "SUMMARY.md", ".gitignore"):
        assert (quest_root / relative).exists()
    assert (quest_root / ".git").exists()
    listed = quest_service.list_quests()
    assert any(item["quest_id"] == "046" for item in listed)


def test_questpath_documents_and_stage_view_cover_quest_root_files(temp_home: Path) -> None:
    quest_service = QuestService(temp_home)
    artifact = ArtifactService(temp_home)
    quest = quest_service.create("stage view quest")
    quest_root = temp_home / "quests" / quest["quest_id"]
    docs_dir = quest_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    appendix = docs_dir / "appendix.md"
    appendix.write_text("# Appendix\n\nQuest-root file.\n", encoding="utf-8")

    opened = quest_service.open_document(quest["quest_id"], "questpath::docs/appendix.md")

    assert opened["document_id"] == "questpath::docs/appendix.md"
    assert "Quest-root file" in opened["content"]

    baseline_dir = quest_root / "baselines" / "local" / "baseline-001"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "metrics.json").write_text('{"acc": 0.91}\n', encoding="utf-8")
    result = artifact.confirm_baseline(
        quest_root,
        baseline_path="baselines/local/baseline-001",
        baseline_id="baseline-001",
        summary="Baseline confirmed for stage view.",
        metrics_summary={"acc": 0.91},
        metric_contract={"primary_metric_id": "acc", "direction": "maximize"},
        primary_metric={"metric_id": "acc", "value": 0.91},
    )
    assert result["ok"] is True

    stage_view = quest_service.stage_view(
        quest["quest_id"],
        {
            "selection_ref": "stage:main:baseline",
            "selection_type": "stage_node",
            "branch_name": "main",
            "stage_key": "baseline",
        },
    )

    assert stage_view["stage_key"] == "baseline"
    assert stage_view["title"] == "Baseline · baseline-001"
    assert any(item["label"] == "Attachment" for item in stage_view["sections"]["key_files"])


def test_workflow_uses_questpath_for_quest_root_outputs_when_active_workspace_is_worktree(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("workflow questpath contract")
    quest_root = Path(quest["quest_root"])
    worktree_root = quest_root / ".ds" / "worktrees" / "branch-001"
    worktree_root.mkdir(parents=True, exist_ok=True)
    (worktree_root / "brief.md").write_text("# Worktree brief\n", encoding="utf-8")

    run_output = quest_root / ".ds" / "runs" / "run-001" / "result.txt"
    run_output.parent.mkdir(parents=True, exist_ok=True)
    run_output.write_text("quest-root output\n", encoding="utf-8")
    history_root = quest_root / ".ds" / "codex_history" / "run-001"
    history_root.mkdir(parents=True, exist_ok=True)
    write_json(
        history_root / "meta.json",
        {
            "run_id": "run-001",
            "skill_id": "experiment",
            "summary": "Recorded output",
            "output_path": str(run_output),
        },
    )

    quest_service.update_research_state(
        quest_root,
        current_workspace_root=str(worktree_root),
        research_head_worktree_root=str(worktree_root),
    )

    workflow = quest_service.workflow(quest["quest_id"])
    output_item = next(
        item for item in workflow["changed_files"] if str(item.get("path") or "").endswith(".ds/runs/run-001/result.txt")
    )

    assert output_item["document_id"] == "questpath::.ds/runs/run-001/result.txt"


def test_explorer_can_switch_to_git_snapshot_and_open_historical_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("git snapshot explorer quest")
    quest_root = Path(quest["quest_root"])

    note_path = quest_root / "literature" / "notes.md"
    note_path.write_text("# Notes\n\nCommitted snapshot.", encoding="utf-8")
    from deepscientist.gitops import checkpoint_repo

    checkpoint_repo(quest_root, "Add literature note for snapshot explorer", allow_empty=False)
    note_path.write_text("# Notes\n\nLive working tree update.", encoding="utf-8")

    snapshot_explorer = quest_service.explorer(quest["quest_id"], revision="HEAD", mode="commit")
    assert snapshot_explorer["view"]["mode"] == "commit"
    assert snapshot_explorer["view"]["revision"] == "HEAD"
    assert snapshot_explorer["view"]["read_only"] is True

    research = next(section for section in snapshot_explorer["sections"] if section["id"] == "research")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    research_nodes = flatten(research["nodes"])
    note_node = next(node for node in research_nodes if node.get("path") == "literature/notes.md")
    assert note_node["document_id"] == "git::HEAD::literature/notes.md"
    assert note_node["writable"] is False

    opened = quest_service.open_document(quest["quest_id"], note_node["document_id"])
    assert opened["source_scope"] == "git_snapshot"
    assert opened["writable"] is False
    assert "Committed snapshot." in opened["content"]
    assert "Live working tree update." not in opened["content"]

    save_attempt = quest_service.save_document(
        quest["quest_id"],
        note_node["document_id"],
        "# Notes\n\nShould not save to snapshot.",
        previous_revision=opened["revision"],
    )
    assert save_attempt["ok"] is False
    assert save_attempt["conflict"] is False


def test_explorer_lists_custom_root_files_and_binary_assets(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("custom explorer quest")
    quest_root = Path(quest["quest_root"])

    code_path = quest_root / "src" / "train.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text("print('quest explorer works')\n", encoding="utf-8")

    image_path = quest_root / "figures" / "plot.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nquest-plot")

    pdf_path = quest_root / "docs" / "appendix.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    explorer = quest_service.explorer(quest["quest_id"])
    quest_section = next(section for section in explorer["sections"] if section["id"] == "quest")

    def flatten(nodes: list[dict]) -> list[dict]:
        items: list[dict] = []
        for node in nodes:
            items.append(node)
            items.extend(flatten(node.get("children") or []))
        return items

    quest_nodes = flatten(quest_section["nodes"])

    code_node = next(node for node in quest_nodes if node.get("path") == "src/train.py")
    assert code_node["document_id"] == "path::src/train.py"
    opened_code = quest_service.open_document(quest["quest_id"], code_node["document_id"])
    assert opened_code["meta"]["renderer_hint"] == "code"
    assert "quest explorer works" in opened_code["content"]

    image_node = next(node for node in quest_nodes if node.get("path") == "figures/plot.png")
    opened_image = quest_service.open_document(quest["quest_id"], image_node["document_id"])
    assert opened_image["meta"]["renderer_hint"] == "image"
    assert opened_image["mime_type"] == "image/png"
    assert "documents/asset" in opened_image["asset_url"]

    pdf_node = next(node for node in quest_nodes if node.get("path") == "docs/appendix.pdf")
    opened_pdf = quest_service.open_document(quest["quest_id"], pdf_node["document_id"])
    assert opened_pdf["meta"]["renderer_hint"] == "pdf"
    assert opened_pdf["mime_type"] == "application/pdf"
    assert "documents/asset" in opened_pdf["asset_url"]


def test_artifact_interact_tracks_pending_request_and_user_reply(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("interactive artifact quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    request = artifact.interact(
        quest_root,
        kind="decision_request",
        message="Should I launch the robustness campaign now?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        options=[
            {"id": "launch", "label": "Launch now", "description": "Run the campaign immediately."},
            {"id": "wait", "label": "Wait", "description": "Hold off until more evidence arrives."},
        ],
    )
    assert request["status"] == "ok"
    assert request["expects_reply"] is True
    assert request["open_request_count"] == 1
    snapshot_waiting = quest_service.snapshot(quest["quest_id"])
    assert snapshot_waiting["status"] == "waiting_for_user"
    assert snapshot_waiting["pending_decisions"]
    assert snapshot_waiting["active_interactions"]

    reply = quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="Launch it now and focus on robustness first.",
        source="qq:group:demo",
    )
    snapshot_after_reply = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after_reply["status"] == "running"
    assert any(item.get("status") == "answered" for item in snapshot_after_reply["active_interactions"])

    follow_up = artifact.interact(
        quest_root,
        kind="progress",
        message="Received your instruction; I am preparing the campaign charter.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )
    assert follow_up["status"] == "ok"
    assert follow_up["recent_inbound_messages"]
    latest = follow_up["recent_inbound_messages"][-1]
    assert latest["message_id"] == reply["id"]
    assert latest["conversation_id"] == "qq:group:demo"
    assert latest["text"].startswith("Launch it now")


def test_artifact_interact_redirects_ordinary_decision_requests_in_autonomous_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "autonomous decision quest",
        startup_contract={"decision_policy": "autonomous"},
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.interact(
        quest_root,
        kind="decision_request",
        message="Should I choose branch A or branch B?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        reply_mode="blocking",
        options=[
            {"id": "a", "label": "A", "description": "Choose branch A."},
            {"id": "b", "label": "B", "description": "Choose branch B."},
        ],
    )

    assert result["status"] == "autonomous_redirected"
    assert result["reply_mode"] == "none"
    assert result["interaction_id"] is None
    snapshot_after = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after["status"] != "waiting_for_user"
    assert not snapshot_after["pending_decisions"]


def test_artifact_interact_allows_completion_approval_in_autonomous_mode(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create(
        "autonomous completion approval quest",
        startup_contract={"decision_policy": "autonomous"},
    )
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    request = artifact.interact(
        quest_root,
        kind="decision_request",
        message="The quest appears complete. May I end it now?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        reply_mode="blocking",
        reply_schema={"decision_type": "quest_completion_approval"},
    )

    assert request["status"] == "ok"
    assert request["reply_mode"] == "blocking"
    snapshot_after = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after["status"] == "waiting_for_user"
    assert snapshot_after["pending_decisions"]


def test_bind_source_repairs_lowercased_connector_binding_and_preserves_chat_id_case(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("binding repair quest")

    quest_service.bind_source(quest["quest_id"], "qq:direct:cf8d2d559aa956b48751539adfb98865")
    repaired = quest_service.bind_source(quest["quest_id"], "qq:direct:CF8D2D559AA956B48751539ADFB98865")

    assert repaired["sources"] == ["qq:direct:CF8D2D559AA956B48751539ADFB98865"]


def test_artifact_delivery_prefers_connector_binding_case_for_qq(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    write_yaml(manager.path_for("connectors"), connectors)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("qq artifact delivery quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    write_json(
        quest_root / ".ds" / "bindings.json",
        {"sources": ["local:default", "qq:direct:cf8d2d559aa956b48751539adfb98865"]},
    )
    write_json(
        temp_home / "logs" / "connectors" / "qq" / "bindings.json",
        {
            "bindings": {
                "qq:direct:CF8D2D559AA956B48751539ADFB98865": {
                    "quest_id": quest["quest_id"],
                    "updated_at": "2026-03-11T17:47:49+00:00",
                }
            }
        },
    )

    deliveries: list[str] = []

    class FakeBridge:
        def deliver(self, outbound: dict, config: dict) -> dict:  # noqa: ANN001
            deliveries.append(str(outbound.get("conversation_id") or ""))
            return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.channels.qq.get_connector_bridge", lambda name: FakeBridge())

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="QQ delivery should preserve the original openid casing.",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["delivered"] is True
    assert deliveries == ["qq:direct:CF8D2D559AA956B48751539ADFB98865"]


def test_artifact_record_and_snapshot_include_guidance_vm(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("guidance quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    recorded = artifact.record(
        quest_root,
        {
            "kind": "baseline",
            "status": "completed",
            "baseline_id": "baseline-guidance",
            "summary": "Baseline recorded for guidance coverage.",
            "reason": "Need a durable baseline before ideation.",
            "primary_metric": "acc",
            "metrics_summary": {"acc": 0.87},
        },
    )

    assert recorded["ok"] is True
    assert recorded["guidance_vm"]["current_anchor"] == "baseline"
    assert recorded["guidance_vm"]["recommended_skill"] == "baseline"
    assert recorded["guidance_vm"]["suggested_artifact_calls"][0]["name"] == "artifact.confirm_baseline(...)"
    assert recorded["next_anchor"] == "baseline"
    assert recorded["recommended_skill_reads"] == ["baseline"]
    assert recorded["suggested_artifact_calls"][0]["name"] == "artifact.confirm_baseline(...)"
    assert recorded["next_instruction"] == recorded["guidance"]

    payload = json.loads(Path(recorded["path"]).read_text(encoding="utf-8"))
    assert payload["guidance_vm"]["recommended_action"] == "continue"

    events = read_jsonl(quest_root / ".ds" / "events.jsonl")
    artifact_event = next(item for item in events if item.get("type") == "artifact.recorded")
    assert artifact_event["guidance_vm"]["recommended_skill"] == "baseline"

    snapshot = quest_service.snapshot(quest["quest_id"])
    assert snapshot["guidance"]["recommended_skill"] == "baseline"
    assert "baseline" in snapshot["guidance"]["current_anchor"]


def test_approval_record_closes_pending_interaction(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("approval closes interaction")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    request = artifact.interact(
        quest_root,
        kind="decision_request",
        message="Approve the expensive baseline reproduction?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )
    decision_id = request["artifact_id"]
    snapshot_waiting = quest_service.snapshot(quest["quest_id"])
    assert snapshot_waiting["status"] == "waiting_for_user"

    artifact.record(
        quest_root,
        {
            "kind": "approval",
            "decision_id": decision_id,
            "reason": "Approved by user command.",
        },
    )

    snapshot_after = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after["status"] == "active"
    assert not snapshot_after["pending_decisions"]


def test_complete_quest_requires_explicit_user_approval(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("completion approval required")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    request = artifact.interact(
        quest_root,
        kind="decision_request",
        message="The quest appears complete. May I end it now?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        reply_mode="blocking",
        reply_schema={"decision_type": "quest_completion_approval"},
        options=[
            {"id": "approve", "label": "Approve", "description": "End the quest now."},
            {"id": "continue", "label": "Continue", "description": "Keep working."},
        ],
    )

    quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="好的",
        source="web-react",
        reply_to_interaction_id=request["interaction_id"],
    )

    result = artifact.complete_quest(quest_root, summary="Attempting to complete the quest.")

    assert result["ok"] is False
    assert result["status"] == "approval_not_explicit"
    snapshot_after = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after["status"] != "completed"


def test_complete_quest_marks_quest_completed_after_explicit_user_approval(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("completion approved")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    request = artifact.interact(
        quest_root,
        kind="decision_request",
        message="The quest appears complete. May I end it now?",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
        reply_mode="blocking",
        reply_schema={"decision_type": "quest_completion_approval"},
        options=[
            {"id": "approve", "label": "Approve", "description": "End the quest now."},
            {"id": "continue", "label": "Continue", "description": "Keep working."},
        ],
    )

    reply = quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="同意完成",
        source="web-react",
        reply_to_interaction_id=request["interaction_id"],
    )

    result = artifact.complete_quest(quest_root, summary="Research line finished with reviewed deliverables.")

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["approval_message_id"] == reply["id"]
    assert result["snapshot"]["status"] == "completed"
    assert result["approval"]["record"]["source"]["kind"] == "user"
    assert result["decision"]["record"]["action"] == "stop"


def test_threaded_progress_auto_links_user_reply_without_waiting(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("threaded progress reply quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    progress = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我已经完成仓库结构审计，正在整理下一步复现实验计划。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )

    assert progress["status"] == "ok"
    assert progress["reply_mode"] == "threaded"

    snapshot_after_progress = quest_service.snapshot(quest["quest_id"])
    assert snapshot_after_progress["status"] != "waiting_for_user"
    assert snapshot_after_progress["default_reply_interaction_id"] == progress["interaction_id"]

    reply = quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="继续，先把依赖和数据集入口确认下来。",
        source="web-react",
    )

    assert reply["reply_to_interaction_id"] == progress["interaction_id"]

    interaction_state = json.loads((quest_root / ".ds" / "interaction_state.json").read_text(encoding="utf-8"))
    latest_thread = interaction_state["recent_threads"][-1]
    assert latest_thread["interaction_id"] == progress["interaction_id"]
    assert latest_thread["last_reply_message_id"] == reply["id"]
    assert latest_thread["reply_count"] == 1

    follow_up = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我已经开始核对依赖版本。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert follow_up["recent_inbound_messages"]
    latest = follow_up["recent_inbound_messages"][-1]
    assert latest["message_id"] == reply["id"]
    assert latest["reply_to_interaction_id"] == progress["interaction_id"]


def test_user_message_queue_is_delivered_only_when_artifact_interact_polls(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("queued mailbox quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="先检查训练入口。",
        source="web-react",
    )
    second = quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="然后核对依赖版本。",
        source="qq:group:demo",
    )

    queue_before = json.loads((quest_root / ".ds" / "user_message_queue.json").read_text(encoding="utf-8"))
    assert [item["message_id"] for item in queue_before["pending"]] == [first["id"], second["id"]]
    assert queue_before["message_states"][first["id"]]["read_state"] == "unread"
    assert queue_before["message_states"][second["id"]]["read_state"] == "unread"
    runtime_before = json.loads((quest_root / ".ds" / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_before["pending_user_message_count"] == 2

    polled = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我已经进入检查阶段。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert polled["delivery_batch"] is not None
    assert [item["message_id"] for item in polled["recent_inbound_messages"]] == [first["id"], second["id"]]
    assert "这是最新用户的要求" in polled["agent_instruction"]
    assert "优先于当前后台子任务" in polled["agent_instruction"]
    assert "立即发送一条有实际内容的 follow-up artifact.interact" in polled["agent_instruction"]
    assert "不要再重复发送一条只有“已收到/处理中”的确认" in polled["agent_instruction"]
    assert "先检查训练入口。" in polled["agent_instruction"]
    assert "然后核对依赖版本。" in polled["agent_instruction"]

    queue_after = json.loads((quest_root / ".ds" / "user_message_queue.json").read_text(encoding="utf-8"))
    assert queue_after["pending"] == []
    assert [item["message_id"] for item in queue_after["completed"][-2:]] == [first["id"], second["id"]]
    assert queue_after["message_states"][first["id"]]["read_state"] == "read"
    assert queue_after["message_states"][first["id"]]["read_reason"] == "artifact_mailbox"
    assert queue_after["message_states"][second["id"]]["read_state"] == "read"
    assert queue_after["message_states"][second["id"]]["read_reason"] == "artifact_mailbox"

    runtime_after = json.loads((quest_root / ".ds" / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_after["pending_user_message_count"] == 0
    assert runtime_after["last_delivered_batch_id"] == polled["delivery_batch"]["batch_id"]
    assert runtime_after["last_artifact_interact_at"] is not None

    no_new_message = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我继续推进检查。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert no_new_message["recent_inbound_messages"] == []
    assert "当前用户并没有发送任何消息" in no_new_message["agent_instruction"]
    assert len(no_new_message["recent_interaction_records"]) >= 3


def test_user_message_queue_agent_instruction_respects_english_locale(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["default_locale"] = "en-US"
    write_yaml(manager.path_for("config"), config)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("english mailbox quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.append_message(
        quest["quest_id"],
        role="user",
        content="Check the training entrypoint first.",
        source="web-react",
    )

    polled = artifact.interact(
        quest_root,
        kind="progress",
        message="I am checking the repository.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert "These are the latest user requirements in chronological order." in polled["agent_instruction"]
    assert "take priority over the current background subtask" in polled["agent_instruction"]
    assert "Immediately send one substantive follow-up artifact.interact" in polled["agent_instruction"]
    assert "do not send a redundant receipt-only message" in polled["agent_instruction"]
    assert "Check the training entrypoint first." in polled["agent_instruction"]

    no_new_message = artifact.interact(
        quest_root,
        kind="progress",
        message="I am continuing the check.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=True,
    )

    assert (
        no_new_message["agent_instruction"]
        .startswith("No new user message has arrived. Continue the task according to the user's requirements.")
    )
    assert "Here are the latest 10 artifact-related interaction records:" in no_new_message["agent_instruction"]


def test_duplicate_progress_is_suppressed_when_message_is_unchanged(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("duplicate progress quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我已经完成第一轮检查，当前状态没有变化。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )
    assert first["status"] == "ok"

    second = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我已经完成第一轮检查，当前状态没有变化。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )
    assert second["status"] == "suppressed_duplicate"
    assert second["artifact_id"] == first["artifact_id"]

    journal = read_jsonl(quest_root / ".ds" / "interaction_journal.jsonl")
    outbound = [item for item in journal if str(item.get("type") or "") == "artifact_outbound"]
    assert len(outbound) == 1


def test_interact_preserves_full_message_for_delivery_and_records_summary_preview(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("interaction preview split quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    long_tail = "tail marker that must remain visible to the connector user"
    long_message = (
        "This is a long milestone update that should stay complete in the actual delivered message. "
        "It includes implementation notes, expected impact, and a precise end marker: "
        f"{long_tail}."
    )

    result = artifact.interact(
        quest_root,
        kind="milestone",
        message=long_message,
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"

    progress_records = sorted((quest_root / "artifacts" / "milestones").glob("*.json"))
    assert progress_records
    record = read_json(progress_records[-1], {})
    assert record["message"] == long_message
    assert record["summary_preview"].endswith("…")
    assert long_tail not in record["summary_preview"]

    journal = read_jsonl(quest_root / ".ds" / "interaction_journal.jsonl")
    outbound = [item for item in journal if str(item.get("type") or "") == "artifact_outbound"]
    assert outbound[-1]["message"] == long_message
    assert outbound[-1]["summary_preview"].endswith("…")

    outbox = read_jsonl(temp_home / "logs" / "connectors" / "local" / "outbox.jsonl")
    assert long_tail in str(outbox[-1].get("message") or "")


def test_failed_connector_delivery_does_not_refresh_visible_interaction_timestamp(temp_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("failed delivery freshness quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.set_binding_sources(quest["quest_id"], ["qq:direct:test-user"])
    baseline_ts = "2026-03-28T00:00:00+00:00"
    quest_service.update_runtime_state(
        quest_root=quest_root,
        last_artifact_interact_at=baseline_ts,
    )

    monkeypatch.setattr(
        artifact,
        "_deliver_to_channel",
        lambda channel_name, payload, connectors=None: {"ok": False, "queued": False, "message": "failed"},
    )

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="老师，我这里尝试发一条会失败的 connector 更新。",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"
    runtime_state = read_json(quest_root / ".ds" / "runtime_state.json", {})
    assert runtime_state["last_artifact_interact_at"] == baseline_ts


def test_get_quest_state_and_global_status_expose_continuation_state(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("global status quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    quest_service.update_settings(quest["quest_id"], active_anchor="finalize")
    quest_service.set_continuation_state(
        quest_root,
        policy="wait_for_user_or_resume",
        anchor="decision",
        reason="bundle_delivered",
    )

    state = artifact.get_quest_state(quest_root, detail="summary")
    assert state["ok"] is True
    assert state["quest_state"]["continuation_policy"] == "wait_for_user_or_resume"
    assert state["quest_state"]["continuation_anchor"] == "decision"
    assert state["quest_state"]["continuation_reason"] == "bundle_delivered"

    global_status = artifact.get_global_status(quest_root, detail="brief", locale="zh")
    assert global_status["ok"] is True
    assert global_status["global_status"]["continuation_policy"] == "wait_for_user_or_resume"
    assert global_status["global_status"]["current_stage"] == "finalize"
    assert "停驻" in global_status["global_status"]["summary_text"]


def test_answer_interaction_is_not_suppressed_like_progress(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("answer interaction quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = artifact.interact(
        quest_root,
        kind="answer",
        message="现在论文已经可交付，不需要再等新的主实验。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )
    second = artifact.interact(
        quest_root,
        kind="answer",
        message="现在论文已经可交付，不需要再等新的主实验。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert first["artifact_id"] != second["artifact_id"]

    journal = read_jsonl(quest_root / ".ds" / "interaction_journal.jsonl")
    outbound = [item for item in journal if str(item.get("type") or "") == "artifact_outbound"]
    assert len(outbound) == 2
    assert all(str(item.get("kind") or "") == "answer" for item in outbound)


def test_answer_local_fallback_reuses_previous_threaded_answer_in_same_turn(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("answer fallback dedupe quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = artifact.interact(
        quest_root,
        kind="answer",
        message="你好，这里再做一次流式回复测试。",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )
    second = artifact.interact(
        quest_root,
        kind="answer",
        message="你好，这里再做一次流式回复测试。",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )

    assert first["status"] == "ok"
    assert second["status"] == "suppressed_duplicate"
    assert second["artifact_id"] == first["artifact_id"]

    journal = read_jsonl(quest_root / ".ds" / "interaction_journal.jsonl")
    outbound = [item for item in journal if str(item.get("type") or "") == "artifact_outbound"]
    assert len(outbound) == 1
    assert outbound[0]["deliver_to_bound_conversations"] is True


def test_answer_interaction_delivers_through_bound_qq_connector(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    connectors = manager.load_named("connectors")
    connectors["qq"]["enabled"] = True
    connectors["qq"]["app_id"] = "1903299925"
    connectors["qq"]["app_secret"] = "qq-secret"
    connectors["_routing"]["artifact_delivery_policy"] = "primary_only"
    write_yaml(manager.path_for("connectors"), connectors)

    captured: list[dict] = []

    def fake_qq_deliver(_self, payload, _config):  # noqa: ANN001
        captured.append(dict(payload))
        return {"ok": True, "transport": "qq-http"}

    monkeypatch.setattr("deepscientist.bridges.connectors.QQConnectorBridge.deliver", fake_qq_deliver)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("answer connector quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    quest_service.bind_source(quest["quest_id"], "qq:direct:qq-user-answer")

    result = artifact.interact(
        quest_root,
        kind="answer",
        message="现在论文已经可交付，当前没有新的主实验阻塞。",
        deliver_to_bound_conversations=True,
        include_recent_inbound_messages=False,
    )

    assert result["status"] == "ok"
    assert result["delivery_targets"] == ["qq:direct:qq-user-answer"]
    assert captured
    assert captured[-1]["kind"] == "answer"
    assert captured[-1]["text"] == "现在论文已经可交付，当前没有新的主实验阻塞。"

    outbox = read_jsonl(temp_home / "logs" / "connectors" / "qq" / "outbox.jsonl")
    assert outbox
    assert outbox[-1]["kind"] == "answer"
    assert outbox[-1]["text"] == "现在论文已经可交付，当前没有新的主实验阻塞。"


def test_refresh_method_scoreboard_writes_status_files_and_incumbent(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("method scoreboard quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root, baseline_id="scoreboard-baseline")
    line = artifact.submit_idea(
        quest_root,
        mode="create",
        title="Scoreboard line",
        problem="Need a canonical scoreboard entry.",
        hypothesis="A verified run should appear as the incumbent.",
        mechanism="Use the existing artifact surfaces to derive one quest-wide line ledger.",
        next_target="experiment",
        decision_reason="Open the line for scoreboard testing.",
    )
    artifact.record(
        quest_root,
        {
            "kind": "run",
            "status": "completed",
            "run_id": "scoreboard-main-001",
            "run_kind": "main_experiment",
            "idea_id": line["idea_id"],
            "branch": line["branch"],
            "summary": "Main run finished for scoreboard testing.",
        },
        workspace_root=Path(line["worktree_root"]),
    )

    result = artifact.refresh_method_scoreboard(quest_root)
    assert result["ok"] is True
    assert Path(result["json_path"]).exists()
    assert Path(result["md_path"]).exists()
    scoreboard = read_json(Path(result["json_path"]), {})
    assert scoreboard["entry_count"] >= 1
    assert scoreboard["incumbent_title"] == "Scoreboard line"
    assert any(item.get("status") == "main_verified" for item in scoreboard["entries"])


def test_semantically_equivalent_report_is_suppressed(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("semantic report dedupe quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = artifact.record(
        quest_root,
        {
            "kind": "report",
            "stage": "finalize",
            "report_type": "checkpoint",
            "summary": "Finalize checkpoint remains unchanged.",
            "reason": "No new blocker or route change.",
        },
    )
    second = artifact.record(
        quest_root,
        {
            "kind": "report",
            "stage": "finalize",
            "report_type": "checkpoint",
            "summary": "Finalize checkpoint remains unchanged.",
            "reason": "No new blocker or route change.",
        },
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["status"] == "semantically_equivalent"
    assert second["artifact_id"] == first["artifact_id"]

    report_files = list((quest_root / "artifacts" / "reports").glob("*.json"))
    assert len(report_files) == 1


def test_semantically_equivalent_decision_is_suppressed(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("semantic decision dedupe quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    first = artifact.record(
        quest_root,
        {
            "kind": "decision",
            "stage": "finalize",
            "verdict": "continue",
            "action": "continue",
            "reason": "Continue later from the same checkpoint.",
            "summary": "Route unchanged.",
        },
    )
    second = artifact.record(
        quest_root,
        {
            "kind": "decision",
            "stage": "finalize",
            "verdict": "continue",
            "action": "continue",
            "reason": "Continue later from the same checkpoint.",
            "summary": "Route unchanged.",
        },
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["status"] == "semantically_equivalent"
    assert second["artifact_id"] == first["artifact_id"]

    decision_files = list((quest_root / "artifacts" / "decisions").glob("*.json"))
    assert len(decision_files) == 1


def test_artifact_interact_default_agent_instruction_respects_english_locale(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    manager = ConfigManager(temp_home)
    manager.ensure_files()
    config = manager.load_named("config")
    config["default_locale"] = "en-US"
    write_yaml(manager.path_for("config"), config)

    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("english fallback instruction quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    result = artifact.interact(
        quest_root,
        kind="progress",
        message="Still auditing.",
        deliver_to_bound_conversations=False,
        include_recent_inbound_messages=False,
    )

    assert result["agent_instruction"] == "No new user message has arrived. Continue the task according to the user's requirements."


def test_activate_branch_preserves_head_and_redirects_main_run(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("activate branch quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root)
    parent = artifact.submit_idea(
        quest_root,
        title="Parent route",
        problem="Need one older branch worth revisiting.",
        hypothesis="This branch should stay reusable after a newer head appears.",
        mechanism="Create one durable branch with a recorded main result.",
        expected_gain="A stable revisit target.",
        decision_reason="Promote the first durable route.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="run-parent-1",
        title="Parent main run",
        hypothesis="The parent route is promising enough.",
        setup="Use the standard configuration.",
        execution="Ran the main experiment.",
        results="The result is promising but may need more work later.",
        conclusion="Keep this branch available for future follow-up.",
        metric_rows=[{"metric_id": "acc", "value": 0.84}],
        evidence_paths=["experiments/main/run-parent-1/result.json"],
    )
    head = artifact.submit_idea(
        quest_root,
        title="Newer head route",
        problem="Create a newer head branch after the first result.",
        hypothesis="The newer route should become head without destroying revisit support.",
        mechanism="Create one more accepted idea branch.",
        expected_gain="A newer durable head.",
        decision_reason="Advance the frontier while keeping the older route.",
    )

    activated = artifact.activate_branch(quest_root, branch=parent["branch"])

    assert activated["ok"] is True
    assert activated["branch"] == parent["branch"]
    assert activated["worktree_root"] == parent["worktree_root"]
    assert activated["idea_id"] == parent["idea_id"]
    assert activated["next_anchor"] == "decision"
    assert activated["promote_to_head"] is False
    assert activated["interaction"]["delivered"] is True
    assert activated["interaction"]["delivery_targets"] == ["local:default"]
    assert activated["interaction"]["normalized_attachments"][0]["kind"] == "branch_activation"

    rerun = artifact.record_main_experiment(
        quest_root,
        run_id="run-parent-2",
        title="Reactivated parent run",
        hypothesis="The reactivated branch still owns the next result.",
        setup="Use the same branch-local workspace.",
        execution="Ran another main experiment after reactivation.",
        results="The follow-up run stayed on the activated branch.",
        conclusion="The branch activation redirect worked.",
        metric_rows=[{"metric_id": "acc", "value": 0.845}],
        evidence_paths=["experiments/main/run-parent-2/result.json"],
    )

    result_payload = read_json(Path(rerun["result_json_path"]), {})
    assert result_payload["branch"] == "run/run-parent-2"
    assert result_payload["parent_branch"] == parent["branch"]
    assert Path(rerun["result_json_path"]).is_relative_to(Path(parent["worktree_root"]))
    final_state = quest_service.read_research_state(quest_root)
    assert final_state["current_workspace_branch"] == "run/run-parent-2"
    assert final_state["research_head_branch"] == "run/run-parent-2"
    assert final_state["active_idea_id"] == parent["idea_id"]


def test_analysis_campaign_uses_current_workspace_parent_and_returns_there(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("current workspace analysis parent quest")
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)

    _confirm_local_baseline(artifact, quest_root)
    parent = artifact.submit_idea(
        quest_root,
        title="Parent route",
        problem="Need a durable parent node.",
        hypothesis="The parent route is promising enough for follow-up evidence.",
        mechanism="Establish the first durable branch.",
        expected_gain="A stable branch to analyze.",
        decision_reason="Promote the first route.",
    )
    artifact.record_main_experiment(
        quest_root,
        run_id="run-parent",
        title="Parent run",
        hypothesis="The parent route works.",
        setup="Use the standard configuration.",
        execution="Ran the main training and evaluation flow.",
        results="The run is promising and needs one extra follow-up experiment.",
        conclusion="Use this result as the parent node for a follow-up branch.",
        metrics_summary={"acc": 0.84},
        metric_rows=[{"metric_id": "acc", "value": 0.84}],
        evidence_paths=["experiments/main/run-parent/result.json"],
    )
    head = artifact.submit_idea(
        quest_root,
        title="New head route",
        problem="A newer route now exists.",
        hypothesis="This becomes the latest head branch.",
        mechanism="Branch a new route after the parent result.",
        expected_gain="A distinct newer head.",
        decision_reason="Keep exploring a different route.",
    )

    activated = artifact.activate_branch(quest_root, branch=parent["branch"])
    assert activated["branch"] == parent["branch"]
    assert activated["next_anchor"] == "decision"

    campaign = artifact.create_analysis_campaign(
        quest_root,
        campaign_title="Single extra experiment",
        campaign_goal="Run one follow-up experiment from the previously selected node.",
        slices=[
            {
                "slice_id": "follow-up",
                "title": "Follow-up experiment",
                "goal": "Run the extra experiment as a true child branch.",
                "required_changes": "Apply only the follow-up change.",
                "metric_contract": "Use the same baseline comparison contract.",
            }
        ],
    )

    assert campaign["parent_branch"] == "run/run-parent"
    assert campaign["parent_worktree_root"] == parent["worktree_root"]
    assert campaign["slices"][0]["branch"].startswith(f"analysis/{parent['idea_id']}/")

    completed = artifact.record_analysis_slice(
        quest_root,
        campaign_id=campaign["campaign_id"],
        slice_id="follow-up",
        setup="Apply the follow-up change only.",
        execution="Ran the extra experiment fully.",
        results="The extra experiment finished cleanly.",
        metric_rows=[{"name": "acc", "value": 0.845}],
        evidence_paths=["experiments/analysis/follow-up/result.json"],
    )

    assert completed["completed"] is True
    assert completed["returned_to_branch"] == "run/run-parent"
    final_state = quest_service.read_research_state(quest_root)
    assert final_state["current_workspace_branch"].startswith("paper/")
    assert final_state["workspace_mode"] == "paper"
    assert final_state["research_head_branch"] == head["branch"]
    assert final_state["active_idea_id"] == parent["idea_id"]
