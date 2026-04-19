#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path('/ssdwork/deepscientist/DeepScientist')
LIB_ROOT = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
STAGE_ROOT = Path('/tmp/aisb_release_stage')
STATUS_PATH = Path('/tmp/aisb_release_stage/status.json')
REPO = 'ResearAI/DeepScientist'
TAG = 'aisb-v0.0.1'

EXCLUDES = {
    '.git',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.DS_Store',
}


def load_status() -> dict:
    if not STATUS_PATH.exists():
        return {'packaged': {}, 'uploaded': {}, 'failed': {}}
    return json.loads(STATUS_PATH.read_text())


def save_status(payload: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def safe_copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    def ignore(dir_str: str, names: list[str]) -> set[str]:
        base = Path(dir_str)
        skipped: set[str] = set()
        for name in names:
            if name in EXCLUDES:
                skipped.add(name)
                continue
            candidate = base / name
            if candidate.is_symlink() and not candidate.exists():
                skipped.add(name)
        return skipped
    shutil.copytree(src, dst, ignore=ignore, symlinks=True, ignore_dangling_symlinks=True)


def package_dir(src: Path, out_zip: Path) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(src.rglob('*')):
            rel = path.relative_to(src)
            if any(part in EXCLUDES for part in rel.parts):
                continue
            if path.is_symlink() and not path.exists():
                continue
            if path.is_dir():
                continue
            archive.write(path, arcname=str(Path(src.name) / rel))


def asset_exists(asset_name: str) -> bool:
    last_exc = None
    for attempt in range(1, 6):
        try:
            proc = subprocess.run(
                ['gh', 'release', 'view', TAG, '--repo', REPO, '--json', 'assets'],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(proc.stdout)
            return any(str(asset.get('name') or '') == asset_name for asset in payload.get('assets', []))
        except Exception as exc:
            last_exc = exc
            time.sleep(attempt * 2)
    raise last_exc


def main() -> int:
    dirs = sorted([p for p in LIB_ROOT.iterdir() if p.is_dir() and p.name.startswith('aisb.')])
    status = load_status()
    for src in dirs:
        bid = src.name
        zip_name = f'{bid}.zip'
        zip_path = STAGE_ROOT / 'zips' / zip_name
        try:
            if not zip_path.exists():
                package_dir(src, zip_path)
            status['packaged'][bid] = {
                'zip_path': str(zip_path),
                'size_bytes': zip_path.stat().st_size,
            }
            save_status(status)
            if asset_exists(zip_name):
                status['failed'].pop(bid, None)
                status['uploaded'][bid] = {'asset_name': zip_name, 'status': 'already_present'}
                save_status(status)
                continue
            subprocess.run(['gh', 'release', 'upload', TAG, str(zip_path), '--repo', REPO], check=True)
            status['failed'].pop(bid, None)
            status['uploaded'][bid] = {'asset_name': zip_name, 'status': 'uploaded'}
            save_status(status)
        except Exception as exc:
            status['failed'][bid] = {'error': repr(exc)}
            save_status(status)
            print(f'[failed] {bid}: {exc}')
            return 1
    print(json.dumps({
        'dir_count': len(dirs),
        'packaged': len(status['packaged']),
        'uploaded': len(status['uploaded']),
        'failed': len(status['failed']),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
