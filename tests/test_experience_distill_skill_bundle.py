from __future__ import annotations

from deepscientist.skills.registry import _DEFAULT_COMPANION_SKILLS


def test_distill_in_default_companions():
    assert "distill" in _DEFAULT_COMPANION_SKILLS


def test_distill_skill_bundle_is_discoverable():
    from deepscientist.home import repo_root
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
