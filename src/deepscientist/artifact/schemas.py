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
    "distill_review": "distill_reviews",
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

DISTILL_CARD_ACTIONS = {"new", "patch"}
DISTILL_CARD_SCOPES = {"global", "quest"}


def validate_artifact_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    kind = payload.get("kind")
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
    if kind == "distill_review":
        reviewed = payload.get("reviewed_run_ids") or []
        if not isinstance(reviewed, list) or not reviewed:
            errors.append("distill_review artifact requires non-empty `reviewed_run_ids`.")
            return errors
        cards = payload.get("cards_written")
        if cards is None or not isinstance(cards, list):
            errors.append("distill_review artifact requires `cards_written` (may be empty list).")
            return errors
        if not cards and not str(payload.get("reason_if_empty") or "").strip():
            errors.append(
                "distill_review with empty `cards_written` requires `reason_if_empty`."
            )
        reviewed_set = set(str(rid) for rid in reviewed)
        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"distill_review.cards_written[{idx}] must be an object.")
                continue
            target = str(card.get("target_run_id") or "")
            if target not in reviewed_set:
                errors.append(
                    f"distill_review.cards_written[{idx}].target_run_id `{target}` "
                    f"must be present in `reviewed_run_ids`."
                )
            action = str(card.get("action") or "")
            if action not in DISTILL_CARD_ACTIONS:
                errors.append(
                    f"distill_review.cards_written[{idx}].action `{action}` "
                    f"must be one of {sorted(DISTILL_CARD_ACTIONS)}."
                )
            scope = str(card.get("scope") or "")
            if scope not in DISTILL_CARD_SCOPES:
                errors.append(
                    f"distill_review.cards_written[{idx}].scope `{scope}` "
                    f"must be one of {sorted(DISTILL_CARD_SCOPES)}."
                )
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
    if kind == "distill_review":
        return "Distill review recorded. The finalize gate cursor advances; resume the original write/finalize route."
    return "Artifact stored. Refresh quest status and continue from the latest durable state."
