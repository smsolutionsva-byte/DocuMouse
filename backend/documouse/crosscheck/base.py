from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from ..processing.pages import PageImage
from ..processing.types import RawDocument


class SecondReaderError(RuntimeError):
    """The second reader couldn't read the document (not configured, unreachable, bad reply)."""


# The fields a second reader is asked about, per document type, by role.
KEY_FIELDS: dict[str, dict[str, str]] = {
    "invoice": {"name": "vendor", "date": "invoice_date", "total": "total"},
    "receipt": {"name": "merchant", "date": "date", "total": "total"},
}


class SecondReading(BaseModel):
    """What a second reader read, stored next to the engine output.

    OCR-style readers (PaddleOCR-VL) return the text lines they read; the same rules that
    run on PaddleOCR's output then pick the key fields from them, for whatever document
    type the user settles on. Vision models answer for the key fields directly, by role
    (``name``, ``date`` as ISO, ``total`` as a plain number).
    """

    reader: str
    raw: RawDocument | None = None
    values: dict[str, str | None] = Field(default_factory=dict)


class SecondReader(Protocol):
    name: str

    def read(self, pages: list[PageImage], doc_type: str) -> SecondReading: ...


def key_pages(pages: list[PageImage]) -> list[PageImage]:
    """The pages a second reader looks at: the first (name, date) and the last (total).

    Keeps a long PDF from costing minutes per page on a CPU or burning a free API quota.
    """
    return pages if len(pages) <= 2 else [pages[0], pages[-1]]
