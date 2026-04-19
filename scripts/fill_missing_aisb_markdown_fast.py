#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

LIB = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
PDF_DIR = Path('/tmp/aisb_pdfs')
STATUS = Path('/tmp/aisb_mineru/status.json')

items = json.loads(STATUS.read_text()).get('items', {}) if STATUS.exists() else {}
generated = []
for entry in sorted(LIB.iterdir()):
    if not (entry.is_dir() and entry.name.startswith('aisb.')):
        continue
    md = entry / 'latex.md'
    if md.exists():
        continue
    pdf = PDF_DIR / f'{entry.name}.pdf'
    if not pdf.exists():
        continue
    item = items.get(entry.name, {})
    reader = PdfReader(str(pdf))
    parts = [
        '# Local Text Extraction',
        '',
        f'- benchmark_id: `{entry.name}`',
        f'- pdf_path: `{pdf}`',
    ]
    src = item.get('pdf_source_url') or item.get('source_url')
    if src:
        parts.append(f'- source_url: `{src}`')
    parts.extend(['', '---', ''])
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or '').strip()
        parts.append(f'## Page {idx}')
        parts.append('')
        parts.append(text if text else '[no extractable text]')
        parts.append('')
    md.write_text('\n'.join(parts).strip() + '\n')
    generated.append(entry.name)
print(json.dumps({'generated_count': len(generated), 'generated': generated[:30]}, ensure_ascii=False, indent=2))
