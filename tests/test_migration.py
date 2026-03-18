from __future__ import annotations

from pathlib import Path

import pytest

from deepscientist.home import ensure_home_layout
from deepscientist.migration import looks_like_deepscientist_root, migrate_deepscientist_root


def test_migrate_deepscientist_root_copies_full_tree_and_verifies(temp_home: Path) -> None:
    source = temp_home
    ensure_home_layout(source)
    (source / "config" / "config.yaml").write_text("ui:\n  host: 0.0.0.0\n", encoding="utf-8")
    (source / "quests" / "001").mkdir(parents=True, exist_ok=True)
    (source / "quests" / "001" / "brief.md").write_text("# quest\n", encoding="utf-8")
    (source / "cli" / "bin").mkdir(parents=True, exist_ok=True)
    (source / "cli" / "bin" / "ds.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")

    target = source.parent / "DeepScientistMigrated"
    payload = migrate_deepscientist_root(source, target)

    assert payload["ok"] is True
    assert payload["source"] == str(source.resolve())
    assert payload["target"] == str(target.resolve())
    assert (target / "config" / "config.yaml").exists()
    assert (target / "quests" / "001" / "brief.md").read_text(encoding="utf-8") == "# quest\n"
    assert (target / "cli" / "bin" / "ds.js").exists()
    assert source.exists()


def test_migrate_deepscientist_root_rejects_nested_target(temp_home: Path) -> None:
    source = temp_home
    ensure_home_layout(source)
    nested_target = source / "migrated"

    with pytest.raises(ValueError, match="inside the current DeepScientist root"):
        migrate_deepscientist_root(source, nested_target)


def test_looks_like_deepscientist_root_accepts_install_only_layout(tmp_path: Path) -> None:
    source = tmp_path / "install-root"
    (source / "cli" / "bin").mkdir(parents=True, exist_ok=True)
    (source / "cli" / "bin" / "ds.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")

    assert looks_like_deepscientist_root(source) is True
