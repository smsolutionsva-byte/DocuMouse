"""PaddleOCR-VL as the second reader.

PaddleOCR-VL (Apache 2.0) is PaddleOCR's own 0.9B vision-language document model. Its
"Spotting:" task returns every text line on the page with its position, which DocuMouse
turns into a ``RawDocument`` and runs through the same rules as PaddleOCR's output. Same
rules, independent reading: where the two disagree, one of them misread the page.

DocuMouse talks to PaddleOCR-VL over HTTP instead of loading it in-process (running it
inside the API process on CPU needed more than 15 GB of memory for one receipt):

- an OpenAI-compatible server: llama.cpp's ``llama-server`` with the official GGUF
  (https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF), started with ``--special`` so
  the location tokens come through, or vLLM. URL ends in ``/v1``.
- a layout-parsing endpoint: PaddleOCR's hosted API (https://aistudio.baidu.com/paddleocr,
  needs a token) or a self-hosted PaddleX serving app. URL ends in ``/layout-parsing``.
"""

from __future__ import annotations

import base64
import html
import io
import re
from typing import Any

import httpx
from PIL import Image

from ..llm.base import LLMError
from ..llm.openai_compat import OpenAICompatibleProvider, image_part
from ..processing.pages import PageImage
from ..processing.types import PageInfo, RawDocument, TextLine, reading_order
from .base import SecondReaderError, SecondReading, key_pages

# Output format of the "Spotting:" task: the text of a line followed by 8 location tokens,
# the line's 4 corner points on a 0..1000 grid, optionally wrapped in TEXT/LOC markers.
_LOC = re.compile(r"<\|LOC_(\d+)\|>")
_MARKERS = re.compile(r"<\|[A-Z_]+\|>|</?s>")
SPOTTING_MAX_TOKENS = 8192


class PaddleOCRVLReader:
    def __init__(self, *, url: str, token: str | None, model: str, timeout: float):
        self.name = "PaddleOCR-VL"
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._layout_api = self._url.endswith("/layout-parsing")
        self._llm = None if self._layout_api else OpenAICompatibleProvider(
            name="paddleocr-vl", base_url=self._url, model=model, api_key=token, timeout=timeout)

    def read(self, pages: list[PageImage], doc_type: str) -> SecondReading:
        infos: list[PageInfo] = []
        lines: list[TextLine] = []
        for page in key_pages(pages):
            width, height = page.image.size
            infos.append(PageInfo(index=page.index, width=width, height=height))
            texts = self._layout_parsing(page) if self._layout_api else self._spot(page)
            for i, (text, (x0, y0, x1, y1)) in enumerate(texts):
                lines.append(TextLine(
                    id=f"p{page.index}-v{i}", page=page.index, text=text,
                    bbox=[round(x0, 5), round(y0, 5), round(x1, 5), round(y1, 5)],
                    # PaddleOCR-VL reports no per-line score; the comparison doesn't use it.
                    confidence=0.9,
                ))
        raw = RawDocument(engine="paddleocr-vl", pages=infos, lines=reading_order(lines))
        return SecondReading(reader=self.name, raw=raw)

    # ---------------------------------------------------------------- transports

    def _spot(self, page: PageImage) -> list[tuple[str, tuple[float, float, float, float]]]:
        image = page.image.convert("RGB")
        # PaddleOCR-VL upscales small pages 2x before spotting (PaddleX pre_process_for_spotting).
        if image.width < 1500 and image.height < 1500:
            image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="PNG")  # what PaddleX sends to llama.cpp servers too
        payload = {
            "model": self._llm.model,
            "temperature": 0,
            "max_tokens": SPOTTING_MAX_TOKENS,
            # Location tokens are special tokens; servers drop them unless asked not to.
            "skip_special_tokens": False,
            "messages": [{"role": "user", "content": [image_part(buf.getvalue(), "image/png"),
                                                      {"type": "text", "text": "Spotting:"}]}],
        }
        try:
            return parse_spotting(self._llm.chat(payload))
        except LLMError as exc:
            raise SecondReaderError(str(exc)) from exc

    def _layout_parsing(self, page: PageImage) -> list[tuple[str, tuple[float, float, float, float]]]:
        buf = io.BytesIO()
        page.image.convert("RGB").save(buf, format="JPEG", quality=92)
        body = {
            "file": base64.b64encode(buf.getvalue()).decode(),
            "fileType": 1,
            "useLayoutDetection": False,
            "promptLabel": "spotting",
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "visualize": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        try:
            response = httpx.post(self._url, json=body, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            results = response.json()["result"]["layoutParsingResults"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SecondReaderError(f"PaddleOCR-VL request failed: {exc}") from exc
        out: list[tuple[str, tuple[float, float, float, float]]] = []
        for item in results:
            res: dict[str, Any] = item.get("prunedResult") or {}
            spotting = res.get("spotting_res") or {}
            if not spotting and res.get("parsing_res_list"):
                raise SecondReaderError("This PaddleOCR-VL service didn't return text lines. It needs PaddleOCR-VL 1.5 or newer.")
            width, height = float(res.get("width") or page.image.width), float(res.get("height") or page.image.height)
            for text, poly in zip(spotting.get("rec_texts") or [], spotting.get("rec_polys") or []):
                xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
                if str(text).strip() and xs and ys:
                    out.append((str(text).strip(), _clamp(min(xs) / width, min(ys) / height,
                                                          max(xs) / width, max(ys) / height)))
        return out


def parse_spotting(output: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Lines and normalised boxes from raw "Spotting:" output."""
    out: list[tuple[str, tuple[float, float, float, float]]] = []
    tokens = list(_LOC.finditer(output))
    start, i = 0, 0
    while i + 8 <= len(tokens):
        group = tokens[i : i + 8]
        text = html.unescape(_MARKERS.sub("", output[start : group[0].start()])).strip()
        vals = [int(t.group(1)) / 1000 for t in group]
        xs, ys = vals[0::2], vals[1::2]
        if text:
            out.append((text, _clamp(min(xs), min(ys), max(xs), max(ys))))
        start = group[-1].end()
        i += 8
    return out


def _clamp(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    c = lambda v: max(0.0, min(1.0, v))  # noqa: E731
    return c(x0), c(y0), c(x1), c(y1)
