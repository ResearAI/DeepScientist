from __future__ import annotations

from pathlib import Path

from deepscientist.artifact import ArtifactService
from deepscientist.home import ensure_home_layout
from deepscientist.quest import QuestService
from deepscientist.shared import append_jsonl, ensure_dir, utc_now, write_json


def test_node_traces_materialize_branch_stage_and_event_views(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    quest = service.create("trace materialization quest", quest_id="trace-quest")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    run_id = "run-idea-1"
    run_root = ensure_dir(quest_root / ".ds" / "runs" / run_id)
    history_root = ensure_dir(quest_root / ".ds" / "codex_history" / run_id)
    write_json(
        history_root / "meta.json",
        {
            "run_id": run_id,
            "skill_id": "idea",
            "summary": "Generated idea branch plan.",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "history_root": str(history_root),
            "run_root": str(run_root),
        },
    )
    append_jsonl(
        history_root / "events.jsonl",
        {
            "timestamp": utc_now(),
            "event": {
                "type": "item.started",
                "item": {
                    "type": "web_search",
                    "id": "call-1",
                    "query": "arxiv graph reasoning",
                },
            },
        },
    )
    append_jsonl(
        history_root / "events.jsonl",
        {
            "timestamp": utc_now(),
            "event": {
                "type": "reasoning",
                "item": {
                    "type": "reasoning",
                    "text": "Compare prior graph reasoning methods before drafting the idea.",
                },
            },
        },
    )

    artifact_path = ensure_dir(quest_root / "artifacts" / "reports") / "idea-report.json"
    write_json(
        artifact_path,
        {
            "artifact_id": "idea-report",
            "kind": "report",
            "branch": "idea/graph-reasoning",
            "run_id": run_id,
            "summary": "Idea report saved.",
            "updated_at": utc_now(),
        },
    )

    payload = service.node_traces(quest_id)

    assert payload["quest_id"] == quest_id
    assert Path(payload["materialized_path"]).exists()

    branch_trace = next(
        item
        for item in payload["items"]
        if item["selection_type"] == "branch_node" and item["selection_ref"] == "idea/graph-reasoning"
    )
    assert branch_trace["counts"]["actions"] >= 2

    stage_trace = next(
        item
        for item in payload["items"]
        if item["selection_type"] == "stage_node"
        and item["selection_ref"] == "stage:idea/graph-reasoning:idea"
    )
    assert stage_trace["stage_key"] == "idea"

    event_trace = next(item for item in payload["items"] if item["selection_type"] == "event_node")
    detail = service.node_trace(
        quest_id,
        event_trace["selection_ref"],
        selection_type="event_node",
    )
    assert detail["trace"]["selection_ref"] == event_trace["selection_ref"]
    assert detail["trace"]["actions"]


def test_node_traces_include_worktree_artifacts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    quest = service.create("trace worktree quest", quest_id="trace-worktree")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    worktree_root = ensure_dir(quest_root / ".ds" / "worktrees" / "idea-adapter")
    artifact_path = ensure_dir(worktree_root / "artifacts" / "runs") / "analysis-run.json"
    write_json(
        artifact_path,
        {
            "artifact_id": "analysis-run",
            "kind": "run",
            "branch": "analysis/idea-1/slice-a",
            "run_id": "analysis-run-1",
            "run_kind": "analysis.ablation",
            "summary": "Analysis slice recorded from worktree.",
            "worktree_rel_path": ".ds/worktrees/idea-adapter",
            "updated_at": utc_now(),
        },
    )

    payload = service.node_traces(quest_id)
    branch_trace = next(
        item
        for item in payload["items"]
        if item["selection_type"] == "branch_node" and item["selection_ref"] == "analysis/idea-1/slice-a"
    )
    assert branch_trace["counts"]["artifacts"] >= 1


def test_node_traces_infer_stage_from_branch_prefix_for_generic_progress_artifacts(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    quest = service.create("trace branch prefix inference quest", quest_id="trace-prefix")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    progress_root = ensure_dir(quest_root / "artifacts" / "progress")
    write_json(
        progress_root / "idea-progress.json",
        {
            "artifact_id": "idea-progress",
            "kind": "progress",
            "branch": "idea/router-idea",
            "summary": "Idea branch progress.",
            "status": "active",
            "updated_at": utc_now(),
        },
    )
    write_json(
        progress_root / "run-progress.json",
        {
            "artifact_id": "run-progress",
            "kind": "progress",
            "branch": "run/router-main",
            "summary": "Experiment branch progress.",
            "status": "active",
            "updated_at": utc_now(),
        },
    )
    write_json(
        progress_root / "analysis-progress.json",
        {
            "artifact_id": "analysis-progress",
            "kind": "progress",
            "branch": "analysis/router-main/slice-a",
            "summary": "Analysis branch progress.",
            "status": "active",
            "updated_at": utc_now(),
        },
    )

    payload = service.node_traces(quest_id)
    selection_refs = {
        item["selection_ref"]
        for item in payload["items"]
        if item["selection_type"] == "stage_node"
    }

    assert "stage:idea/router-idea:idea" in selection_refs
    assert "stage:run/router-main:experiment" in selection_refs
    assert "stage:analysis/router-main/slice-a:analysis" in selection_refs


def test_node_traces_expose_artifact_payload_commit_and_changed_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    quest = service.create("trace payload detail quest", quest_id="trace-payload")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    run_id = "run-trace-payload"
    history_root = ensure_dir(quest_root / ".ds" / "codex_history" / run_id)
    run_root = ensure_dir(quest_root / ".ds" / "runs" / run_id)
    write_json(
        history_root / "meta.json",
        {
            "run_id": run_id,
            "skill_id": "experiment",
            "summary": "Record the main experiment and its changed files.",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "history_root": str(history_root),
            "run_root": str(run_root),
        },
    )
    append_jsonl(
        history_root / "events.jsonl",
        {
            "timestamp": utc_now(),
            "event": {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "id": "cmd-1",
                    "status": "completed",
                    "command": "pytest tests/test_example.py",
                    "output_text": "1 passed",
                },
            },
        },
    )

    artifact_path = ensure_dir(quest_root / "artifacts" / "runs") / "main-trace.json"
    write_json(
        artifact_path,
        {
            "artifact_id": "main-trace",
            "kind": "run",
            "branch": "run/trace-main",
            "run_id": run_id,
            "run_kind": "experiment",
            "summary": "Main experiment recorded with durable files.",
            "head_commit": "abc123def456",
            "paths": {
                "run_md": "experiments/main/trace-main/RUN.md",
                "result_json": "experiments/main/trace-main/RESULT.json",
            },
            "details": {
                "title": "Trace main run",
                "evaluation_summary": {"takeaway": "Inline payload should survive into node traces."},
            },
            "files_changed": ["src/model.py", "configs/train.yaml"],
            "updated_at": utc_now(),
        },
    )
    write_json(
        run_root / "artifact.json",
        {
            "ok": True,
            "record": {
                "run_id": run_id,
                "branch": "run/trace-main",
                "head_commit": "base123",
                "paths": {
                    "run_md": "experiments/main/trace-main/RUN.md",
                    "result_json": "experiments/main/trace-main/RESULT.json",
                },
                "files_changed": ["src/model.py", "configs/train.yaml"],
            },
            "checkpoint": {
                "head": "head789",
            },
        },
    )

    payload = service.node_traces(quest_id)
    stage_trace = next(
        item
        for item in payload["items"]
        if item["selection_type"] == "stage_node"
        and item["selection_ref"] == "stage:run/trace-main:experiment"
    )

    assert stage_trace["artifact_id"] == "main-trace"
    assert stage_trace["artifact_kind"] == "run"
    assert stage_trace["head_commit"] == "abc123def456"
    assert stage_trace["payload_json"]["paths"]["run_md"] == "experiments/main/trace-main/RUN.md"
    assert stage_trace["details_json"]["title"] == "Trace main run"
    assert stage_trace["paths_map"]["result_json"] == "experiments/main/trace-main/RESULT.json"
    assert stage_trace["changed_files"] == ["src/model.py", "configs/train.yaml"]

    detail = service.node_trace(quest_id, "stage:run/trace-main:experiment", selection_type="stage_node")
    assert detail["trace"]["actions"]
    artifact_action = next(action for action in reversed(detail["trace"]["actions"]) if action.get("artifact_id") == "main-trace")
    assert artifact_action["artifact_id"] == "main-trace"
    assert artifact_action["checkpoint_json"]["head"] == "head789"


def test_node_traces_expose_science_stage_and_evidence_paths(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    service = QuestService(temp_home)
    quest = service.create("trace science artifact quest", quest_id="trace-science")
    quest_id = quest["quest_id"]
    quest_root = Path(quest["quest_root"])

    ArtifactService(temp_home).science(
        quest_root,
        action="record_node",
        node_type="science.computational_run",
        node_id="run_water_hf_sto3g",
        title="Water HF/STO-3G energy",
        summary="Computed water molecule total energy.",
        status="success",
        input_paths=["simulations/inputs/water.py"],
        log_paths=["simulations/logs/water.out"],
        output_paths=["simulations/outputs/water/energy.json"],
    )

    payload = service.node_traces(quest_id)
    stage_trace = next(
        item
        for item in payload["items"]
        if item["selection_type"] == "stage_node" and item["selection_ref"] == "stage:main:science"
    )

    assert stage_trace["stage_key"] == "science"
    assert stage_trace["artifact_kind"] == "science.computational_run"
    assert stage_trace["payload_json"]["node_id"] == "run_water_hf_sto3g"
    assert stage_trace["paths_map"]["input_1"] == "simulations/inputs/water.py"
    assert stage_trace["paths_map"]["log_1"] == "simulations/logs/water.out"
    assert "simulations/outputs/water/energy.json" in stage_trace["changed_files"]
