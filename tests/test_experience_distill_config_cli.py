"""Configuration toggles, retroactive CLI, and skill discovery for
experience-distill.

Folds in:
- (was) tests/test_experience_distill_config.py — coerce_*/read_* toggles
  for `experience_distill` and `recall_priors` startup_contract entries.
- (was) tests/test_experience_distill_cli.py — `ds distill-quest` and
  `emit_experience_drafts` retroactive draft emission.
- (was) tests/test_experience_distill_skill_bundle.py — distill skill
  registration + bundle discoverability.

These three are user-facing surfaces that don't share state — but each is
small enough that splitting hurts more than it helps.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepscientist.artifact import ArtifactService
from deepscientist.artifact.experience_distill import (
    coerce_distill_mode,
    coerce_recall_priors_mode,
    emit_experience_drafts,
    is_distill_on,
    is_recall_priors_on,
    read_distill_mode,
    read_recall_priors_mode,
)
from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller
from deepscientist.skills.registry import _DEFAULT_COMPANION_SKILLS


def _write_quest_yaml(quest_root: Path, body: str) -> None:
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / "quest.yaml").write_text(body, encoding="utf-8")


# ===== experience_distill mode toggles ===================================


def test_coerce_string_on_off():
    assert coerce_distill_mode("on") == {"mode": "on"}
    assert coerce_distill_mode("OFF") == {"mode": "off"}
    assert coerce_distill_mode("") == {"mode": "off"}
    assert coerce_distill_mode(None) == {"mode": "off"}


def test_coerce_dict_passthrough():
    assert coerce_distill_mode({"mode": "on"}) == {"mode": "on"}
    assert coerce_distill_mode({"mode": "bogus"}) == {"mode": "off"}
    assert coerce_distill_mode({}) == {"mode": "off"}
    # YAML parses `mode: on` as boolean True inside a dict; must still resolve to on.
    assert coerce_distill_mode({"mode": True}) == {"mode": "on"}
    assert coerce_distill_mode({"mode": False}) == {"mode": "off"}


def test_read_distill_mode_defaults_off(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(qr, "startup_contract: {}\n")
    assert read_distill_mode(qr) == {"mode": "off"}
    assert is_distill_on(qr) is False


def test_read_distill_mode_on(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(
        qr,
        "startup_contract:\n  experience_distill:\n    mode: on\n",
    )
    assert read_distill_mode(qr) == {"mode": "on"}
    assert is_distill_on(qr) is True


def test_read_distill_mode_accepts_bare_string(tmp_path: Path):
    qr = tmp_path / "q_demo"
    _write_quest_yaml(
        qr,
        "startup_contract:\n  experience_distill: on\n",
    )
    assert is_distill_on(qr) is True


def test_read_distill_mode_missing_quest_yaml_defaults_off(tmp_path: Path):
    qr = tmp_path / "q_demo"
    qr.mkdir()
    assert is_distill_on(qr) is False


def test_is_distill_on_accepts_none_quest_root():
    assert is_distill_on(None) is False


# ===== recall_priors mode toggles ========================================


def test_coerce_recall_priors_mode_accepts_bool() -> None:
    assert coerce_recall_priors_mode(True) == {"mode": "on"}
    assert coerce_recall_priors_mode(False) == {"mode": "off"}


def test_coerce_recall_priors_mode_accepts_string() -> None:
    assert coerce_recall_priors_mode("on") == {"mode": "on"}
    assert coerce_recall_priors_mode("OFF") == {"mode": "off"}
    assert coerce_recall_priors_mode("garbage") == {"mode": "off"}


def test_coerce_recall_priors_mode_accepts_dict() -> None:
    assert coerce_recall_priors_mode({"mode": "on"}) == {"mode": "on"}
    assert coerce_recall_priors_mode({"mode": True}) == {"mode": "on"}
    assert coerce_recall_priors_mode({"mode": False}) == {"mode": "off"}


def test_coerce_recall_priors_mode_default_off() -> None:
    assert coerce_recall_priors_mode(None) == {"mode": "off"}
    assert coerce_recall_priors_mode(42) == {"mode": "off"}


def test_read_recall_priors_mode_reads_quest_yaml(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n", encoding="utf-8"
    )
    assert read_recall_priors_mode(quest_root) == {"mode": "on"}
    assert is_recall_priors_on(quest_root) is True


def test_read_recall_priors_mode_defaults_off_when_missing(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text("startup_contract: {}\n", encoding="utf-8")
    assert read_recall_priors_mode(quest_root) == {"mode": "off"}
    assert is_recall_priors_on(quest_root) is False


def test_read_recall_priors_mode_defaults_off_when_no_yaml(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    assert is_recall_priors_on(quest_root) is False


def test_read_recall_priors_mode_independent_of_distill(tmp_path: Path) -> None:
    """recall_priors and experience_distill are separate fields."""
    from deepscientist.artifact.experience_distill import is_distill_on

    quest_root = tmp_path / "quest"
    quest_root.mkdir()
    (quest_root / "quest.yaml").write_text(
        "startup_contract:\n  recall_priors: on\n  experience_distill: off\n",
        encoding="utf-8",
    )
    assert is_recall_priors_on(quest_root) is True
    assert is_distill_on(quest_root) is False


# ===== emit_experience_drafts (pure) =====================================


def test_emit_experience_drafts_writes_one_file_per_slice(tmp_path: Path):
    drafts_root = tmp_path / "drafts_out"
    records = [
        {
            "artifact_id": "a1",
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "campaign_id": "cmp_1",
            "slice_id": "s_1",
            "details": {"title": "Warm-up effect on CNNs"},
            "summary": "Warm-up helps on small batch",
        },
        {
            "artifact_id": "a2",
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_2",
            "campaign_id": "cmp_1",
            "slice_id": "s_2",
            "details": {"title": "Cooldown effect"},
            "summary": "Cooldown mostly neutral",
        },
        {
            "artifact_id": "a3",
            "kind": "run",
            "run_kind": "main.experiment",  # not a slice — must be skipped
        },
    ]
    written = emit_experience_drafts(quest_id="q_demo", records=records, drafts_root=drafts_root)
    assert len(written) == 2
    draft_dir = drafts_root / "q_demo"
    assert (draft_dir / "cmp_1__s_1.md").exists()
    assert (draft_dir / "cmp_1__s_2.md").exists()
    body = (draft_dir / "cmp_1__s_1.md").read_text(encoding="utf-8")
    assert "subtype: experience" in body
    assert "quest: q_demo" in body
    assert "run: cmp_1:s_1" in body
    assert "TODO: claim" in body
    assert "TODO: mechanism" in body
    assert "Warm-up effect on CNNs" in body


def test_emit_experience_drafts_escapes_title_with_quote(tmp_path: Path):
    import yaml
    drafts_root = tmp_path / "drafts_out"
    records = [{
        "artifact_id": "a1",
        "kind": "run",
        "run_kind": "analysis.slice",
        "status": "completed",
        "run_id": "cmp_1:s_1",
        "campaign_id": "cmp_1",
        "slice_id": "s_1",
        "details": {"title": 'effect of "warm-up" on CNNs'},
    }]
    written = emit_experience_drafts(quest_id="q_demo", records=records, drafts_root=drafts_root)
    body = written[0].read_text(encoding="utf-8")
    # Parse the YAML frontmatter and verify title survived the escaping.
    frontmatter_text = body.split("---\n", 2)[1]
    meta = yaml.safe_load(frontmatter_text)
    assert meta["lineage"][0]["note"] == 'effect of "warm-up" on CNNs'


# ===== ds distill-quest CLI ==============================================


def test_distill_quest_cli_end_to_end(tmp_path: Path, capsys):
    home = tmp_path / "DeepScientistHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("Distill retro demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id
    ArtifactService(home).record(
        quest_root,
        {
            "kind": "run",
            "run_kind": "analysis.slice",
            "status": "completed",
            "run_id": "cmp_1:s_1",
            "summary": "Slice 1 recorded",
        },
    )
    from deepscientist.cli import distill_quest_command
    rc = distill_quest_command(home, quest_id)
    assert rc == 0
    drafts_dir = home / "drafts" / "experiences" / quest_id
    files = list(drafts_dir.glob("*.md"))
    assert len(files) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["quest_id"] == quest_id
    assert payload["drafts"] == 1


def test_distill_quest_command_includes_main_experiment_and_experiment_kinds(tmp_path: Path):
    """Retroactive CLI must emit drafts for analysis.slice + main_experiment + experiment, not just analysis.slice."""
    from deepscientist.cli import distill_quest_command
    import yaml

    home = tmp_path / "DSHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("CLI candidates demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id

    # Enable distill (some downstream emit logic may need it; harmless if not)
    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    service = ArtifactService(home)
    service.record(quest_root, {"kind": "run", "run_kind": "analysis.slice", "status": "completed", "run_id": "cmp:s1", "summary": "slice"})
    service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:1", "summary": "main"})
    service.record(quest_root, {"kind": "run", "run_kind": "experiment", "status": "completed", "run_id": "abl:1", "summary": "ablation"})

    rc = distill_quest_command(home, quest_id)
    assert rc == 0
    drafts_dir = home / "drafts" / "experiences" / quest_id
    drafts = sorted(drafts_dir.glob("*.md"))
    assert len(drafts) == 3, f"expected 3 drafts (analysis.slice + main_experiment + experiment); got {len(drafts)}"


def test_distill_quest_command_excludes_already_reviewed_runs(tmp_path: Path):
    """Retroactive CLI must skip runs already covered by distill_review records."""
    from deepscientist.cli import distill_quest_command
    import yaml

    home = tmp_path / "DSHome"
    ensure_home_layout(home)
    ConfigManager(home).ensure_files()
    quest_service = QuestService(home, skill_installer=SkillInstaller(repo_root(), home))
    quest = quest_service.create("CLI exclude reviewed demo")
    quest_id = quest["quest_id"]
    quest_root = home / "quests" / quest_id

    quest_yaml = quest_root / "quest.yaml"
    payload = yaml.safe_load(quest_yaml.read_text(encoding="utf-8")) or {}
    contract = payload.get("startup_contract") if isinstance(payload.get("startup_contract"), dict) else {}
    contract["experience_distill"] = {"mode": "on"}
    payload["startup_contract"] = contract
    quest_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    service = ArtifactService(home)
    run_a = service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:1", "summary": "A"})
    run_b = service.record(quest_root, {"kind": "run", "run_kind": "main_experiment", "status": "completed", "run_id": "main:2", "summary": "B"})
    # Mark run A as reviewed
    service.record(quest_root, {
        "kind": "decision",
        "action": "distill_review",
        "verdict": "covered",
        "reason": "smoke",
        "reviewed_run_ids": [run_a["artifact_id"]],
        "cards_written": [],
        "reason_if_empty": "smoke",
    })

    rc = distill_quest_command(home, quest_id)
    assert rc == 0
    drafts_dir = home / "drafts" / "experiences" / quest_id
    drafts = sorted(drafts_dir.glob("*.md"))
    assert len(drafts) == 1, f"expected 1 draft (only run B unreviewed); got {len(drafts)}"


def test_distill_quest_command_returns_error_for_nonexistent_quest(tmp_path: Path, capsys):
    from deepscientist.cli import distill_quest_command

    home = tmp_path / "DSHome"
    ensure_home_layout(home)

    rc = distill_quest_command(home, "no-such-quest")
    assert rc == 1
    captured = capsys.readouterr()
    assert "Quest not found" in captured.err
    assert "no-such-quest" in captured.err


# ===== distill skill bundle ==============================================


def test_distill_in_default_companions():
    assert "distill" in _DEFAULT_COMPANION_SKILLS


def test_distill_skill_bundle_is_discoverable():
    from deepscientist.skills.registry import discover_skill_bundles

    root = repo_root()
    bundles = discover_skill_bundles(root)
    ids = {bundle.skill_id for bundle in bundles}
    assert "distill" in ids, f"Expected distill skill; got {sorted(ids)}"
    distill = next(bundle for bundle in bundles if bundle.skill_id == "distill")
    assert distill.skill_md.exists()
    assert distill.metadata.get("name") == "distill"
    assert "experience" in (distill.metadata.get("description") or "").lower()
    assert distill.metadata.get("skill_role") == "companion"
