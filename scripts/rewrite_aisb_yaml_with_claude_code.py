#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path('/ssdwork/deepscientist/DeepScientist')
sys.path.insert(0, str(REPO_ROOT / 'src'))

from deepscientist.benchstore.service import BenchStoreService

LIB_ROOT = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
CATALOG_ROOT = REPO_ROOT / 'AISB' / 'catalog'
WORKSPACE_HOME = Path.home() / 'DeepScientist'
DEFAULT_MODEL = 'claude-opus-4-6'
CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite_claude_code'
DEFAULT_MAX_OUTPUT_TOKENS = int(os.environ.get('CLAUDE_CODE_MAX_OUTPUT_TOKENS', '12000'))

SYSTEM_PROMPT = textwrap.dedent('''\
You rewrite BenchStore YAML entries for DeepScientist.
Output YAML only. No fences. No prose.
Preserve facts from the provided material only.
Do not mention AutoSOTA.
Keep fields compatible with DeepScientist BenchStore.
Improve detail, clarity, specificity, hardware notes, dataset notes, time estimates, launch profiles, risks, and operational descriptions.
Do not invent metrics, checkpoints, or execution claims.
''')

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

KEYWORD_PATTERNS = [
    r'\bA100\b', r'\bH100\b', r'\bV100\b', r'\bRTX\b', r'\bGPU\b', r'\bCUDA\b',
    r'\bGB\b', r'\bTB\b', r'\bRAM\b', r'\bVRAM\b', r'\bhours?\b', r'\bdays?\b',
    r'\bminutes?\b', r'\bdataset\b', r'\bdownload\b', r'\btrain(?:ing)?\b',
    r'\beval(?:uation)?\b', r'\bbatch size\b', r'\bepochs?\b', r'\bmemory\b',
    r'\bdisk\b', r'\bthroughput\b', r'\bbenchmark\b', r'\bdeepspeed\b', r'\bslurm\b',
]


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


def _tree(root: Path, *, max_items: int = 80, max_depth: int = 2) -> str:
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


def _snippets(root: Path, agents_text: str, *, max_files: int = 5, chars_per_file: int = 1200) -> str:
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


def _keyword_lines(*texts: str, max_lines: int = 80) -> str:
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
    try:
        payload = json.loads(response_text)
        if isinstance(payload, dict) and str(payload.get('type') or '') == 'result':
            text = str(payload.get('result') or '').strip()
            if text:
                response_text = text
    except Exception:
        pass
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


def _build_prompt(root: Path, yaml_path: Path) -> str:
    readme = _read_text(root / 'README.md', limit=9000)
    agents = _read_text(root / 'AGENTS.md', limit=7000)
    latex = _read_text(root / 'latex.md', limit=12000)
    current_yaml = _read_text(yaml_path)
    code_snips = _snippets(root, agents)
    keywords = _keyword_lines(readme, agents, latex, code_snips)
    tree = _tree(root)
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


def _repair_yaml_with_claude_cli(raw_yaml: str, *, model: str) -> str:
    repair_prompt = textwrap.dedent(f"""\
The following text is intended to be a BenchStore YAML entry but is not strictly valid YAML.
Repair it into strictly valid YAML only.
Do not change factual content unless necessary for YAML validity.
Quote strings when needed.
Return YAML only.

Invalid YAML:
```yaml
{raw_yaml}
```
""")
    return _call_claude_cli(repair_prompt, model=model)


def _bench_ids(ids_arg: str | None) -> list[str]:
    if ids_arg:
        return [item.strip() for item in ids_arg.split(',') if item.strip()]
    return [path.stem for path in sorted(CATALOG_ROOT.glob('aisb.*.yaml'))]


def _call_claude_cli(prompt: str, *, model: str) -> str:
    env = dict(os.environ)
    cmd = [
        'claude',
        '-p',
        '--input-format', 'text',
        '--output-format', 'json',
        '--model', model,
        '--permission-mode', 'bypassPermissions',
        '--no-session-persistence',
        '--tools', '',
        '--system-prompt', SYSTEM_PROMPT,
    ]
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'claude_cli_failed rc={proc.returncode} stderr={proc.stderr[-4000:]} stdout={proc.stdout[-2000:]}')
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description='Rewrite AISB BenchStore YAML entries with Claude Code CLI.')
    parser.add_argument('--ids', type=str, default='')
    parser.add_argument('--model', type=str, default=os.environ.get('CLAUDE_CODE_MODEL', DEFAULT_MODEL))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)
    results = []

    for benchmark_id in _bench_ids(args.ids or None):
        root = LIB_ROOT / benchmark_id
        yaml_path = CATALOG_ROOT / f'{benchmark_id}.yaml'
        lib_yaml_path = root / 'aisb_catalog.yaml'
        if not root.exists() or not yaml_path.exists() or not lib_yaml_path.exists():
            results.append({'id': benchmark_id, 'status': 'skipped_missing_files'})
            continue
        bundle = CONTEXT_ROOT / benchmark_id
        bundle.mkdir(parents=True, exist_ok=True)
        prompt = _build_prompt(root, yaml_path)
        (bundle / 'prompt.txt').write_text(prompt)
        try:
            raw = _call_claude_cli(prompt, model=args.model)
            (bundle / 'response.txt').write_text(raw)
            yaml_text = _extract_yaml_text(raw)
            try:
                validated = _validate_yaml(yaml_text, validation_name=f'claude_code_{benchmark_id}')
            except Exception as first_exc:
                (bundle / 'validate_error.txt').write_text(repr(first_exc))
                repaired_raw = _repair_yaml_with_claude_cli(yaml_text, model=args.model)
                (bundle / 'repair_response.txt').write_text(repaired_raw)
                yaml_text = _extract_yaml_text(repaired_raw)
                validated = _validate_yaml(yaml_text, validation_name=f'claude_code_repair_{benchmark_id}')
            (bundle / 'validated.json').write_text(json.dumps(validated, indent=2, ensure_ascii=False))
            if not args.dry_run:
                yaml_path.write_text(yaml_text)
                lib_yaml_path.write_text(yaml_text)
            results.append({'id': benchmark_id, 'status': 'ok', 'model': args.model})
        except Exception as exc:
            (bundle / 'error.txt').write_text(repr(exc))
            results.append({'id': benchmark_id, 'status': 'error', 'error': repr(exc)})
    print(json.dumps({'total': len(results), 'results': results}, ensure_ascii=False, indent=2))
    return 0 if all(item['status'] == 'ok' for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
