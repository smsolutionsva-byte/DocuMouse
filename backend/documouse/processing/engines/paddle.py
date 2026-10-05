"""PaddleOCR 3.x / PP-StructureV3 adapter.

PP-StructureV3 does all of the low-level document understanding: orientation,
layout detection, text detection + recognition, reading order and table
recognition. This module only translates its output into ``RawDocument``.

Docs: https://github.com/PaddlePaddle/PaddleOCR (PP-StructureV3 pipeline)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
from PIL import Image

from ...config import Settings
from ..html_table import parse_html_table
from ..pages import PageImage
from ..types import LayoutBlock, PageInfo, RawDocument, Table, TextLine
from .base import EngineResult, EngineUnavailable

log = logging.getLogger(__name__)

# Lighter models for CPU machines. Layout detection keeps the pipeline default
# (PP-DocLayout_plus-L) because the pipeline's per-class thresholds are tuned for it.
FAST_MODELS = {
    "text_detection_model_name": "PP-OCRv5_mobile_det",
    "text_recognition_model_name": "PP-OCRv5_mobile_rec",
}


class PaddleStructureEngine:
    name = "paddleocr-ppstructurev3"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._pipeline: Any = None
        self._lock = threading.Lock()
        self.version: str | None = None

    def _load(self) -> Any:
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                import paddleocr
                from paddleocr import PPStructureV3
            except ImportError as exc:
                raise EngineUnavailable(
                    "PaddleOCR is not installed. Install the backend with the `ocr` extra: "
                    "pip install -e '.[ocr]'"
                ) from exc
            self.version = getattr(paddleocr, "__version__", None)
            kwargs: dict[str, Any] = {
                # Only what invoices and receipts need; formulas/charts/seals are off.
                "use_doc_orientation_classify": self.settings.ocr_detect_orientation,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "use_table_recognition": True,
                "use_formula_recognition": False,
                "use_chart_recognition": False,
                "use_seal_recognition": False,
                "use_region_detection": True,
            }
            if self.settings.ocr_preset == "fast":
                kwargs.update(FAST_MODELS)
            else:
                kwargs["lang"] = self.settings.ocr_lang
            if self.settings.ocr_device:
                kwargs["device"] = self.settings.ocr_device
            try:
                self._pipeline = PPStructureV3(**kwargs)
            except Exception as exc:  # model download / runtime problems
                raise EngineUnavailable(
                    f"PP-StructureV3 could not be initialised: {exc}. The first run downloads "
                    "models; check network access to the model host (PADDLE_PDX_MODEL_SOURCE)."
                ) from exc
            return self._pipeline

    def process(self, pages: list[PageImage]) -> EngineResult:
        pipeline = self._load()
        page_infos: list[PageInfo] = []
        lines: list[TextLine] = []
        blocks: list[LayoutBlock] = []
        tables: list[Table] = []
        corrected: dict[int, Image.Image] = {}
        native: list[dict[str, Any]] = []

        for page in pages:
            bgr = np.asarray(page.image)[:, :, ::-1].copy()
            results = list(pipeline.predict(bgr))
            if not results:
                page_infos.append(PageInfo(index=page.index, width=page.image.width, height=page.image.height))
                continue
            res = results[0]
            data = res.json["res"]
            native.append(data)
            width, height = int(data["width"]), int(data["height"])
            page_infos.append(PageInfo(index=page.index, width=width, height=height))

            pre = data.get("doc_preprocessor_res") or {}
            if pre.get("angle") not in (None, 0, -1):
                try:
                    out = res["doc_preprocessor_res"]["output_img"]
                    corrected[page.index] = Image.fromarray(np.asarray(out)[:, :, ::-1])
                except Exception:  # pragma: no cover - defensive; keep the original image
                    log.warning("Could not read the orientation-corrected page image", exc_info=True)

            lines.extend(_lines(data.get("overall_ocr_res") or {}, page.index, width, height))
            page_blocks, page_tables = _blocks(data.get("parsing_res_list") or [], page.index, width, height)
            blocks.extend(page_blocks)
            tables.extend(page_tables)

        lines.sort(key=lambda ln: (ln.page, round(ln.bbox[1], 3), ln.bbox[0]))
        doc = RawDocument(
            engine=self.name,
            engine_version=self.version,
            pages=page_infos,
            lines=lines,
            blocks=blocks,
            tables=tables,
            meta={"preset": self.settings.ocr_preset},
        )
        return EngineResult(document=doc, corrected_pages=corrected, native=native)


def _norm(box: list[float], width: int, height: int) -> list[float]:
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    return [
        round(max(0.0, min(1.0, x0 / width)), 5),
        round(max(0.0, min(1.0, y0 / height)), 5),
        round(max(0.0, min(1.0, x1 / width)), 5),
        round(max(0.0, min(1.0, y1 / height)), 5),
    ]


def _lines(ocr: dict[str, Any], page: int, width: int, height: int) -> list[TextLine]:
    texts = ocr.get("rec_texts") or []
    scores = ocr.get("rec_scores") or []
    boxes = ocr.get("rec_boxes") or []
    out: list[TextLine] = []
    for i, (text, score, box) in enumerate(zip(texts, scores, boxes)):
        text = str(text).strip()
        if not text:
            continue
        out.append(
            TextLine(
                id=f"p{page}-l{i}",
                page=page,
                text=text,
                bbox=_norm(box, width, height),
                confidence=round(float(score), 4),
            )
        )
    return out


def _blocks(parsing: list[dict[str, Any]], page: int, width: int, height: int) -> tuple[list[LayoutBlock], list[Table]]:
    blocks: list[LayoutBlock] = []
    tables: list[Table] = []
    for i, block in enumerate(parsing):
        label = str(block.get("block_label", ""))
        bbox = _norm(block.get("block_bbox") or [0, 0, 0, 0], width, height)
        content = str(block.get("block_content") or "")
        block_id = f"p{page}-b{block.get('block_id', i)}"
        if label == "table" and "<t" in content:
            grid, header_rows = parse_html_table(content)
            if grid:
                tables.append(
                    Table(
                        id=f"p{page}-t{len(tables)}",
                        page=page,
                        bbox=bbox,
                        rows=grid,
                        header_rows=header_rows,
                        html=content,
                    )
                )
            content = ""
        blocks.append(
            LayoutBlock(id=block_id, page=page, label=label, bbox=bbox, text=content, order=block.get("block_order"))
        )
    return blocks, tables
