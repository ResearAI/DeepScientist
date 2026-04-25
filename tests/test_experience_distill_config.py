from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact.experience_distill import (
    coerce_distill_mode,
    coerce_recall_priors_mode,
    is_distill_on,
    is_recall_priors_on,
    read_distill_mode,
    read_recall_priors_mode,
)


def _write_quest_yaml(quest_root: Path, body: str) -> None:
    quest_root.mkdir(parents=True, exist_ok=True)
    (quest_root / "quest.yaml").write_text(body, encoding="utf-8")


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
