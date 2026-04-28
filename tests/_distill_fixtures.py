"""Shared fixtures for the experience-distill test suite.

Lifted out of the per-file `_seed_runs` / `_seed_distill_review` /
`_make_quest` / `_seed_pending_run` helpers that were duplicated across
the original 10 test files. Module name has a leading underscore so
pytest does not collect tests from it.
"""
from __future__ import annotations

import json
from pathlib import Path


def write_quest_yaml(
    quest_root: Path,
    *,
    distill_on: bool = True,
    recall_priors: bool = False,
    bare_string: bool = False,
) -> None:
    """Materialize quest.yaml startup_contract block. bare_string=True writes
    `experience_distill: on` (vs the dict `experience_distill: {mode: on}`)."""
    quest_root.mkdir(parents=True, exist_ok=True)
    distill_block = ""
    if distill_on:
        distill_block = "  experience_distill: on\n" if bare_string else "  experience_distill:\n    mode: on\n"
    recall_block = "  recall_priors: on\n" if recall_priors else ""
    if distill_block or recall_block:
        body = "startup_contract:\n" + distill_block + recall_block
    else:
        body = "startup_contract: {}\n"
    (quest_root / "quest.yaml").write_text(body, encoding="utf-8")


def make_quest_root(tmp_path: Path, *, distill_on: bool = True) -> Path:
    qr = tmp_path / "q"
    qr.mkdir()
    write_quest_yaml(qr, distill_on=distill_on)
    return qr


def seed_runs(artifacts_dir: Path, runs: list[dict]) -> None:
    """Write run records under artifacts_dir/runs/ and append index lines."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = artifacts_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    index = []
    for r in runs:
        path = runs_dir / f"{r['artifact_id']}.json"
        path.write_text(json.dumps(r), encoding="utf-8")
        index.append(json.dumps({
            "artifact_id": r["artifact_id"],
            "kind": r.get("kind", "run"),
            "status": r.get("status", "completed"),
            "path": str(path),
        }))
    (artifacts_dir / "_index.jsonl").write_text("\n".join(index) + "\n", encoding="utf-8")


def seed_pending_run(quest_root: Path, *, run_id: str = "run-pending-1", workspace: Path | None = None) -> None:
    """Append one completed main_experiment run; idempotent over an existing index."""
    target = workspace if workspace is not None else quest_root
    artifacts = target / "artifacts"
    runs_dir = artifacts / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    record = {"artifact_id": run_id, "kind": "run", "run_kind": "main_experiment", "status": "completed"}
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    line = json.dumps({"artifact_id": run_id, "kind": "run", "status": "completed", "path": str(runs_dir / f"{run_id}.json")})
    index_path = artifacts / "_index.jsonl"
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        index_path.write_text(existing + line + "\n", encoding="utf-8")
    else:
        index_path.write_text(line + "\n", encoding="utf-8")


def seed_worktree_pending_run(quest_root: Path, *, worktree_name: str, run_id: str) -> Path:
    worktree = quest_root / ".ds" / "worktrees" / worktree_name
    worktree.mkdir(parents=True, exist_ok=True)
    seed_pending_run(quest_root, run_id=run_id, workspace=worktree)
    return worktree


def seed_distill_review(
    artifacts_dir: Path,
    review_id: str,
    reviewed_run_ids: list[str],
    *,
    created_at: str = "2026-04-25T00:00:00+00:00",
) -> Path:
    """Write a decision(action='distill_review') record + index entry. Returns
    the record path so callers can mutate `created_at` post-write."""
    reviews_dir = artifacts_dir / "decisions"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "artifact_id": review_id,
        "kind": "decision",
        "action": "distill_review",
        "verdict": "covered",
        "reason": "test",
        "reviewed_run_ids": reviewed_run_ids,
        "cards_written": [],
        "reason_if_empty": "test",
        "created_at": created_at,
    }
    record_path = reviews_dir / f"{review_id}.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    index_path = artifacts_dir / "_index.jsonl"
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    line = json.dumps({"artifact_id": review_id, "kind": "decision", "status": "completed", "path": str(record_path)})
    index_path.write_text(existing + line + "\n", encoding="utf-8")
    return record_path


def seed_distill_review_in_quest(quest_root: Path, *, reviewed_run_ids: list[str]) -> None:
    seed_distill_review(quest_root / "artifacts", "distill-review-1", reviewed_run_ids)


def make_artifact_quest(temp_home: Path, *, distill_on: bool = True):
    """Boot QuestService + ArtifactService and create a quest. Returns
    (quest_service, artifact_service, quest_dict, quest_root)."""
    from deepscientist.artifact import ArtifactService
    from deepscientist.config import ConfigManager
    from deepscientist.home import ensure_home_layout, repo_root
    from deepscientist.quest import QuestService
    from deepscientist.skills import SkillInstaller

    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    contract = {"experience_distill": "on" if distill_on else "off"}
    quest = quest_service.create("distill quest", startup_contract=contract)
    quest_root = Path(quest["quest_root"])
    artifact = ArtifactService(temp_home)
    return quest_service, artifact, quest, quest_root


def enable_distill_in_quest(home: Path, quest_id: str) -> Path:
    """Patch an already-created quest's quest.yaml to set
    experience_distill={mode: on}. Returns the quest_root."""
    import yaml

    quest_root = home / "quests" / quest_id
    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return quest_root


def make_decision_record(action: str, *, artifact_id: str = "decision-zzz", reason: str = "test") -> dict:
    return {"kind": "decision", "action": action, "artifact_id": artifact_id, "reason": reason}


def make_baseline_guidance() -> dict:
    return {
        "schema_version": 1,
        "recommended_skill": "write",
        "recommended_action": "write",
        "alternative_routes": [],
    }
