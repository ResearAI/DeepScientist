#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path('/ssdwork/deepscientist/DeepScientist')
MAIN_LOG = Path('/tmp/aisb_yaml_rewrite.log')
RUNNER_LOG = Path('/tmp/aisb_yaml_rewrite_claude_code_retry.log')
RUNNER_STATUS = Path('/tmp/aisb_yaml_rewrite_claude_code_retry_status.json')
CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite_claude_code'
SCRIPT = REPO_ROOT / 'scripts' / 'rewrite_aisb_yaml_with_claude_code.py'
MAX_RETRIES = int(os.environ.get('AISB_CLAUDE_CODE_MAX_RETRIES', '3'))
SLEEP_SECONDS = int(os.environ.get('AISB_CLAUDE_CODE_SLEEP', '20'))
MODEL = os.environ.get('CLAUDE_CODE_MODEL', 'claude-opus-4-6')


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
    ids = []
    for row in payload.get('results', []):
        if row.get('status') != 'ok':
            ids.append(str(row.get('id')))
    return ids


def already_done(bid: str) -> bool:
    return (CONTEXT_ROOT / bid / 'validated.json').exists()


def main() -> int:
    state = load_json(RUNNER_STATUS, {'attempts': {}, 'completed': [], 'failed': []})
    todo = [bid for bid in failed_ids() if not already_done(bid)]
    print(json.dumps({'todo_count': len(todo), 'todo': todo[:30]}, ensure_ascii=False, indent=2))
    for bid in todo:
        attempts = int(state['attempts'].get(bid, 0))
        while attempts < MAX_RETRIES:
            attempts += 1
            state['attempts'][bid] = attempts
            save_json(RUNNER_STATUS, state)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), '--ids', bid, '--model', MODEL],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=dict(os.environ),
            )
            RUNNER_LOG.parent.mkdir(parents=True, exist_ok=True)
            with RUNNER_LOG.open('a', encoding='utf-8') as fh:
                fh.write(f'## {bid} attempt {attempts} rc={proc.returncode}\n')
                fh.write(proc.stdout[-4000:])
                if proc.stderr:
                    fh.write('\n[stderr]\n')
                    fh.write(proc.stderr[-4000:])
                fh.write('\n\n')
            if already_done(bid):
                if bid not in state['completed']:
                    state['completed'].append(bid)
                state['failed'] = [row for row in state['failed'] if row.get('id') != bid]
                save_json(RUNNER_STATUS, state)
                print(f'[done] {bid} in {attempts} attempt(s)')
                break
            state['failed'] = [row for row in state['failed'] if row.get('id') != bid]
            state['failed'].append({'id': bid, 'attempt': attempts, 'returncode': proc.returncode})
            save_json(RUNNER_STATUS, state)
            print(f'[retry] {bid} attempt {attempts}/{MAX_RETRIES} rc={proc.returncode}')
            if attempts >= MAX_RETRIES:
                break
            time.sleep(SLEEP_SECONDS * attempts)
    print(json.dumps({'completed': len(state['completed']), 'failed': len(state['failed'])}, ensure_ascii=False, indent=2))
    save_json(RUNNER_STATUS, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
