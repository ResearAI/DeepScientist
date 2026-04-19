#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
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
CONTEXT_ROOT = REPO_ROOT / '.tmp' / 'aisb_yaml_rewrite'

KEYWORD_PATTERNS = [
    r'\bA100\b', r'\bH100\b', r'\bV100\b', r'\bRTX\b', r'\bGPU\b', r'\bCUDA\b',
    r'\bGB\b', r'\bTB\b', r'\bRAM\b', r'\bVRAM\b', r'\bhours?\b', r'\bdays?\b',
    r'\bminutes?\b', r'\bdataset\b', r'\bdownload\b', r'\btrain(?:ing)?\b',
    r'\beval(?:uation)?\b', r'\bbatch size\b', r'\bepochs?\b', r'\bmemory\b',
    r'\bdisk\b', r'\bthroughput\b', r'\btime\b', r'\bbenchmark\b',
]

SYSTEM_PROMPT = textwrap.dedent('''\
You rewrite BenchStore YAML entries for DeepScientist.

Hard requirements:
- Output YAML only. No fences. No prose.
- Preserve factual correctness. Use only provided evidence from current YAML, README, AGENTS, code snippets, and latex.md.
- Do not mention AutoSOTA anywhere.
- Keep existing ids and routing fields stable unless the provided evidence clearly contradicts them.
- Make `one_line` and `task_description` substantially clearer, more operational, and more specific.
- Add or improve: `snapshot_status`, `support_level`, `primary_outputs`, `launch_profiles`, `dataset_download`, `credential_requirements`, `resources`, `environment`, `risk_flags`, `risk_notes`, `recommended_when`, `not_recommended_when` when evidence allows.
- For time / hardware / storage estimates, prefer explicit evidence from README / paper / code. If exact values are unknown, keep conservative ranges and explain uncertainty in notes rather than inventing precision.
- Keep YAML valid for DeepScientist BenchStore.
- `download`, `display`, and `image_path` should usually be preserved unless clearly broken.
- `paper.url` should point to the best paper landing page or proceedings page supported by the evidence.
- Use concise but detailed wording. Prefer direct, operational language.
- `credential_requirements.items` must be a list of short strings, not objects.
- `dataset_download.sources` may be a list of objects with `kind`, `url`, `access`, `note`.
- `launch_profiles` entries should have `id`, `label`, `description`.
- Resource specs should use numeric fields: `cpu_cores`, `ram_gb`, `disk_gb`, `gpu_count`, `gpu_vram_gb`.
''')

USER_TEMPLATE = textwrap.dedent('''\
Rewrite this benchmark YAML into a clearer and more detailed BenchStore entry.

Target style guidance:
- Make the task understandable to someone deciding whether to run it.
- Explain the real execution route, expected outputs, data route, hardware route, and major caveats.
- Be explicit about whether the route is self-contained or depends on external evaluators / datasets / credentials.
- Keep the output within the existing DeepScientist BenchStore schema.

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

Keyword evidence extracted from README / latex / code:
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

Return only the rewritten YAML.
''')

ID_EXAMPLE = textwrap.dedent('''\
id: aisb.t3.043_vhm
name: VHM
version: 0.1.0
one_line: Two-stage remote-sensing vision-language benchmark with large-scale pretraining and external evaluation.
task_description: >
  This packaged benchmark covers two-stage training and downstream evaluation for a 7B
  remote-sensing vision-language model. The task is to pretrain on VersaD, run supervised
  fine-tuning on instruction data, and evaluate remote-sensing understanding tasks through
  the RSEvalKit stack.
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
    description: Run the pretrain and SFT routes without external evaluation.
  - id: paper_faithful
    label: Paper-Faithful
    description: Run training and then evaluate through RSEvalKit.
dataset_download:
  primary_method: mixed
  sources:
    - kind: huggingface
      url: https://...
      access: public
      note: VersaD corpus
  notes:
    - Hundreds of GB after extraction.
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
  key_packages: []
  notes: []
risk_flags:
  - external_eval_dependency
  - large_dataset_route
risk_notes:
  - RSEvalKit is not bundled in the local snapshot.
recommended_when: ...
not_recommended_when: ...
paper: {}
display: {}
image_path: ...
''')


def _read_text(path: Path, *, limit: int | None = None) -> str:
    if not path.exists():
        return ''
    text = path.read_text(errors='ignore')
    return text if limit is None else text[:limit]


def _top_tree(root: Path, *, max_items: int = 120, max_depth: int = 2) -> str:
    lines: list[str] = []
    count = 0
    for path in sorted(root.rglob('*')):
        if count >= max_items:
            break
        rel = path.relative_to(root)
        if len(rel.parts) > max_depth:
            continue
        if '.git' in rel.parts or '__pycache__' in rel.parts:
            continue
        marker = '/' if path.is_dir() else ''
        lines.append(str(rel) + marker)
        count += 1
    return '\n'.join(lines)


def _extract_first_read_paths(agents_text: str) -> list[str]:
    results: list[str] = []
    for line in agents_text.splitlines():
        match = re.match(r'\s*\d+\.\s+`([^`]+)`', line)
        if match:
            results.append(match.group(1).strip())
    return results


def _selected_code_snippets(root: Path, agents_text: str, *, max_files: int = 8, chars_per_file: int = 2400) -> str:
    snippets: list[str] = []
    for rel in _extract_first_read_paths(agents_text):
        if rel.endswith(('.md', '.yaml', '.json')):
            continue
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        text = _read_text(path, limit=chars_per_file)
        snippets.append(f'### {rel}\n{text}')
        if len(snippets) >= max_files:
            break
    return '\n\n'.join(snippets)


def _keyword_lines(*texts: str, max_lines: int = 120) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    combined = '\n'.join(texts)
    for raw in combined.splitlines():
        line = raw.strip()
        if not line or line in seen:
            continue
        if any(re.search(pattern, line, flags=re.I) for pattern in KEYWORD_PATTERNS):
            seen.add(line)
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return '\n'.join(lines)


def _extract_yaml_text(response_text: str) -> str:
    match = re.search(r'```yaml\s*(.*?)```', response_text, flags=re.S | re.I)
    if match:
        return match.group(1).strip() + '\n'
    match = re.search(r'```\s*(.*?)```', response_text, flags=re.S)
    if match:
        return match.group(1).strip() + '\n'
    return response_text.strip() + '\n'


def _validate_yaml(yaml_text: str, *, validation_name: str) -> dict[str, Any]:
    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict):
        raise ValueError('Model output is not a YAML object.')
    temp_path = REPO_ROOT / f'.tmp_{validation_name}.yaml'
    temp_path.write_text(yaml_text)
    try:
        service = BenchStoreService(WORKSPACE_HOME, repo_root=REPO_ROOT)
        return service._load_entry_file(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _build_prompt(root: Path, yaml_path: Path) -> str:
    readme_text = _read_text(root / 'README.md', limit=14000)
    agents_text = _read_text(root / 'AGENTS.md', limit=12000)
    latex_text = _read_text(root / 'latex.md', limit=22000)
    current_yaml = _read_text(yaml_path)
    keyword_evidence = _keyword_lines(readme_text, agents_text, latex_text, _selected_code_snippets(root, agents_text))
    tree_summary = _top_tree(root)
    code_snippets = _selected_code_snippets(root, agents_text)
    return USER_TEMPLATE.format(
        id_example=ID_EXAMPLE.strip(),
        current_yaml=current_yaml.strip(),
        readme_excerpt=readme_text.strip(),
        agents_excerpt=agents_text.strip(),
        latex_excerpt=latex_text.strip(),
        keyword_evidence=keyword_evidence.strip(),
        tree_summary=tree_summary.strip(),
        code_snippets=code_snippets.strip(),
    )


def _client(api_key: str, base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, base_url=base_url, max_retries=2)


def _call_model(client: anthropic.Anthropic, *, model: str, prompt: str, max_output_tokens: int) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_output_tokens,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': prompt}],
    )
    texts = [block.text for block in response.content if getattr(block, 'type', None) == 'text']
    return '\n'.join(texts).strip()


def _bench_ids(ids_arg: str | None) -> list[str]:
    if ids_arg:
        return [item.strip() for item in ids_arg.split(',') if item.strip()]
    return [path.stem for path in sorted(CATALOG_ROOT.glob('aisb.*.yaml'))]


def main() -> int:
    parser = argparse.ArgumentParser(description='Rewrite AISB BenchStore YAML entries with Claude.')
    parser.add_argument('--ids', type=str, default='')
    parser.add_argument('--model', type=str, default=os.environ.get('ANTHROPIC_MODEL', DEFAULT_MODEL))
    parser.add_argument('--base-url', type=str, default=os.environ.get('ANTHROPIC_BASE_URL', DEFAULT_BASE_URL))
    parser.add_argument('--api-key', type=str, default=os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN') or DEFAULT_API_KEY)
    parser.add_argument('--max-output-tokens', type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    client = _client(args.api_key, args.base_url)
    CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for benchmark_id in _bench_ids(args.ids or None):
        root = LIB_ROOT / benchmark_id
        yaml_path = CATALOG_ROOT / f'{benchmark_id}.yaml'
        lib_yaml_path = root / 'aisb_catalog.yaml'
        if not root.exists() or not yaml_path.exists() or not lib_yaml_path.exists():
            results.append({'id': benchmark_id, 'status': 'skipped_missing_files'})
            continue
        prompt = _build_prompt(root, yaml_path)
        bundle_dir = CONTEXT_ROOT / benchmark_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / 'prompt.txt').write_text(prompt)
        try:
            raw = _call_model(client, model=args.model, prompt=prompt, max_output_tokens=args.max_output_tokens)
            (bundle_dir / 'response.txt').write_text(raw)
            yaml_text = _extract_yaml_text(raw)
            validated = _validate_yaml(yaml_text, validation_name=f'validate_{benchmark_id}')
            (bundle_dir / 'validated.json').write_text(json.dumps(validated, indent=2, ensure_ascii=False))
            if not args.dry_run:
                yaml_path.write_text(yaml_text)
                lib_yaml_path.write_text(yaml_text)
            results.append({'id': benchmark_id, 'status': 'ok', 'model': args.model})
        except Exception as exc:
            results.append({'id': benchmark_id, 'status': 'error', 'error': repr(exc)})
            (bundle_dir / 'error.txt').write_text(repr(exc))

    print(json.dumps({'total': len(results), 'results': results}, ensure_ascii=False, indent=2))
    return 0 if all(item['status'] == 'ok' for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
