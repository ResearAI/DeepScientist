#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from deepscientist.runtime_storage import slim_quest_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact oversized quest JSONL payloads into quest-local backups.")
    parser.add_argument("quest_root", help="Absolute quest root path")
    parser.add_argument("--threshold-mb", type=int, default=8, help="Compact lines larger than this many MB")
    args = parser.parse_args()

    quest_root = Path(args.quest_root).expanduser().resolve()
    manifest = slim_quest_jsonl(quest_root, threshold_bytes=max(1, args.threshold_mb) * 1024 * 1024)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
