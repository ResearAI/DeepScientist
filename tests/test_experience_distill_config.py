from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.artifact.experience_distill import (
    coerce_distill_mode,
    is_distill_on,
    read_distill_mode,
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
