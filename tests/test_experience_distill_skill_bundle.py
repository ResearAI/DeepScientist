from __future__ import annotations

from deepscientist.skills.registry import _DEFAULT_COMPANION_SKILLS


def test_distill_in_default_companions():
    assert "distill" in _DEFAULT_COMPANION_SKILLS
