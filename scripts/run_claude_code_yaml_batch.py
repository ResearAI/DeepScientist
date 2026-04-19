#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path('/ssdwork/deepscientist/DeepScientist')
MAIN_LOG = Path('/tmp/aisb_yaml_rewrite.log')
BATCH_LOG = Path('/tmp/aisb_yaml_rewrite_claude_code_batch.log')
STATUS_PATH = Path('/tmp/aisb_yaml_rewrite_claude_code_batch_status.json')
SCRIPT = REPO_ROOT / 'scripts' / 'rewrite_aisb_yaml_with_claude_code.py'
CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite_claude_code'
MODEL = os.environ.get('CLAUDE_CODE_MODEL', 'claude-opus-4-6')
SLEEP = int(os.environ.get('AISB_CLAUDE_CODE_BATCH_SLEEP', '10'))
MAX_RETRIES = int(os.environ.get('AISB_CLAUDE_CODE_BATCH_RETRIES', '3'))


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def failed_ids() -> list[str]:
    if not MAIN_LOG.exists():
        return []
    text = MAIN_LOG.read_text(errors='ignore')
    start = text.find('{')
    if start == -1:
        return []
    payload = json.loads(text[start:])
    return [str(row.get('id')) for row in payload.get('results', []) if row.get('status') != 'ok']


def done_ids() -> set[str]:
    if not CONTEXT_ROOT.exists():
        return set()
    return {d.name for d in CONTEXT_ROOT.iterdir() if d.is_dir() and (d / 'validated.json').exists()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', default='')
    args = parser.parse_args()
    ids = [x.strip() for x in args.ids.split(',') if x.strip()] if args.ids else failed_ids()
    state = load_json(STATUS_PATH, {'attempts': {}, 'completed': [], 'failed': []})
    done = done_ids()
    todo = [bid for bid in ids if bid not in done]
    print(json.dumps({'todo_count': len(todo), 'todo': todo[:30]}, ensure_ascii=False, indent=2))
    BATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    for bid in todo:
        attempts = int(state['attempts'].get(bid, 0))
        while attempts < MAX_RETRIES:
            attempts += 1
            state['attempts'][bid] = attempts
            save_json(STATUS_PATH, state)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), '--ids', bid, '--model', MODEL],
                cwd=str(REPO_ROOT),
                text=True,
                capture_output=True,
                env=dict(os.environ),
            )
            with BATCH_LOG.open('a', encoding='utf-8') as fh:
                fh.write(f'## {bid} attempt {attempts} rc={proc.returncode}\n')
                fh.write(proc.stdout[-4000:])
                if proc.stderr:
                    fh.write('\n[stderr]\n')
                    fh.write(proc.stderr[-4000:])
                fh.write('\n\n')
            if bid in done_ids():
                if bid not in state['completed']:
                    state['completed'].append(bid)
                state['failed'] = [row for row in state['failed'] if row.get('id') != bid]
                save_json(STATUS_PATH, state)
                print(f'[done] {bid} in {attempts} attempt(s)')
                break
            state['failed'] = [row for row in state['failed'] if row.get('id') != bid]
            state['failed'].append({'id': bid, 'attempt': attempts, 'returncode': proc.returncode})
            save_json(STATUS_PATH, state)
            print(f'[retry] {bid} attempt {attempts}/{MAX_RETRIES} rc={proc.returncode}')
            if attempts >= MAX_RETRIES:
                break
            time.sleep(SLEEP * attempts)
        time.sleep(SLEEP)
    print(json.dumps({'completed': len(state['completed']), 'failed': len(state['failed'])}, ensure_ascii=False, indent=2))
    save_json(STATUS_PATH, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
