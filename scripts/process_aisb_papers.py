#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import yaml
from playwright.async_api import async_playwright

DEFAULT_CATALOG_ROOT = Path("/ssdwork/deepscientist/DeepScientist/AISB/catalog")
DEFAULT_LIBRARY_ROOT = Path("/ssdwork/deepscientist/AISB_AUTOSOTA")
DEFAULT_PDF_DIR = Path("/tmp/aisb_pdfs")
DEFAULT_MINERU_DIR = Path("/tmp/aisb_mineru")
USER_AGENT = "DeepScientist AISB paper pipeline/1.0"
MINERU_BASE = "https://mineru.net/api/v4"

SOURCE_URL_OVERRIDES: dict[str, list[str]] = {
    "aisb.t3.004_decentralattn": ["https://arxiv.org/abs/2602.18473"],
    "aisb.t3.031_circuitstability": ["https://arxiv.org/abs/2505.24731"],
    "aisb.t3.042_xpatch": ["https://arxiv.org/pdf/2412.17323"],
    "aisb.t3.048_proxyspex": ["https://arxiv.org/abs/2410.01649"],
    "aisb.t3.051_flashtp": [
        "https://raw.githubusercontent.com/mlresearch/v267/main/assets/lee25l/lee25l.pdf",
        "https://proceedings.mlr.press/v267/lee25l.html",
    ],
    "aisb.t3.057_mdreid": ["https://arxiv.org/abs/2510.23301v2"],
    "aisb.t3.069_treehfd": ["https://arxiv.org/abs/2510.24815v1"],
    "aisb.t3.075_treeslicedentropy": [
        "https://openreview.net/pdf/14c70262ff77b938cee1c6c5eb63f76e044fc1f3.pdf",
        "https://openreview.net/pdf?id=41ZbysfW4h",
    ],
    "aisb.t3.076_aanet": ["https://arxiv.org/abs/2506.05768"],
    "aisb.t3.078_conformalanomaly": [
        "https://raw.githubusercontent.com/mlresearch/v267/main/assets/zhang25dn/zhang25dn.pdf",
        "https://proceedings.mlr.press/v267/zhang25dn.html",
    ],
    "aisb.t3.082_onlinellmrouting": ["https://arxiv.org/abs/2509.02718v3"],
    "aisb.t3.080_latentscorereweight": [
        "https://raw.githubusercontent.com/mlresearch/v267/main/assets/tong25c/tong25c.pdf",
        "https://proceedings.mlr.press/v267/tong25c.html",
    ],
    "aisb.t3.084_ift": ["https://haoxuanli-pku.github.io/papers/NeurIPS%2025%20-%20Towards%20Accurate%20Time%20Series%20Forecasting%20via%20Implicit%20Decoding.pdf"],
    "aisb.t3.087_moses": ["https://arxiv.org/abs/2510.21453v1"],
    "aisb.t3.091_timeawarecausal": ["https://arxiv.org/abs/2506.17718v2"],
    "aisb.t3.094_boundre": [
        "https://raw.githubusercontent.com/mlresearch/v267/main/assets/bang25a/bang25a.pdf",
        "https://proceedings.mlr.press/v267/bang25a.html",
    ],
    "aisb.t3.093_fedwmsam": ["https://openreview.net/pdf?id=nutryQ3SBf"],
    "aisb.t3.096_m3svm": ["https://arxiv.org/abs/2510.04027"],
    "aisb.t3.099_ollalanding": ["https://arxiv.org/abs/2510.22044v1"],
    "aisb.t3.061_hsgkn": [
        "https://openreview.net/pdf/5a1a8edf9d94e51f8c947f9d0e98cb0c4b491c37.pdf",
        "https://openreview.net/pdf?id=721bDIvjen",
    ],
    "aisb.t3.101_acia": ["https://arxiv.org/abs/2510.18052"],
}

YAML_FIXES: dict[str, dict[str, Any]] = {
    "aisb.t3.080_latentscorereweight": {
        "paper": {"venue": "ICML 2025", "url": "https://proceedings.mlr.press/v267/tong25c.html"}
    },
    "aisb.t3.093_fedwmsam": {
        "paper": {"url": "https://openreview.net/forum?id=75JiIa0fU1"}
    },
    "aisb.t3.099_ollalanding": {
        "paper": {"url": "https://arxiv.org/abs/2510.22044"}
    },
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))


def _extract_urls(text: str) -> list[str]:
    matches = re.findall(r'https?://[^\s<>"\')\]]+', text)
    return [match.rstrip(").,]}") for match in matches]


def _openreview_id(url: str) -> str | None:
    parsed = urlparse(url)
    if "openreview.net" not in parsed.netloc:
        return None
    query = parse_qs(parsed.query)
    values = query.get("id")
    if values:
        return values[0]
    return None


def _normalized_candidates(url: str) -> list[str]:
    if not url:
        return []
    normalized: list[str] = []
    parsed = urlparse(url)
    value = url.rstrip()
    if "arxiv.org/abs/" in value:
        normalized.append(value.replace("/abs/", "/pdf/") + ".pdf")
        normalized.append(value)
    elif "arxiv.org/pdf/" in value:
        normalized.append(value if value.endswith(".pdf") else f"{value}.pdf")
    elif "openreview.net" in parsed.netloc:
        paper_id = _openreview_id(value)
        if paper_id:
            normalized.extend([
                f"https://openreview.net/pdf?id={paper_id}",
                f"https://openreview.net/attachment?id={paper_id}&name=pdf",
                f"https://openreview.net/forum?id={paper_id}",
            ])
        else:
            normalized.append(value)
    elif "ojs.aaai.org" in parsed.netloc and "/article/view/" in value:
        normalized.append(value)
    elif "aclanthology.org" in parsed.netloc and not value.endswith(".pdf"):
        normalized.extend([value.rstrip("/") + ".pdf", value])
    elif value.endswith(".pdf"):
        normalized.append(value)
    elif value.endswith("-Abstract-Conference.html"):
        normalized.append(value.replace("-Abstract-Conference.html", "-Paper-Conference.pdf"))
        normalized.append(value)
    else:
        normalized.append(value)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in normalized:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _readme_candidates(entry_root: Path) -> list[str]:
    readme = entry_root / "README.md"
    if not readme.exists():
        return []
    text = readme.read_text(errors="ignore")
    urls = []
    for url in _extract_urls(text):
        urls.extend(_normalized_candidates(url))
    return urls


def _candidate_urls(benchmark_id: str, catalog: dict[str, Any], entry_root: Path) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for source in SOURCE_URL_OVERRIDES.get(benchmark_id, []):
        for url in _normalized_candidates(source):
            if url not in seen:
                seen.add(url)
                ordered.append(url)
    paper_url = str(((catalog.get("paper") or {}).get("url")) or "").strip()
    for url in _normalized_candidates(paper_url):
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    for url in _readme_candidates(entry_root):
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _response_bytes(resp: requests.Response) -> bytes | None:
    if resp.status_code != 200:
        return None
    content = resp.content
    if content[:4] == b"%PDF":
        return content
    if "application/pdf" in (resp.headers.get("Content-Type") or ""):
        return content
    return None


def _html_to_pdf_url(source_url: str, text: str) -> str | None:
    patterns = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'href=["\']([^"\']+\.pdf)["\']',
        r'https?://[^"\']+\.pdf',
        r'href=["\']([^"\']+/article/download/[^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        href = match.group(1) if match.groups() else match.group(0)
        return urljoin(source_url, href)
    return None




def _download_openreview_with_playwright(source_url: str) -> bytes | None:
    async def _run() -> bytes | None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            download = None
            try:
                async with page.expect_download() as dl_info:
                    try:
                        await page.goto(source_url, wait_until="commit", timeout=120000)
                    except Exception:
                        pass
                download = await dl_info.value
                temp_path = await download.path()
                blob = Path(temp_path).read_bytes() if temp_path else None
            finally:
                await browser.close()
            if blob and blob[:4] == b"%PDF":
                return blob
            return None
    try:
        return asyncio.run(_run())
    except Exception:
        return None

def _download_pdf(session: requests.Session, source_url: str) -> tuple[bytes | None, str | None]:
    if "openreview.net/" in source_url:
        blob = _download_openreview_with_playwright(source_url)
        if blob is not None:
            return blob, None
    try:
        response = session.get(source_url, timeout=90, allow_redirects=True)
    except requests.RequestException as exc:
        return None, str(exc)
    blob = _response_bytes(response)
    if blob is not None:
        return blob, None
    text = response.text if "text" in (response.headers.get("Content-Type") or "") else ""
    if not text:
        return None, f"http_{response.status_code}"
    pdf_url = _html_to_pdf_url(source_url, text)
    if not pdf_url:
        return None, "no_pdf_link"
    try:
        pdf_response = session.get(pdf_url, timeout=120, allow_redirects=True)
    except requests.RequestException as exc:
        return None, str(exc)
    blob = _response_bytes(pdf_response)
    if blob is not None:
        return blob, None
    return None, f"http_{pdf_response.status_code}"


def _save_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _load_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": {}}
    return json.loads(path.read_text())


def _write_latex_md(entry_root: Path, md_text: str) -> Path:
    target = entry_root / "latex.md"
    target.write_text(md_text)
    return target


def _extract_zip_outputs(zip_bytes: bytes, benchmark_id: str, pdf_dir: Path, mineru_dir: Path, entry_root: Path) -> dict[str, str | None]:
    cache_root = mineru_dir / "extracted" / benchmark_id
    cache_root.mkdir(parents=True, exist_ok=True)
    zip_path = mineru_dir / "zips" / f"{benchmark_id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(zip_bytes)

    md_text: str | None = None
    full_tex_path: Path | None = None
    origin_pdf_path = pdf_dir / f"{benchmark_id}.pdf"

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            blob = archive.read(member)
            extracted_path = cache_root / member
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_bytes(blob)
            if name == "full.md":
                md_text = blob.decode("utf-8", errors="ignore")
            elif name == "full.tex":
                full_tex_path = extracted_path
            elif name.endswith("_origin.pdf") or name == "origin.pdf":
                origin_pdf_path.write_bytes(blob)
    if md_text is None and full_tex_path is not None:
        md_text = full_tex_path.read_text(errors="ignore")
    latex_md_path = _write_latex_md(entry_root, md_text or "")
    return {
        "zip_path": str(zip_path),
        "origin_pdf_path": str(origin_pdf_path) if origin_pdf_path.exists() else None,
        "latex_md_path": str(latex_md_path),
        "full_tex_path": str(full_tex_path) if full_tex_path and full_tex_path.exists() else None,
    }


def _mineru_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _submit_upload_batch(session: requests.Session, token: str, items: list[dict[str, Any]]) -> str:
    payload = {
        "files": [{"name": Path(item["pdf_path"]).name, "data_id": item["id"]} for item in items],
        "model_version": "vlm",
        "extra_formats": ["latex"],
    }
    response = session.post(f"{MINERU_BASE}/file-urls/batch", headers=_mineru_headers(token), json=payload, timeout=120)
    response.raise_for_status()
    body = response.json()["data"]
    for item, upload_url in zip(items, body["file_urls"], strict=True):
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--http1.1", "-T", str(Path(item["pdf_path"])), upload_url], check=True)
    return body["batch_id"]


def _submit_url_batch(session: requests.Session, token: str, items: list[dict[str, Any]]) -> str:
    payload = {
        "files": [{"url": item["source_url"], "data_id": item["id"]} for item in items],
        "model_version": "vlm",
        "extra_formats": ["latex"],
    }
    response = session.post(f"{MINERU_BASE}/extract/task/batch", headers=_mineru_headers(token), json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["data"]["batch_id"]


def _poll_batch(session: requests.Session, token: str, batch_id: str) -> dict[str, Any]:
    response = session.get(f"{MINERU_BASE}/extract-results/batch/{batch_id}", headers={"Authorization": f"Bearer {token}"}, timeout=120)
    response.raise_for_status()
    data = response.json()["data"]
    return {item["data_id"]: item for item in (data.get("extract_result") or [])}


def _download_phase(session: requests.Session, entries: list[dict[str, Any]], pdf_dir: Path, status: dict[str, Any], status_path: Path) -> None:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        benchmark_id = entry["id"]
        item_state = status["items"].setdefault(benchmark_id, {})
        pdf_path = pdf_dir / f"{benchmark_id}.pdf"
        entry["pdf_path"] = str(pdf_path)
        candidates = _candidate_urls(benchmark_id, entry["catalog"], entry["entry_root"])
        item_state["candidate_urls"] = candidates
        if pdf_path.exists() and pdf_path.read_bytes()[:4] == b"%PDF":
            item_state["download_status"] = "ok"
            item_state["pdf_path"] = str(pdf_path)
            _save_status(status_path, status)
            continue
        item_state["download_attempts"] = []
        for url in candidates:
            blob, error = _download_pdf(session, url)
            item_state["download_attempts"].append({"url": url, "error": error})
            if blob is None:
                continue
            pdf_path.write_bytes(blob)
            item_state["download_status"] = "ok"
            item_state["pdf_source_url"] = url
            item_state["pdf_path"] = str(pdf_path)
            break
        else:
            item_state["download_status"] = "pending_mineru_url"
        _save_status(status_path, status)


def _await_batch(session: requests.Session, token: str, batch_id: str, expected_ids: list[str], pdf_dir: Path, mineru_dir: Path, entry_index: dict[str, dict[str, Any]], status: dict[str, Any], status_path: Path, sleep_seconds: int) -> None:
    pending = set(expected_ids)
    while pending:
        results = _poll_batch(session, token, batch_id)
        for benchmark_id in list(pending):
            item = results.get(benchmark_id)
            if not item:
                continue
            item_state = status["items"].setdefault(benchmark_id, {})
            state = item.get("state")
            item_state["mineru_state"] = state
            item_state["mineru_err_msg"] = item.get("err_msg")
            item_state["mineru_progress"] = item.get("extract_progress")
            if state == "done":
                zip_url = item.get("full_zip_url")
                zip_blob = session.get(zip_url, timeout=600).content
                outputs = _extract_zip_outputs(zip_blob, benchmark_id, pdf_dir, mineru_dir, entry_index[benchmark_id]["entry_root"])
                item_state["mineru_outputs"] = outputs
                item_state["mineru_state"] = "done"
                item_state["download_status"] = "ok"
                item_state["pdf_path"] = outputs.get("origin_pdf_path") or item_state.get("pdf_path")
                pending.remove(benchmark_id)
            elif state == "failed":
                pending.remove(benchmark_id)
            _save_status(status_path, status)
        if pending:
            time.sleep(sleep_seconds)


def _mineru_ready_urls(item_state: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    preferred = item_state.get("pdf_source_url")
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(item_state.get("candidate_urls") or [])
    for url in candidates:
        if not isinstance(url, str):
            continue
        value = url.strip()
        if not value or value in seen:
            continue
        parsed = value.lower()
        if (
            value.endswith('.pdf')
            or '/pdf?' in parsed
            or '/pdf/' in parsed
            or 'name=pdf' in parsed
        ):
            seen.add(value)
            ordered.append(value)
    return ordered


def _chunked(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _mineru_phase(session: requests.Session, token: str | None, entries: list[dict[str, Any]], pdf_dir: Path, mineru_dir: Path, status: dict[str, Any], status_path: Path, chunk_size: int, sleep_seconds: int) -> None:
    if not token:
        return

    entry_index = {entry["id"]: entry for entry in entries}
    upload_items: list[dict[str, Any]] = []
    url_items: list[dict[str, Any]] = []

    for entry in entries:
        benchmark_id = entry["id"]
        item_state = status["items"].setdefault(benchmark_id, {})
        if (entry["entry_root"] / "latex.md").exists():
            item_state["mineru_state"] = "done"
            _save_status(status_path, status)
            continue
        candidates = item_state.get("candidate_urls") or _candidate_urls(benchmark_id, entry["catalog"], entry["entry_root"])
        item_state["candidate_urls"] = candidates
        mineru_urls = _mineru_ready_urls(item_state)
        if mineru_urls:
            item_state["mineru_mode"] = "url"
            item_state["source_url"] = mineru_urls[0]
            url_items.append({"id": benchmark_id, "source_url": mineru_urls[0]})
        else:
            pdf_path = Path(entry["pdf_path"])
            if pdf_path.exists() and pdf_path.read_bytes()[:4] == b"%PDF":
                upload_items.append({"id": benchmark_id, "pdf_path": str(pdf_path)})
                item_state["mineru_mode"] = "upload"
            else:
                item_state["mineru_state"] = "failed"
                item_state["mineru_err_msg"] = "no_candidate_url"
                _save_status(status_path, status)
                continue
        _save_status(status_path, status)

    for chunk in _chunked(upload_items, chunk_size):
        batch_id = _submit_upload_batch(session, token, chunk)
        for item in chunk:
            state = status["items"].setdefault(item["id"], {})
            state["mineru_batch_id"] = batch_id
        _save_status(status_path, status)
        _await_batch(session, token, batch_id, [item["id"] for item in chunk], pdf_dir, mineru_dir, entry_index, status, status_path, sleep_seconds)

    retry_queue = url_items[:]
    while retry_queue:
        chunk = retry_queue[:chunk_size]
        retry_queue = retry_queue[chunk_size:]
        batch_id = _submit_url_batch(session, token, chunk)
        for item in chunk:
            state = status["items"].setdefault(item["id"], {})
            state["mineru_batch_id"] = batch_id
            state["source_url"] = item["source_url"]
        _save_status(status_path, status)
        _await_batch(session, token, batch_id, [item["id"] for item in chunk], pdf_dir, mineru_dir, entry_index, status, status_path, sleep_seconds)
        for item in chunk:
            benchmark_id = item["id"]
            item_state = status["items"].setdefault(benchmark_id, {})
            if item_state.get("mineru_state") != "failed":
                continue
            candidates = _mineru_ready_urls(item_state)
            current = item_state.get("source_url")
            try:
                index = candidates.index(current)
            except ValueError:
                index = 0
            next_index = index + 1
            if next_index < len(candidates):
                next_url = candidates[next_index]
                item_state["source_url"] = next_url
                retry_queue.append({"id": benchmark_id, "source_url": next_url})
            _save_status(status_path, status)

    upload_fallback: list[dict[str, Any]] = []
    for entry in entries:
        benchmark_id = entry["id"]
        item_state = status["items"].setdefault(benchmark_id, {})
        pdf_path = Path(entry["pdf_path"])
        if item_state.get("mineru_state") == "done":
            continue
        if not pdf_path.exists() or pdf_path.read_bytes()[:4] != b"%PDF":
            continue
        upload_fallback.append({"id": benchmark_id, "pdf_path": str(pdf_path)})
        item_state["mineru_mode"] = "upload"
        _save_status(status_path, status)

    for chunk in _chunked(upload_fallback, chunk_size):
        batch_id = _submit_upload_batch(session, token, chunk)
        for item in chunk:
            state = status["items"].setdefault(item["id"], {})
            state["mineru_batch_id"] = batch_id
            state["mineru_mode"] = "upload"
        _save_status(status_path, status)
        _await_batch(session, token, batch_id, [item["id"] for item in chunk], pdf_dir, mineru_dir, entry_index, status, status_path, sleep_seconds)


def _apply_yaml_fixes(catalog_root: Path, library_root: Path) -> None:
    for benchmark_id, patch in YAML_FIXES.items():
        catalog_path = catalog_root / f"{benchmark_id}.yaml"
        entry_catalog_path = library_root / benchmark_id / "aisb_catalog.yaml"
        for path in (catalog_path, entry_catalog_path):
            payload = _load_yaml(path)
            paper = payload.setdefault("paper", {})
            for key, value in (patch.get("paper") or {}).items():
                paper[key] = value
            _write_yaml(path, payload)


def _collect_entries(catalog_root: Path, library_root: Path, only_ids: set[str] | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for catalog_path in sorted(catalog_root.glob("aisb.*.yaml")):
        benchmark_id = catalog_path.stem
        if only_ids and benchmark_id not in only_ids:
            continue
        entry_root = library_root / benchmark_id
        if not entry_root.exists():
            continue
        entries.append({
            "id": benchmark_id,
            "catalog_path": catalog_path,
            "entry_root": entry_root,
            "catalog": _load_yaml(catalog_path),
        })
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Download AISB benchmark papers and process them through MinerU.")
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOG_ROOT)
    parser.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--mineru-dir", type=Path, default=DEFAULT_MINERU_DIR)
    parser.add_argument("--chunk-size", type=int, default=6)
    parser.add_argument("--sleep-seconds", type=int, default=15)
    parser.add_argument("--ids", type=str, default="")
    parser.add_argument("--skip-yaml-fixes", action="store_true")
    args = parser.parse_args()

    if not args.skip_yaml_fixes:
        _apply_yaml_fixes(args.catalog_root, args.library_root)

    only_ids = {item.strip() for item in args.ids.split(",") if item.strip()} or None
    entries = _collect_entries(args.catalog_root, args.library_root, only_ids)
    status_path = args.mineru_dir / "status.json"
    status = _load_status(status_path)

    session = _session()
    _download_phase(session, entries, args.pdf_dir, status, status_path)
    token = os.environ.get("MINERU_TOKEN")
    _mineru_phase(session, token, entries, args.pdf_dir, args.mineru_dir, status, status_path, max(args.chunk_size, 1), max(args.sleep_seconds, 5))
    _save_status(status_path, status)


if __name__ == "__main__":
    main()
