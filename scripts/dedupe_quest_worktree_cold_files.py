#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from deepscientist.runtime_storage import dedupe_worktree_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Hardlink-dedupe duplicated large cold files under quest worktrees.")
    parser.add_argument("quest_root", help="Absolute quest root path")
    parser.add_argument("--min-mb", type=int, default=1, help="Only dedupe files at or above this size")
    args = parser.parse_args()

    quest_root = Path(args.quest_root).expanduser().resolve()
    result = dedupe_worktree_files(quest_root, min_bytes=max(1, args.min_mb) * 1024 * 1024)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
