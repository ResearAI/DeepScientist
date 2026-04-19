from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import yaml
from PIL import Image, ImageOps
from PIL import ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
AUTOSOTA_ROOT = WORKSPACE_ROOT / "AutoSOTA-main"
CATALOG_ROOT = REPO_ROOT / "AISB" / "catalog"
IMAGE_ROOT = WORKSPACE_ROOT / "AISB" / "image"

IMAGE_ROOT.mkdir(parents=True, exist_ok=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _yaml_paths(selection: Iterable[str] | None = None) -> list[Path]:
    paths = sorted(CATALOG_ROOT.glob("aisb.t3.[0-9][0-9][0-9]_*.yaml"))
    if not selection:
        return paths
    wanted = set(selection)
    result: list[Path] = []
    for path in paths:
        stem = path.stem
        m = re.search(r"aisb\.t3\.(\d{3})_", stem)
        if not m:
            continue
        if m.group(1) in wanted or path.name in wanted:
            result.append(path)
    return result


def _paper_dir(num: int) -> Path:
    return next(AUTOSOTA_ROOT.glob(f"paper-{num}-*"))


def _readme_path(paper_dir: Path) -> Path | None:
    for name in ("README.md", "Readme.md", "readme.md"):
        path = paper_dir / name
        if path.exists():
            return path
    return None


def _extract_image_refs(readme_text: str) -> list[str]:
    refs: list[str] = []
    patterns = [
        r'!\[[^\]]*\]\(([^)]+)\)',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, readme_text, flags=re.I):
            ref = match.group(1).strip()
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _looks_like_badge(ref: str) -> bool:
    lowered = ref.lower()
    return any(
        token in lowered
        for token in (
            "img.shields.io",
            "badge",
            "logo",
            "favicon",
        )
    )


def _load_image_bytes_from_ref(ref: str, paper_dir: Path) -> bytes | None:
    if _looks_like_badge(ref):
        return None
    if ref.startswith("http://") or ref.startswith("https://"):
        try:
            resp = requests.get(ref, timeout=20)
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:
            return None
        return None
    resolved = (paper_dir / ref).resolve()
    if resolved.exists() and resolved.is_file():
        try:
            return resolved.read_bytes()
        except Exception:
            return None
    return None


def _pick_readme_image(paper_dir: Path) -> tuple[bytes, str] | None:
    readme = _readme_path(paper_dir)
    if not readme:
        return None
    refs = _extract_image_refs(_read_text(readme))
    best: tuple[int, bytes, str] | None = None
    for ref in refs:
        blob = _load_image_bytes_from_ref(ref, paper_dir)
        if not blob:
            continue
        try:
            with Image.open(io.BytesIO(blob)) as img:
                area = img.width * img.height
        except Exception:
            continue
        if best is None or area > best[0]:
            best = (area, blob, ref)
    if best is None:
        return None
    return best[1], best[2]


def _pick_any_local_image(paper_dir: Path) -> tuple[bytes, str] | None:
    best: tuple[int, bytes, str] | None = None
    for path in sorted(paper_dir.rglob("*")):
        if not path.is_file():
            continue
        if len(path.relative_to(paper_dir).parts) > 3:
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            continue
        try:
            blob = path.read_bytes()
            if path.suffix.lower() == ".svg":
                continue
            with Image.open(io.BytesIO(blob)) as img:
                area = img.width * img.height
        except Exception:
            continue
        if best is None or area > best[0]:
            best = (area, blob, str(path.relative_to(paper_dir)))
    if best is None:
        return None
    return best[1], best[2]


def _candidate_pdf_urls(paper_url: str, readme_text: str) -> list[str]:
    urls: list[str] = []
    if paper_url:
        if "arxiv.org/abs/" in paper_url:
            urls.append(paper_url.replace("/abs/", "/pdf/") + ".pdf")
        elif "openreview.net/forum?id=" in paper_url:
            parsed = urlparse(paper_url)
            query = parsed.query
            urls.append(f"https://openreview.net/pdf?{query}")
        elif "aclanthology.org/" in paper_url and not paper_url.endswith(".pdf"):
            urls.append(paper_url.rstrip("/") + ".pdf")
        elif "ojs.aaai.org/" in paper_url and "/view/" in paper_url:
            # best-effort html parse later
            urls.append(paper_url)
        else:
            urls.append(paper_url)
    for match in re.finditer(r'https?://[^\s)>\]]+\.pdf', readme_text):
        url = match.group(0).rstrip(").,}]")
        if url not in urls:
            urls.append(url)
    return urls


def _download_pdf(urls: list[str]) -> bytes | None:
    for url in urls:
        try:
            if url.endswith(".pdf"):
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                    return resp.content
            else:
                resp = requests.get(url, timeout=30)
                if resp.status_code != 200:
                    continue
                text = resp.text
                m = re.search(r'https?://[^"\']+\.pdf', text)
                if not m:
                    m = re.search(r'href=["\']([^"\']+\.pdf)["\']', text, flags=re.I)
                    if m:
                        href = m.group(1)
                        pdf_url = urljoin(url, href)
                    else:
                        continue
                else:
                    pdf_url = m.group(0)
                pdf_resp = requests.get(pdf_url, timeout=30)
                if pdf_resp.status_code == 200 and pdf_resp.content[:4] == b"%PDF":
                    return pdf_resp.content
        except Exception:
            continue
    return None


def _extract_pdf_first_page(pdf_bytes: bytes) -> bytes | None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        pdf_path = td_path / "paper.pdf"
        jpg_prefix = td_path / "page"
        pdf_path.write_bytes(pdf_bytes)
        try:
            subprocess.run(
                ["pdftoppm", "-f", "1", "-singlefile", "-jpeg", "-jpegopt", "quality=90", str(pdf_path), str(jpg_prefix)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            jpg_path = jpg_prefix.with_suffix(".jpg")
            if jpg_path.exists():
                return jpg_path.read_bytes()
        except Exception:
            return None
    return None


def _fit_16_9(blob: bytes) -> bytes:
    with Image.open(io.BytesIO(blob)) as raw:
        image = raw.convert("RGB")
    target_ratio = 16 / 9
    width, height = image.size
    current_ratio = width / height
    if current_ratio > target_ratio:
        new_width = int(height * target_ratio)
        left = max((width - new_width) // 2, 0)
        image = image.crop((left, 0, left + new_width, height))
    elif current_ratio < target_ratio:
        new_height = int(width / target_ratio)
        top = max((height - new_height) // 2, 0)
        image = image.crop((0, top, width, top + new_height))

    size_candidates = [(960, 540), (800, 450), (704, 396), (640, 360), (576, 324), (512, 288)]
    quality_candidates = [82, 76, 70, 64, 58, 52, 46]
    for w, h in size_candidates:
        resized = ImageOps.fit(image, (w, h), method=Image.Resampling.LANCZOS)
        for quality in quality_candidates:
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
            payload = buf.getvalue()
            if len(payload) <= 100 * 1024:
                return payload
    buf = io.BytesIO()
    ImageOps.fit(image, (480, 270), method=Image.Resampling.LANCZOS).save(
        buf, format="JPEG", quality=42, optimize=True, progressive=True
    )
    return buf.getvalue()


def _render_title_card(title: str, subtitle: str) -> bytes:
    width, height = 960, 540
    image = Image.new("RGB", (width, height), (240, 235, 226))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    title_lines = wrap(title, title_font, width - 120)[:5]
    sub_lines = wrap(subtitle, sub_font, width - 120)[:4]

    y = 120
    for line in title_lines:
        draw.text((60, y), line, fill=(32, 38, 48), font=title_font)
        y += 52
    y += 20
    for line in sub_lines:
        draw.text((60, y), line, fill=(90, 96, 110), font=sub_font)
        y += 34

    draw.rounded_rectangle((56, 56, width - 56, height - 56), radius=28, outline=(180, 160, 130), width=3)
    draw.rectangle((60, 72, 260, 82), fill=(166, 124, 82))

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=78, optimize=True, progressive=True)
    return buf.getvalue()


def generate_for_yaml(yaml_path: Path) -> tuple[Path | None, str]:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    m = re.search(r"(\d{3})_", yaml_path.name)
    if not m:
        return None, "skip"
    num = int(m.group(1))
    paper_dir = _paper_dir(num)
    readme = _readme_path(paper_dir)
    readme_text = _read_text(readme) if readme else ""

    picked = _pick_readme_image(paper_dir)
    source = "readme"
    blob: bytes | None = None
    if picked:
        blob = picked[0]
    else:
        local_fallback = _pick_any_local_image(paper_dir)
        if local_fallback:
            blob = local_fallback[0]
            source = "local_image"
        else:
            paper = data.get("paper") or {}
            pdf = _download_pdf(_candidate_pdf_urls(str(paper.get("url") or ""), readme_text))
            if pdf:
                blob = _extract_pdf_first_page(pdf)
                source = "pdf_first_page"
    if not blob:
        title = str(data.get("name") or yaml_path.stem)
        subtitle = str(data.get("one_line") or data.get("task_description") or "Benchmark preview")
        final_blob = _render_title_card(title, subtitle)
        out_name = f"{num:03d}_{yaml_path.stem}.jpg"
        out_path = IMAGE_ROOT / out_name
        out_path.write_bytes(final_blob)
        data["image_path"] = f"../../../AISB/image/{out_name}"
        yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return out_path, "title_card"

    final_blob = _fit_16_9(blob)
    out_name = f"{num:03d}_{yaml_path.stem}.jpg"
    out_path = IMAGE_ROOT / out_name
    out_path.write_bytes(final_blob)
    data["image_path"] = f"../../../AISB/image/{out_name}"
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out_path, source


def main() -> None:
    import sys

    selection = sys.argv[1:] if len(sys.argv) > 1 else None
    for path in _yaml_paths(selection):
        out_path, source = generate_for_yaml(path)
        print(path.name, source, out_path)


if __name__ == "__main__":
    main()
