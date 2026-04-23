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

from pathlib import Path
from typing import Any


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
