"""Run the document engine once per image and cache its normalised output.

OCR is the slow part; caching it lets the extraction rules be evaluated and
tuned in seconds. Cached files are RawDocument JSON, the same thing the app
stores for every upload.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from documouse.config import get_settings  # noqa: E402
from documouse.processing.pages import render_pages, sniff_content_type  # noqa: E402
from documouse.processing.types import RawDocument  # noqa: E402


def cached_raw(image: Path, cache_dir: Path, engine=None) -> tuple[RawDocument, float | None]:
    """Return ``(raw, seconds)``; seconds is None when the result came from the cache."""
    target = cache_dir / f"{image.stem}.raw.json"
    if target.exists():
        return RawDocument.model_validate_json(target.read_text()), None
    if engine is None:
        raise RuntimeError("no cached output and no engine given")
    settings = get_settings()
    data = image.read_bytes()
    pages = render_pages(data, sniff_content_type(data) or "image/jpeg", dpi=settings.pdf_render_dpi, max_pages=settings.max_pages)
    start = time.time()
    raw = engine.process(pages).document
    seconds = time.time() - start
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw.model_dump_json())
    return raw, seconds


def warm_cache(images: Iterable[Path], cache_dir: Path) -> None:
    from documouse.processing.engines.paddle import PaddleStructureEngine

    engine = PaddleStructureEngine(get_settings())
    images = list(images)
    times: list[float] = []
    for i, image in enumerate(images, start=1):
        try:
            _, seconds = cached_raw(image, cache_dir, engine)
        except Exception as exc:  # keep going; report at the end
            print(f"[{i}/{len(images)}] {image.name}: FAILED {exc}", flush=True)
            continue
        if seconds is not None:
            times.append(seconds)
        if i % 25 == 0 or i == len(images):
            avg = sum(times) / len(times) if times else 0
            print(f"[{i}/{len(images)}] avg {avg:.2f}s/image over {len(times)} new", flush=True)
