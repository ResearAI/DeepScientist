"""Experience distillation helpers.

Experience is a `subtype` of the `knowledge` memory kind — not a new kind.
Frontmatter schema enforced here:

    subtype: experience
    claim: <one-sentence mechanism-bearing claim>
    mechanism: <why the claim plausibly holds>
    conditions: [<scoping tags>, ...]
    confidence: 0.0..1.0
    lineage: [{quest, run, direction, note}, ...]

Cross-quest patches may append lineage and downgrade confidence only;
the `claim` text is locked once the card spans more than one quest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


_REQUIRED_LINEAGE_KEYS = ("quest", "run", "direction", "note")


def build_experience_metadata(
    *,
    claim: str,
    mechanism: str,
    conditions: list[str],
    confidence: float,
    lineage: list[dict[str, str]],
) -> dict[str, Any]:
    """Construct a well-formed experience frontmatter dict."""
    return {
        "subtype": "experience",
        "claim": str(claim).strip(),
        "mechanism": str(mechanism).strip(),
        "conditions": [str(item).strip() for item in (conditions or []) if str(item).strip()],
        "confidence": float(confidence),
        "lineage": [_canonical_lineage_entry(item) for item in (lineage or [])],
    }


def _canonical_lineage_entry(entry: dict[str, Any]) -> dict[str, str]:
    return {key: str(entry.get(key) or "").strip() for key in _REQUIRED_LINEAGE_KEYS}


def validate_experience_metadata(meta: dict[str, Any]) -> None:
    """Raise ValueError if the frontmatter does not satisfy the experience contract."""
    if str(meta.get("subtype") or "").strip() != "experience":
        raise ValueError("Experience frontmatter must have subtype: experience")
    for field in ("claim", "mechanism"):
        if not str(meta.get(field) or "").strip():
            raise ValueError(f"Experience frontmatter missing required field `{field}`")
    conditions = meta.get("conditions") or []
    if not isinstance(conditions, list) or not any(str(item).strip() for item in conditions):
        raise ValueError("Experience frontmatter `conditions` must be a non-empty list of scoping tags")
    confidence = meta.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise ValueError("Experience frontmatter `confidence` must be a float in [0.0, 1.0]")
    lineage = meta.get("lineage") or []
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("Experience frontmatter `lineage` must be a non-empty list")
    for idx, entry in enumerate(lineage):
        if not isinstance(entry, dict):
            raise ValueError(f"Experience lineage[{idx}] must be a dict")
        for key in ("quest", "run"):
            if not str(entry.get(key) or "").strip():
                raise ValueError(f"Experience lineage[{idx}] missing required key `{key}`")


def validate_cross_quest_patch(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    patching_quest: str,
) -> None:
    """Enforce cross-quest patch permissions (prompt-level contract, enforced in tests/CLI).

    Same quest -> free edit. Cross-quest -> claim locked, confidence non-increasing,
    lineage may only grow.
    """
    validate_experience_metadata(after)
    owning_quests = {str(entry.get("quest") or "").strip() for entry in (before.get("lineage") or [])}
    is_same_quest = owning_quests == {patching_quest} or not owning_quests
    if is_same_quest:
        return
    if str(before.get("claim") or "").strip() != str(after.get("claim") or "").strip():
        raise ValueError("Cross-quest patch may not change `claim` text; claim is locked across quests")
    if float(after.get("confidence", 0.0)) > float(before.get("confidence", 0.0)):
        raise ValueError("Cross-quest patch may only downgrade `confidence`, not increase it")
    before_lineage = before.get("lineage") or []
    after_lineage = after.get("lineage") or []
    if len(after_lineage) < len(before_lineage):
        raise ValueError("Cross-quest patch may not shrink lineage")
    if after_lineage[: len(before_lineage)] != before_lineage:
        raise ValueError("Cross-quest patch may not rewrite existing lineage entries, only append")


def coerce_distill_mode(value: Any, *, field_name: str = "experience_distill") -> dict[str, str]:
    """Normalize user-supplied value into {"mode": "on"|"off"}.

    Accepts:
      - bool True/False
      - string "on"/"off" (case-insensitive)
      - dict {"mode": "on"|"off"}
    Anything else collapses to {"mode": "off"}.
    """
    if value is True:
        return {"mode": "on"}
    if value is False or value is None:
        return {"mode": "off"}
    if isinstance(value, str):
        return {"mode": "on" if value.strip().lower() == "on" else "off"}
    if isinstance(value, dict):
        mode_val = value.get("mode")
        if mode_val is True:
            return {"mode": "on"}
        if mode_val is False:
            return {"mode": "off"}
        raw = str(mode_val or "").strip().lower()
        return {"mode": "on" if raw == "on" else "off"}
    return {"mode": "off"}


def read_distill_mode(quest_root: Path | None) -> dict[str, str]:
    """Read `startup_contract.experience_distill` from quest.yaml; return normalized dict."""
    if quest_root is None:
        return {"mode": "off"}
    quest_yaml = quest_root / "quest.yaml"
    if not quest_yaml.exists():
        return {"mode": "off"}
    try:
        from ..shared import require_yaml
        require_yaml()
        import yaml  # type: ignore
        payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mode": "off"}
    if not isinstance(payload, dict):
        return {"mode": "off"}
    contract = payload.get("startup_contract") or {}
    if not isinstance(contract, dict):
        return {"mode": "off"}
    return coerce_distill_mode(contract.get("experience_distill"))


def is_distill_on(quest_root: Path | None) -> bool:
    return read_distill_mode(quest_root)["mode"] == "on"


def coerce_recall_priors_mode(value: Any, *, field_name: str = "recall_priors") -> dict[str, str]:
    """Normalize user-supplied value into {"mode": "on"|"off"} for recall_priors.

    Accepts: bool, "on"/"off" string, dict {"mode": ...}. Anything else collapses to off.
    """
    if value is True:
        return {"mode": "on"}
    if value is False or value is None:
        return {"mode": "off"}
    if isinstance(value, str):
        return {"mode": "on" if value.strip().lower() == "on" else "off"}
    if isinstance(value, dict):
        mode_val = value.get("mode")
        if mode_val is True:
            return {"mode": "on"}
        if mode_val is False:
            return {"mode": "off"}
        raw = str(mode_val or "").strip().lower()
        return {"mode": "on" if raw == "on" else "off"}
    return {"mode": "off"}


def read_recall_priors_mode(quest_root: Path | None) -> dict[str, str]:
    """Read `startup_contract.recall_priors` from quest.yaml; return normalized dict."""
    if quest_root is None:
        return {"mode": "off"}
    quest_yaml = quest_root / "quest.yaml"
    if not quest_yaml.exists():
        return {"mode": "off"}
    try:
        from ..shared import require_yaml
        require_yaml()
        import yaml  # type: ignore
        payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"mode": "off"}
    if not isinstance(payload, dict):
        return {"mode": "off"}
    contract = payload.get("startup_contract") or {}
    if not isinstance(contract, dict):
        return {"mode": "off"}
    return coerce_recall_priors_mode(contract.get("recall_priors"))


def is_recall_priors_on(quest_root: Path | None) -> bool:
    return read_recall_priors_mode(quest_root)["mode"] == "on"


def _is_analysis_slice_terminal(record: dict[str, Any]) -> bool:
    if str(record.get("kind") or "") != "run":
        return False
    run_kind = str(record.get("run_kind") or "")
    if run_kind != "analysis.slice":
        return False
    status = str(record.get("status") or "").strip().lower()
    if status not in {"completed", "success", "succeeded", "done"}:
        return False
    return True


def maybe_inject_distill_routing(
    quest_root: Path,
    record: dict[str, Any],
    guidance_vm: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """When distill is on and the record is a completed analysis-slice run,
    return a new guidance_vm recommending the `distill` companion skill.

    Otherwise return guidance_vm unchanged (same object identity).
    Never raises; callers should still wrap in try/except for defense.
    """
    if not is_distill_on(quest_root):
        return guidance_vm
    if not _is_analysis_slice_terminal(record):
        return guidance_vm
    base = dict(guidance_vm) if isinstance(guidance_vm, dict) else {}
    previous_skill = str(base.get("recommended_skill") or "").strip() or None
    previous_action = str(base.get("recommended_action") or "").strip() or None
    routes = list(base.get("alternative_routes") or []) if isinstance(base.get("alternative_routes"), list) else []
    if previous_skill and previous_skill != "distill":
        routes.append(
            {
                "recommended_skill": previous_skill,
                "recommended_action": previous_action or f"Fall back to `{previous_skill}` if nothing to distill.",
                "reason": "Original next step before distill redirect.",
            }
        )
    out = {
        **base,
        "recommended_skill": "distill",
        "recommended_action": "Inspect this analysis slice and distill reusable experience if warranted.",
        "previous_recommended_skill": previous_skill,
        "previous_recommended_action": previous_action,
        "alternative_routes": routes,
        "experience_distill": True,
        "source_artifact_id": str(record.get("artifact_id") or ""),
    }
    return out


def iter_analysis_slice_records(artifacts_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield full analysis-slice run records by reading the artifact index."""
    import json
    index_path = artifacts_dir / "_index.jsonl"
    if not index_path.exists():
        return
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("kind") != "run":
            continue
        record_path = Path(str(entry.get("path") or ""))
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _is_analysis_slice_terminal(record):
            yield record


DISTILL_CANDIDATE_RUN_KINDS: frozenset[str] = frozenset(
    {"analysis.slice", "main_experiment", "experiment"}
)


def _is_distill_candidate(record: dict[str, Any], allowed_kinds: frozenset[str]) -> bool:
    if str(record.get("kind") or "") != "run":
        return False
    if str(record.get("run_kind") or "") not in allowed_kinds:
        return False
    status = str(record.get("status") or "").strip().lower()
    return status in {"completed", "success", "succeeded", "done"}


def iter_distill_candidate_records(
    artifacts_dir: Path,
    *,
    run_kinds: frozenset[str] | set[str] | None = None,
) -> Iterable[dict[str, Any]]:
    """Yield completed run records eligible for distillation.

    Default kinds cover analysis.slice, main_experiment, and experiment.
    Pass `run_kinds` to narrow or widen the scope.
    """
    import json

    allowed = frozenset(run_kinds) if run_kinds else DISTILL_CANDIDATE_RUN_KINDS
    index_path = artifacts_dir / "_index.jsonl"
    if not index_path.exists():
        return
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("kind") != "run":
            continue
        record_path = Path(str(entry.get("path") or ""))
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _is_distill_candidate(record, allowed):
            yield record


def emit_experience_drafts(
    *,
    quest_id: str,
    records: list[dict[str, Any]] | Iterable[dict[str, Any]],
    drafts_root: Path,
) -> list[Path]:
    """Write one draft markdown per analysis-slice record.

    Each draft has experience frontmatter with lineage pre-filled and
    TODO placeholders for claim/mechanism/conditions/confidence. The
    human reviewer edits these and promotes the card to global memory.
    """
    slices = [r for r in records if _is_distill_candidate(r, DISTILL_CANDIDATE_RUN_KINDS)]
    quest_dir = drafts_root / quest_id
    quest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for record in slices:
        campaign_id = str(record.get("campaign_id") or "cmp").strip() or "cmp"
        slice_id = str(record.get("slice_id") or record.get("artifact_id") or "slice").strip() or "slice"
        run_id = str(record.get("run_id") or f"{campaign_id}:{slice_id}")
        title = str((record.get("details") or {}).get("title") or record.get("summary") or slice_id)
        body = _render_experience_draft(
            quest_id=quest_id,
            run_id=run_id,
            campaign_id=campaign_id,
            slice_id=slice_id,
            title=title,
            summary=str(record.get("summary") or ""),
        )
        path = quest_dir / f"{campaign_id}__{slice_id}.md"
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def _render_experience_draft(
    *,
    quest_id: str,
    run_id: str,
    campaign_id: str,
    slice_id: str,
    title: str,
    summary: str,
) -> str:
    return (
        "---\n"
        "subtype: experience\n"
        "claim: \"TODO: claim — one mechanism-bearing sentence.\"\n"
        "mechanism: \"TODO: mechanism — why this plausibly holds.\"\n"
        "conditions:\n"
        "  - \"TODO: at least one scoping tag\"\n"
        "confidence: 0.4\n"
        "lineage:\n"
        f"  - quest: {quest_id}\n"
        f"    run: {run_id}\n"
        f"    direction: {campaign_id}\n"
        f"    note: {json.dumps(str(title))}\n"
        "---\n"
        f"# Draft experience from {campaign_id}:{slice_id}\n\n"
        f"Source summary: {summary or '(empty)'}\n\n"
        "Write 3–8 lines of prose explaining the causal story. Delete this guidance\n"
        "block when you promote the card to global memory.\n"
    )


def read_distill_reviews(artifacts_dir: Path) -> list[dict[str, Any]]:
    import json
    index_path = artifacts_dir / "_index.jsonl"
    if not index_path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("kind") != "decision":
            continue
        record_path = Path(str(entry.get("path") or ""))
        if not record_path.exists():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if record.get("action") != "distill_review":
            continue
        out.append(record)
    return out


def collect_reviewed_run_ids(
    reviews: list[dict[str, Any]],
) -> tuple[set[str], str | None]:
    """Aggregate reviewed run ids and the latest review timestamp.

    Returns:
      (reviewed_set, cursor_run_created_at)
      cursor_run_created_at is the max ISO created_at across reviews, or None if absent.
    """
    reviewed_set: set[str] = set()
    cursor_run_created_at: str | None = None
    for rec in reviews:
        for rid in rec.get("reviewed_run_ids") or []:
            reviewed_set.add(str(rid))
        ts = str(rec.get("created_at") or "")
        if ts and (cursor_run_created_at is None or ts > cursor_run_created_at):
            cursor_run_created_at = ts
    return reviewed_set, cursor_run_created_at


def evaluate_distill_gate(
    quest_root: Path,
    artifacts_dir: Path,
) -> dict[str, Any] | None:
    """Return a gate payload if the agent should be routed to distill, else None.

    Returned dict shape:
      {
        "pending_distill_count": int,        # total candidates past the reviewed set
        "pending_distill_ids": list[str],    # first 5 candidate artifact_ids
        "cursor_run_created_at": str | None, # latest review timestamp, if any
      }
    """
    if not is_distill_on(quest_root):
        return None
    reviews = read_distill_reviews(artifacts_dir)
    reviewed_set, cursor_created_at = collect_reviewed_run_ids(reviews)
    candidates = [
        rec for rec in iter_distill_candidate_records(artifacts_dir)
        if str(rec.get("artifact_id") or "") not in reviewed_set
    ]
    if not candidates:
        return None
    ids = [str(rec.get("artifact_id") or "") for rec in candidates]
    return {
        "pending_distill_count": len(candidates),
        "pending_distill_ids": ids[:5],
        "cursor_run_created_at": cursor_created_at,
    }


def _quest_workspace_artifact_dirs(quest_root: Path) -> list[Path]:
    roots: list[Path] = [quest_root]
    worktrees_root = quest_root / ".ds" / "worktrees"
    if worktrees_root.exists():
        for path in sorted(worktrees_root.iterdir()):
            if path.is_dir():
                roots.append(path)
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        artifacts = root / "artifacts"
        if not artifacts.exists():
            continue
        key = str(artifacts.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(artifacts)
    return out


def evaluate_distill_gate_for_quest(quest_root: Path) -> dict[str, Any] | None:
    """Evaluate the distill gate across every artifacts dir owned by the quest.

    Closure entry points (`submit_paper_bundle`, `complete_quest`, prompt cues)
    fire outside `record(...)` and have no per-record `write_root` context, so
    they must look at every workspace's artifacts directory — the canonical
    `quest_root/artifacts` plus each `quest_root/.ds/worktrees/*/artifacts`.
    Candidates and reviews are deduped by `artifact_id`.
    """
    if not is_distill_on(quest_root):
        return None
    artifact_dirs = _quest_workspace_artifact_dirs(quest_root)
    if not artifact_dirs:
        return None
    reviewed_set: set[str] = set()
    cursor_created_at: str | None = None
    for artifacts_dir in artifact_dirs:
        reviews = read_distill_reviews(artifacts_dir)
        partial_reviewed, partial_cursor = collect_reviewed_run_ids(reviews)
        reviewed_set.update(partial_reviewed)
        if partial_cursor and (cursor_created_at is None or partial_cursor > cursor_created_at):
            cursor_created_at = partial_cursor
    candidates_by_id: dict[str, dict[str, Any]] = {}
    for artifacts_dir in artifact_dirs:
        for rec in iter_distill_candidate_records(artifacts_dir):
            rid = str(rec.get("artifact_id") or "")
            if not rid or rid in reviewed_set or rid in candidates_by_id:
                continue
            candidates_by_id[rid] = rec
    if not candidates_by_id:
        return None
    ids = list(candidates_by_id.keys())
    return {
        "pending_distill_count": len(ids),
        "pending_distill_ids": ids[:5],
        "cursor_run_created_at": cursor_created_at,
    }


_FINALIZE_GATE_ACTIONS: frozenset[str] = frozenset({"write", "finalize"})

_FINALIZE_GATE_INJECTED_KEYS: frozenset[str] = frozenset({
    "gate",
    "pending_distill_count",
    "pending_distill_ids",
    "cursor_run_created_at",
    "previous_recommended_skill",
    "previous_recommended_action",
    "experience_distill",
    "source_artifact_id",
})

def maybe_inject_distill_finalize_gate(
    quest_root: Path,
    artifacts_dir: Path,
    record: dict[str, Any],
    guidance_vm: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Pre-write/pre-finalize sweep.

    When the agent records `decision(action='write'|'finalize')` and the quest
    has completed runs not yet covered by any `distill_review`, swap the
    recommended_skill to `distill` and surface the candidate count. Returns
    `guidance_vm` unchanged (same identity) when the gate does not fire.
    """
    if str(record.get("kind") or "").strip().lower() != "decision":
        return guidance_vm
    if str(record.get("action") or "").strip().lower() not in _FINALIZE_GATE_ACTIONS:
        return guidance_vm
    gate = evaluate_distill_gate(quest_root, artifacts_dir)
    if gate is None:
        # Gate has cleared — if the incoming guidance_vm was previously gate-injected,
        # restore the previous recommended_skill so stale distill redirections are dropped.
        if isinstance(guidance_vm, dict) and guidance_vm.get("gate") == "finalize":
            base = dict(guidance_vm)
            previous_skill = str(base.get("previous_recommended_skill") or "").strip() or None
            previous_action = str(base.get("previous_recommended_action") or "").strip() or None
            cleared: dict[str, Any] = {
                k: v for k, v in base.items()
                if k not in _FINALIZE_GATE_INJECTED_KEYS
            }
            if previous_skill:
                cleared["recommended_skill"] = previous_skill
            if previous_action:
                cleared["recommended_action"] = previous_action
            return cleared
        return guidance_vm
    base = dict(guidance_vm) if isinstance(guidance_vm, dict) else {}
    previous_skill = str(base.get("recommended_skill") or "").strip() or None
    previous_action = str(base.get("recommended_action") or "").strip() or None
    routes = list(base.get("alternative_routes") or []) if isinstance(base.get("alternative_routes"), list) else []
    return {
        **base,
        "recommended_skill": "distill",
        "recommended_action": (
            "Distill required before write/finalize: scan completed runs, "
            "write 0..N knowledge cards, record one distill_review. "
            "The original write/finalize route is paused until distill_review lands."
        ),
        "previous_recommended_skill": previous_skill,
        "previous_recommended_action": previous_action,
        "alternative_routes": routes,
        "experience_distill": True,
        "gate": "finalize",
        "pending_distill_count": gate["pending_distill_count"],
        "pending_distill_ids": gate["pending_distill_ids"],
        "cursor_run_created_at": gate.get("cursor_run_created_at"),
        "source_artifact_id": str(record.get("artifact_id") or ""),
    }
