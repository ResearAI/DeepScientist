from __future__ import annotations

ARTIFACT_DIRS = {
    "baseline": "baselines",
    "idea": "ideas",
    "decision": "decisions",
    "progress": "progress",
    "answer": "answers",
    "milestone": "milestones",
    "run": "runs",
    "report": "reports",
    "approval": "approvals",
    "graph": "graphs",
}

SCIENCE_ARTIFACT_DIR = "science"

SCIENCE_NODE_TYPES = {
    "science.package_check",
    "science.computational_run",
    "science.dataset_analysis",
    "science.parameter_sweep",
    "science.validation_result",
    "science.claim",
}

SCIENCE_STATUSES = {
    "planned",
    "ready",
    "queued",
    "running",
    "success",
    "failed",
    "blocked",
    "warning",
    "passed",
    "active",
    "superseded",
}

SCIENCE_CLAIM_TYPES = {
    "computed",
    "parsed",
    "digitized",
    "hypothesis",
}

SCIENCE_ACTIONS = {
    "record_node",
    "update_node",
    "link_nodes",
    "status",
    "focus",
}

DECISION_ACTIONS = {
    "continue",
    "launch_experiment",
    "launch_analysis_campaign",
    "branch",
    "prepare_branch",
    "activate_branch",
    "reuse_baseline",
    "attach_baseline",
    "publish_baseline",
    "waive_baseline",
    "iterate",
    "reset",
    "stop",
    "write",
    "finalize",
    "request_user_decision",
}


def is_science_kind(kind: str | None) -> bool:
    return str(kind or "").strip() in SCIENCE_NODE_TYPES


def artifact_dir_for_kind(kind: str) -> str:
    if is_science_kind(kind):
        return SCIENCE_ARTIFACT_DIR
    return ARTIFACT_DIRS[kind]


def _has_any_path(payload: dict, fields: tuple[str, ...]) -> bool:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, list) and any(str(item or "").strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _has_any_related_node(payload: dict) -> bool:
    for field in ("parent_node_ids", "related_node_ids"):
        value = payload.get(field)
        if isinstance(value, list) and any(str(item or "").strip() for item in value):
            return True
    return False


def validate_science_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    kind = str(payload.get("kind") or payload.get("node_type") or "").strip()
    if kind not in SCIENCE_NODE_TYPES:
        errors.append(f"Unknown science node type: {kind}")
        return errors
    status = str(payload.get("status") or "").strip()
    if status and status not in SCIENCE_STATUSES:
        errors.append(f"Unknown science status: {status}")
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        errors.append("Science artifact requires `node_id`.")
    action = str(payload.get("action") or "record_node").strip() or "record_node"
    if action == "link_nodes":
        if not _has_any_related_node(payload):
            errors.append("Science link_nodes requires related_node_ids or parent_node_ids.")
        return errors
    if kind == "science.claim":
        claim_type = str(payload.get("claim_type") or "").strip()
        if not claim_type and action == "record_node":
            errors.append("Science claim requires `claim_type`.")
        elif claim_type and claim_type not in SCIENCE_CLAIM_TYPES:
            errors.append(f"Unknown science claim_type: {claim_type}")
        if claim_type == "computed" and not (
            _has_any_path(payload, ("evidence_paths", "validation_paths", "output_paths", "log_paths"))
            or _has_any_related_node(payload)
        ):
            errors.append("Computed science claim requires evidence_paths, validation_paths, output/log paths, or related_node_ids.")
    if kind == "science.validation_result" and not _has_any_related_node(payload):
        errors.append("Science validation_result must reference a related or parent run, analysis, or sweep node.")
    if kind == "science.computational_run" and status == "success" and not _has_any_path(
        payload,
        ("input_paths", "log_paths", "output_paths", "evidence_paths"),
    ):
        errors.append("Successful computational_run requires at least one input, log, output, or evidence path.")
    if kind == "science.package_check" and status == "passed" and not _has_any_path(
        payload,
        ("evidence_paths", "log_paths", "output_paths", "validation_paths"),
    ):
        errors.append("Passed package_check requires environment-check evidence.")
    return errors


def validate_artifact_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    kind = payload.get("kind")
    if is_science_kind(kind):
        return validate_science_payload(payload)
    if kind not in ARTIFACT_DIRS:
        errors.append(f"Unknown artifact kind: {kind}")
        return errors
    if kind == "decision":
        for field in ("verdict", "action", "reason"):
            if not payload.get(field):
                errors.append(f"Decision artifact requires `{field}`.")
        action = payload.get("action")
        if action and action not in DECISION_ACTIONS:
            errors.append(f"Unknown decision action: {action}")
    if kind == "run" and not payload.get("run_kind"):
        errors.append("Run artifact requires `run_kind`.")
    return errors


def guidance_for_kind(kind: str) -> str:
    if kind == "baseline":
        return "Baseline recorded. You can now reuse it or start idea selection."
    if kind == "idea":
        return "Idea captured. Evaluate whether it merits a decision and an experiment branch."
    if kind == "decision":
        return "Decision recorded. Follow the chosen action and notify the user with the reason."
    if kind == "run":
        return "Run recorded. Compare metrics, then decide whether to continue, branch, or stop."
    if kind == "milestone":
        return "Milestone recorded. Send a concise progress update to the active surface."
    if kind == "answer":
        return "Answer stored. This was a direct user-facing reply, not a long-running progress checkpoint."
    if kind == "report":
        return "Report saved. Use it to update SUMMARY.md and the next planning step."
    if kind == "approval":
        return "Approval captured. The quest may proceed with the approved step."
    if kind == "graph":
        return "Graph exported. Share the preview or attach it to a status response."
    if is_science_kind(kind):
        return "Science evidence recorded. Continue execution through bash_exec and keep claims linked to durable evidence paths."
    return "Artifact stored. Refresh quest status and continue from the latest durable state."
