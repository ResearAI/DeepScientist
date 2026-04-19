#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

LIB = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
REPO = Path('/ssdwork/deepscientist/DeepScientist')
STATUS_PATH = Path('/tmp/aisb_mineru/status.json')
RUNNER_STATUS = Path('/tmp/aisb_mineru/runner_status.json')
PDF_DIR = Path('/tmp/aisb_pdfs')
MAX_RETRIES = int(os.environ.get('AISB_MINERU_MAX_RETRIES', '4'))
SLEEP_SECONDS = int(os.environ.get('AISB_MINERU_RETRY_SLEEP', '20'))


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _is_local_placeholder(md: Path) -> bool:
    try:
        head = md.read_text(errors='ignore')[:500]
    except Exception:
        return False
    return (
        head.startswith('# Local Markdown Extraction')
        or head.startswith('# Local Text Extraction')
        or 'generated locally from the saved PDF' in head
    )


def backfill_done() -> dict:
    status = load_json(STATUS_PATH, {'items': {}})
    items = status.setdefault('items', {})
    changed = False
    for md in LIB.glob('aisb.*/latex.md'):
        if _is_local_placeholder(md):
            continue
        bid = md.parent.name
        item = items.setdefault(bid, {})
        if item.get('mineru_state') != 'done':
            item['mineru_state'] = 'done'
            item['mineru_outputs'] = item.get('mineru_outputs') or {}
            item['mineru_outputs']['latex_md_path'] = str(md)
            pdf = PDF_DIR / f'{bid}.pdf'
            if pdf.exists():
                item['download_status'] = 'ok'
                item['pdf_path'] = str(pdf)
                item['mineru_outputs']['origin_pdf_path'] = str(pdf)
            changed = True
    if changed:
        save_json(STATUS_PATH, status)
    return status


def pending_ids(status: dict) -> list[str]:
    items = status.get('items', {})
    ids = []
    for entry in sorted(LIB.iterdir()):
        if not (entry.is_dir() and entry.name.startswith('aisb.')):
            continue
        bid = entry.name
        md_path = entry / 'latex.md'
        if md_path.exists() and not _is_local_placeholder(md_path):
            continue
        state = (items.get(bid) or {}).get('mineru_state')
        if state == 'done':
            continue
        ids.append(bid)
    return ids


def main() -> int:
    env = os.environ.copy()
    if 'MINERU_TOKEN' not in env:
        print('MINERU_TOKEN missing', file=sys.stderr)
        return 2
    runner = load_json(RUNNER_STATUS, {'attempts': {}, 'completed': [], 'failed': []})
    status = backfill_done()
    todo = pending_ids(status)
    print(json.dumps({'pending_count': len(todo), 'pending': todo[:30]}, ensure_ascii=False, indent=2))
    for bid in todo:
        attempts = runner['attempts'].get(bid, 0)
        while attempts < MAX_RETRIES:
            attempts += 1
            runner['attempts'][bid] = attempts
            save_json(RUNNER_STATUS, runner)
            cmd = [
                sys.executable,
                str(REPO / 'scripts' / 'process_aisb_papers.py'),
                '--ids', bid,
                '--chunk-size', '1',
                '--sleep-seconds', '10',
            ]
            proc = subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True)
            status = backfill_done()
            if (LIB / bid / 'latex.md').exists():
                if bid not in runner['completed']:
                    runner['completed'].append(bid)
                save_json(RUNNER_STATUS, runner)
                print(f'[done] {bid} after {attempts} attempt(s)')
                break
            runner['failed'] = [item for item in runner['failed'] if item.get('id') != bid]
            runner['failed'].append({
                'id': bid,
                'attempt': attempts,
                'returncode': proc.returncode,
                'stderr_tail': proc.stderr[-2000:],
                'stdout_tail': proc.stdout[-2000:],
            })
            save_json(RUNNER_STATUS, runner)
            print(f'[retry] {bid} attempt {attempts}/{MAX_RETRIES} rc={proc.returncode}')
            if attempts >= MAX_RETRIES:
                break
            time.sleep(SLEEP_SECONDS)
    status = backfill_done()
    remaining = pending_ids(status)
    print(json.dumps({
        'completed_count': len(runner['completed']),
        'remaining_count': len(remaining),
        'remaining': remaining[:30],
    }, ensure_ascii=False, indent=2))
    save_json(RUNNER_STATUS, runner)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
