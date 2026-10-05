"""Re-record the real-engine fixtures used by test_real_engine_output.py.

    python tests/record_engine_output.py

Runs PaddleOCR / PP-StructureV3 (needs the `ocr` extra and downloaded models) on
every document in tests/samples and writes the normalised RawDocument JSON to
tests/fixtures_real.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from documouse.config import get_settings  # noqa: E402
from documouse.processing.engines.paddle import PaddleStructureEngine  # noqa: E402
from documouse.processing.pages import render_pages, sniff_content_type  # noqa: E402

HERE = Path(__file__).parent
SAMPLES = HERE / "samples"
OUT = HERE / "fixtures_real"


def main() -> None:
    settings = get_settings()
    engine = PaddleStructureEngine(settings)
    OUT.mkdir(exist_ok=True)
    for path in sorted(SAMPLES.iterdir()):
        data = path.read_bytes()
        content_type = sniff_content_type(data)
        if content_type is None:
            continue
        pages = render_pages(data, content_type, dpi=settings.pdf_render_dpi, max_pages=settings.max_pages)
        start = time.time()
        result = engine.process(pages)
        (OUT / f"{path.stem}.raw.json").write_text(result.document.model_dump_json(indent=1))
        print(f"{path.name}: {time.time() - start:.1f}s, {len(result.document.lines)} lines, {len(result.document.tables)} tables")


if __name__ == "__main__":
    main()
