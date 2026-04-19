#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf4llm
from pypdf import PdfReader

DEFAULT_LIBRARY_ROOT = Path('/ssdwork/deepscientist/AISB_AUTOSOTA')
DEFAULT_PDF_DIR = Path('/tmp/aisb_pdfs')
DEFAULT_STATUS_PATH = Path('/tmp/aisb_mineru/status.json')


def _load_status(path: Path) -> dict:
    if not path.exists():
        return {'items': {}}
    return json.loads(path.read_text())


def _plain_text_fallback(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ''
        parts.append(f'## Page {i}\n\n{text.strip()}')
    return '\n\n'.join(parts)


def _build_header(benchmark_id: str, pdf_path: Path, item: dict) -> str:
    lines = [
        '# Local Markdown Extraction',
        '',
        f'- benchmark_id: `{benchmark_id}`',
        f'- pdf_path: `{pdf_path}`',
    ]
    source = item.get('pdf_source_url') or item.get('source_url')
    if source:
        lines.append(f'- source_url: `{source}`')
    mineru_state = item.get('mineru_state')
    if mineru_state:
        lines.append(f'- mineru_state: `{mineru_state}`')
    err = item.get('mineru_err_msg')
    if err:
        lines.append(f'- mineru_error: `{err}`')
    lines.extend(['', '> This `latex.md` was generated locally from the saved PDF because MinerU output was missing or incomplete.', '', '---', ''])
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Fill missing AISB latex.md files from local PDFs.')
    parser.add_argument('--library-root', type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument('--pdf-dir', type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument('--status-path', type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    status = _load_status(args.status_path).get('items', {})
    generated = []
    failed = []

    for entry in sorted(args.library_root.iterdir()):
        if not (entry.is_dir() and entry.name.startswith('aisb.')):
            continue
        benchmark_id = entry.name
        md_path = entry / 'latex.md'
        if md_path.exists() and not args.force:
            continue
        pdf_path = args.pdf_dir / f'{benchmark_id}.pdf'
        if not pdf_path.exists():
            failed.append({'id': benchmark_id, 'error': 'missing_pdf'})
            continue
        item = status.get(benchmark_id, {})
        try:
            body = pymupdf4llm.to_markdown(str(pdf_path))
            if not isinstance(body, str) or not body.strip():
                body = _plain_text_fallback(pdf_path)
            content = _build_header(benchmark_id, pdf_path, item) + body.strip() + '\n'
            md_path.write_text(content)
            generated.append(benchmark_id)
        except Exception as exc:
            try:
                body = _plain_text_fallback(pdf_path)
                content = _build_header(benchmark_id, pdf_path, item) + body.strip() + '\n'
                md_path.write_text(content)
                generated.append(benchmark_id)
            except Exception as inner_exc:
                failed.append({'id': benchmark_id, 'error': repr(exc), 'fallback_error': repr(inner_exc)})

    print(json.dumps({'generated_count': len(generated), 'failed_count': len(failed), 'generated': generated[:20], 'failed': failed[:20]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
