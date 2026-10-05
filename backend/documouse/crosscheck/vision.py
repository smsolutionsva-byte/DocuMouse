"""A vision model as the second reader, through any OpenAI-compatible chat endpoint.

Gemini (free tier), OpenRouter, GitHub Models, Ollama and LM Studio all speak this
protocol. The model sees the page images and answers for the key fields only. Its
answers are compared with what PaddleOCR + the rules found; they are never used as
values on their own.
"""

from __future__ import annotations

import io

from PIL import Image

from ..llm.base import LLMError
from ..llm.openai_compat import OpenAICompatibleProvider
from ..processing.pages import PageImage
from .base import SecondReaderError, SecondReading, key_pages

MAX_SIDE = 2000  # pixels on the long side
# Generous, so models that reason before answering (Gemini Flash, for one) aren't cut off.
MAX_TOKENS = 2048

SYSTEM = (
    "You read scanned business documents and report exactly what is printed. "
    "You never guess: if something is unclear, cut off or missing, you answer null."
)

PROMPT = """This is a {label}. Read it and report:

- "name": the business that issued it (the seller or shop), as printed, including a legal suffix such as "SDN BHD", "Pvt Ltd" or "LLC". Not the customer, not an address.
- "date": the date it was issued, as YYYY-MM-DD.
- "total": the final amount the customer has to pay, as a plain number with a dot for decimals, such as 1234.50. Not the cash handed over, not the change, not a subtotal or a tax amount.

Use null for anything you can't read with certainty. Do not fix or complete unclear characters.
Reply with JSON only: {{"name": ..., "date": ..., "total": ...}}"""


class VisionReader:
    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout: float, provider: str):
        self.name = model
        self._llm = OpenAICompatibleProvider(name=provider, base_url=base_url, model=model, api_key=api_key,
                                             timeout=timeout)

    def read(self, pages: list[PageImage], doc_type: str) -> SecondReading:
        label = {"invoice": "invoice", "receipt": "receipt"}.get(doc_type, "business document")
        images = [_jpeg(p.image) for p in key_pages(pages)]
        try:
            reply = self._llm.complete_json(SYSTEM, PROMPT.format(label=label), max_tokens=MAX_TOKENS, images=images)
        except LLMError as exc:
            raise SecondReaderError(str(exc)) from exc
        values = {key: _text(reply.get(key)) for key in ("name", "date", "total")}
        return SecondReading(reader=self.name, values=values)


def _text(value: object) -> str | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("null", "none", "n/a") else None


def _jpeg(image: Image.Image) -> bytes:
    img = image.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
