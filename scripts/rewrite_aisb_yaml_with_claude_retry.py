#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import anthropic
import yaml

REPO_ROOT = Path('/ssdwork/deepscientist/DeepScientist')
sys.path.insert(0, str(REPO_ROOT / 'src'))

from deepscientist.benchstore.service import BenchStoreService

LIB_ROOT = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
CATALOG_ROOT = REPO_ROOT / 'AISB' / 'catalog'
WORKSPACE_HOME = Path.home() / 'DeepScientist'
DEFAULT_MODEL = 'claude-opus-4-6'
DEFAULT_BASE_URL = 'https://cursor.scihub.edu.kg/api'
DEFAULT_API_KEY = 'cr_93615fbfcf32ba9739623fcadde6dead1f0ca79f5357c841d392f137ffa79c6f'
DEFAULT_MAX_OUTPUT_TOKENS = int(os.environ.get('CLAUDE_CODE_MAX_OUTPUT_TOKENS', '12000'))
CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite_retry'
PREV_CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite'
LOG_PATH = Path('/tmp/aisb_yaml_rewrite_retry.log')

SYSTEM_PROMPT = textwrap.dedent('''\
You rewrite BenchStore YAML entries for DeepScientist.
Output YAML only. No fences. No prose.
Preserve facts from the provided material only.
Do not mention AutoSOTA.
Keep fields compatible with DeepScientist BenchStore.
Improve detail, clarity, specificity, hardware notes, dataset notes, time estimates, launch profiles, risks, and operational descriptions.
Do not invent metrics, checkpoints, or execution claims.
''')

KEYWORD_PATTERNS = [
    r'\bA100\b', r'\bH100\b', r'\bV100\b', r'\bRTX\b', r'\bGPU\b', r'\bCUDA\b',
    r'\bGB\b', r'\bTB\b', r'\bRAM\b', r'\bVRAM\b', r'\bhours?\b', r'\bdays?\b',
    r'\bminutes?\b', r'\bdataset\b', r'\bdownload\b', r'\btrain(?:ing)?\b',
    r'\beval(?:uation)?\b', r'\bbatch size\b', r'\bepochs?\b', r'\bmemory\b',
    r'\bdisk\b', r'\bthroughput\b', r'\bbenchmark\b', r'\bdeepspeed\b', r'\bslurm\b',
]

PROFILES = [
    {'name': 'full', 'readme': 12000, 'agents': 9000, 'latex': 18000, 'tree_items': 100, 'tree_depth': 2, 'code_files': 6, 'code_chars': 1800, 'keyword_lines': 100},
    {'name': 'medium', 'readme': 7000, 'agents': 5000, 'latex': 10000, 'tree_items': 70, 'tree_depth': 2, 'code_files': 4, 'code_chars': 1200, 'keyword_lines': 70},
    {'name': 'small', 'readme': 4000, 'agents': 3000, 'latex': 6000, 'tree_items': 40, 'tree_depth': 1, 'code_files': 3, 'code_chars': 800, 'keyword_lines': 40},
]

ID_EXAMPLE = textwrap.dedent('''\
id: aisb.t3.043_vhm
name: VHM
version: 0.1.0
one_line: Two-stage remote-sensing vision-language benchmark with large-scale pretraining and external evaluation.
task_description: >
  This packaged benchmark covers two-stage training and downstream evaluation for a 7B
  remote-sensing vision-language model.
task_mode: experiment_driven
requires_execution: true
requires_paper: true
integrity_level: cas_plus_canary
snapshot_status: external_eval_required
support_level: recovery
time_band: 2-4d
cost_band: very_high
difficulty: hard
data_access: public
primary_outputs:
  - aid_accuracy
  - vhm_sft_checkpoint
  - rseval_report
launch_profiles:
  - id: train_only
    label: Train Only
    description: Run training stages only.
dataset_download:
  primary_method: mixed
  sources: []
  notes: []
credential_requirements:
  mode: none
  items: []
  notes: []
resources:
  minimum: {}
  recommended: {}
environment:
  python: '3.10'
  cuda: '11.8'
  pytorch: '2.1.0'
  flash_attn: null
  key_packages: []
  notes: []
risk_flags: []
risk_notes: []
recommended_when: ...
not_recommended_when: ...
paper: {}
download: {}
display: {}
image_path: ...
''')

USER_TEMPLATE = textwrap.dedent('''\
Rewrite this benchmark YAML into a clearer and more detailed BenchStore entry.
Return YAML only.

Desired field shape example:
{id_example}

Current YAML:
```yaml
{current_yaml}
```

README excerpt:
```text
{readme_excerpt}
```

AGENTS excerpt:
```text
{agents_excerpt}
```

latex.md excerpt:
```text
{latex_excerpt}
```

Keyword evidence:
```text
{keyword_evidence}
```

Code tree summary:
```text
{tree_summary}
```

Selected code snippets:
```text
{code_snippets}
```
''')


def _read_text(path: Path, *, limit: int | None = None) -> str:
    if not path.exists():
        return ''
    text = path.read_text(errors='ignore')
    return text if limit is None else text[:limit]


def _extract_first_read_paths(agents_text: str) -> list[str]:
    out: list[str] = []
    for line in agents_text.splitlines():
        m = re.match(r'\s*\d+\.\s+`([^`]+)`', line)
        if m:
            out.append(m.group(1).strip())
    return out


def _tree(root: Path, *, max_items: int, max_depth: int) -> str:
    lines = []
    count = 0
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if len(rel.parts) > max_depth:
            continue
        if '.git' in rel.parts or '__pycache__' in rel.parts:
            continue
        lines.append(str(rel) + ('/' if path.is_dir() else ''))
        count += 1
        if count >= max_items:
            break
    return '\n'.join(lines)


def _snippets(root: Path, agents_text: str, *, max_files: int, chars_per_file: int) -> str:
    chunks = []
    for rel in _extract_first_read_paths(agents_text):
        if rel.endswith(('.md', '.yaml', '.json')):
            continue
        p = root / rel
        if not p.exists() or not p.is_file():
            continue
        chunks.append(f'### {rel}\n{_read_text(p, limit=chars_per_file)}')
        if len(chunks) >= max_files:
            break
    return '\n\n'.join(chunks)


def _keyword_lines(*texts: str, max_lines: int) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for raw in '\n'.join(texts).splitlines():
        line = raw.strip()
        if not line or line in seen:
            continue
        if any(re.search(pat, line, flags=re.I) for pat in KEYWORD_PATTERNS):
            seen.add(line)
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return '\n'.join(lines)


def _extract_yaml_text(response_text: str) -> str:
    m = re.search(r'```yaml\s*(.*?)```', response_text, flags=re.S | re.I)
    if m:
        return m.group(1).strip() + '\n'
    m = re.search(r'```\s*(.*?)```', response_text, flags=re.S)
    if m:
        return m.group(1).strip() + '\n'
    return response_text.strip() + '\n'


def _validate_yaml(yaml_text: str, *, validation_name: str) -> dict[str, Any]:
    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict):
        raise ValueError('Model output is not a YAML object.')
    tmp = REPO_ROOT / f'.tmp_{validation_name}.yaml'
    tmp.write_text(yaml_text)
    try:
        service = BenchStoreService(WORKSPACE_HOME, repo_root=REPO_ROOT)
        return service._load_entry_file(tmp)
    finally:
        if tmp.exists():
            tmp.unlink()


def _build_prompt(root: Path, yaml_path: Path, profile: dict[str, Any]) -> str:
    readme = _read_text(root / 'README.md', limit=profile['readme'])
    agents = _read_text(root / 'AGENTS.md', limit=profile['agents'])
    latex = _read_text(root / 'latex.md', limit=profile['latex'])
    current_yaml = _read_text(yaml_path)
    code_snips = _snippets(root, agents, max_files=profile['code_files'], chars_per_file=profile['code_chars'])
    keywords = _keyword_lines(readme, agents, latex, code_snips, max_lines=profile['keyword_lines'])
    tree = _tree(root, max_items=profile['tree_items'], max_depth=profile['tree_depth'])
    return USER_TEMPLATE.format(
        id_example=ID_EXAMPLE.strip(),
        current_yaml=current_yaml.strip(),
        readme_excerpt=readme.strip(),
        agents_excerpt=agents.strip(),
        latex_excerpt=latex.strip(),
        keyword_evidence=keywords.strip(),
        tree_summary=tree.strip(),
        code_snippets=code_snips.strip(),
    )


def _client(api_key: str, base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, base_url=base_url, max_retries=0)


def _call(client: anthropic.Anthropic, *, model: str, prompt: str, max_output_tokens: int) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=max_output_tokens,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return '\n'.join(block.text for block in resp.content if getattr(block, 'type', None) == 'text').strip()


def _failed_ids_from_log(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(errors='ignore')
    start = text.find('{')
    if start == -1:
        return []
    try:
        payload = json.loads(text[start:])
    except Exception:
        return []
    return [row['id'] for row in payload.get('results', []) if row.get('status') != 'ok']


def main() -> int:
    parser = argparse.ArgumentParser(description='Retry failed AISB YAML rewrites with smaller prompts and backoff.')
    parser.add_argument('--ids', type=str, default='')
    parser.add_argument('--model', type=str, default=os.environ.get('ANTHROPIC_MODEL', DEFAULT_MODEL))
    parser.add_argument('--base-url', type=str, default=os.environ.get('ANTHROPIC_BASE_URL', DEFAULT_BASE_URL))
    parser.add_argument('--api-key', type=str, default=os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN') or DEFAULT_API_KEY)
    parser.add_argument('--max-output-tokens', type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument('--sleep', type=float, default=20.0)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.ids:
        ids = [x.strip() for x in args.ids.split(',') if x.strip()]
    else:
        ids = _failed_ids_from_log(Path('/tmp/aisb_yaml_rewrite.log'))

    client = _client(args.api_key, args.base_url)
    CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)
    results = []

    for benchmark_id in ids:
        root = LIB_ROOT / benchmark_id
        yaml_path = CATALOG_ROOT / f'{benchmark_id}.yaml'
        lib_yaml_path = root / 'aisb_catalog.yaml'
        bundle = CONTEXT_ROOT / benchmark_id
        bundle.mkdir(parents=True, exist_ok=True)
        success = False
        errors = []
        for profile in PROFILES:
            prompt = _build_prompt(root, yaml_path, profile)
            (bundle / f'prompt_{profile["name"]}.txt').write_text(prompt)
            for attempt in range(1, 6):
                try:
                    raw = _call(client, model=args.model, prompt=prompt, max_output_tokens=args.max_output_tokens)
                    (bundle / f'response_{profile["name"]}_{attempt}.txt').write_text(raw)
                    yaml_text = _extract_yaml_text(raw)
                    validated = _validate_yaml(yaml_text, validation_name=f'{benchmark_id}_{profile["name"]}_{attempt}')
                    (bundle / f'validated_{profile["name"]}_{attempt}.json').write_text(json.dumps(validated, indent=2, ensure_ascii=False))
                    if not args.dry_run:
                        yaml_path.write_text(yaml_text)
                        lib_yaml_path.write_text(yaml_text)
                    results.append({'id': benchmark_id, 'status': 'ok', 'profile': profile['name'], 'attempt': attempt})
                    success = True
                    break
                except Exception as exc:
                    err = repr(exc)
                    errors.append({'profile': profile['name'], 'attempt': attempt, 'error': err, 'prompt_len': len(prompt)})
                    (bundle / f'error_{profile["name"]}_{attempt}.txt').write_text(err)
                    if (
                        'RateLimitError' in err
                        or 'PermissionDeniedError' in err
                        or 'InternalServerError' in err
                        or 'E015' in err
                        or 'E012' in err
                        or 'E001' in err
                        or '429' in err
                        or '529' in err
                        or '503' in err
                        or '403' in err
                    ):
                        time.sleep(args.sleep * (2 ** (attempt - 1)) + random.random() * 3)
                        continue
                    if 'BadRequestError' in err or 'E005' in err:
                        break
                    time.sleep(args.sleep + random.random() * 2)
            if success:
                break
        if not success:
            results.append({'id': benchmark_id, 'status': 'error', 'errors': errors})
    output = {'total': len(results), 'results': results}
    LOG_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(r['status'] == 'ok' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
