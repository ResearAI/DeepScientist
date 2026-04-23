from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..memory.frontmatter import load_markdown_document

_DEFAULT_STAGE_SKILLS = (
    "scout",
    "baseline",
    "idea",
    "optimize",
    "experiment",
    "analysis-campaign",
    "write",
    "finalize",
    "decision",
)

_DEFAULT_COMPANION_SKILLS = (
    "paper-plot",
    "figure-polish",
    "intake-audit",
    "review",
    "rebuttal",
    "distill",
)

_SKILL_ROLE_FALLBACK_ORDER = {
    **{skill_id: index for index, skill_id in enumerate(_DEFAULT_STAGE_SKILLS, start=10)},
    **{skill_id: 100 + index for index, skill_id in enumerate(_DEFAULT_COMPANION_SKILLS, start=10)},
}


@dataclass(frozen=True)
class SkillBundle:
    skill_id: str
    name: str
    description: str
    root: Path
    skill_md: Path
    role: str
    metadata: dict[str, Any]
    openai_yaml: Path | None = None
    claude_md: Path | None = None


def _parse_frontmatter(path: Path) -> dict:
    metadata, _body = load_markdown_document(path)
    if not isinstance(metadata, dict):
        return {}
    return metadata


def _normalize_skill_role(skill_id: str, metadata: dict[str, Any]) -> str:
    raw = str(metadata.get("skill_role") or metadata.get("role") or "").strip().lower()
    if raw in {"stage", "companion", "custom"}:
        return raw
    if skill_id in _DEFAULT_STAGE_SKILLS:
        return "stage"
    if skill_id in _DEFAULT_COMPANION_SKILLS:
        return "companion"
    return "custom"


def _skill_order(skill_id: str, metadata: dict[str, Any]) -> tuple[int, str]:
    raw = metadata.get("skill_order")
    if isinstance(raw, int):
        return raw, skill_id
    if isinstance(raw, str):
        try:
            return int(raw.strip()), skill_id
        except ValueError:
            pass
    return _SKILL_ROLE_FALLBACK_ORDER.get(skill_id, 10_000), skill_id


def discover_skill_bundles(repo_root: Path) -> list[SkillBundle]:
    bundles: list[SkillBundle] = []
    skills_root = repo_root / "src" / "skills"
    if not skills_root.exists():
        return bundles
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        skill_id = skill_md.parent.name
        if skill_id.startswith("."):
            continue
        metadata = _parse_frontmatter(skill_md)
        bundles.append(
            SkillBundle(
                skill_id=skill_id,
                name=metadata.get("name", skill_id),
                description=metadata.get("description", ""),
                root=skill_md.parent,
                skill_md=skill_md,
                role=_normalize_skill_role(skill_id, metadata),
                metadata=metadata,
                openai_yaml=(skill_md.parent / "agents" / "openai.yaml") if (skill_md.parent / "agents" / "openai.yaml").exists() else None,
                claude_md=(skill_md.parent / "agents" / "claude.md") if (skill_md.parent / "agents" / "claude.md").exists() else None,
            )
        )
    bundles.sort(key=lambda bundle: _skill_order(bundle.skill_id, bundle.metadata))
    return bundles


def skill_ids_for_role(repo_root: Path, role: str) -> tuple[str, ...]:
    normalized = str(role or "").strip().lower()
    return tuple(bundle.skill_id for bundle in discover_skill_bundles(repo_root) if bundle.role == normalized)


def stage_skill_ids(repo_root: Path) -> tuple[str, ...]:
    return skill_ids_for_role(repo_root, "stage")


def companion_skill_ids(repo_root: Path) -> tuple[str, ...]:
    return skill_ids_for_role(repo_root, "companion")
