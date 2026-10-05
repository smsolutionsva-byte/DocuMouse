"""Engine-neutral representation of what a document engine found.

Every engine adapter (PaddleOCR / PP-StructureV3 today) converts its native
output into a ``RawDocument``. Everything downstream (classification,
extraction, validation, the review UI) only ever sees this shape, so another
engine can be added later without touching those layers.

Coordinates are normalised to 0..1 relative to the page image, as
``[x0, y0, x1, y1]`` with the origin at the top-left.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

BBox = list[float]


class TextLine(BaseModel):
    id: str
    page: int
    text: str
    bbox: BBox
    confidence: float


class LayoutBlock(BaseModel):
    id: str
    page: int
    label: str  # engine label, e.g. "doc_title", "text", "table", "header"
    bbox: BBox
    text: str = ""
    order: int | None = None


class Table(BaseModel):
    id: str
    page: int
    bbox: BBox
    # Fully expanded grid (row/col spans repeated into the covered cells is avoided;
    # spanned cells are left empty) so every row has the same number of columns.
    rows: list[list[str]]
    header_rows: int = 0
    html: str | None = None


class PageInfo(BaseModel):
    index: int
    width: int
    height: int


class RawDocument(BaseModel):
    engine: str
    engine_version: str | None = None
    pages: list[PageInfo]
    lines: list[TextLine] = Field(default_factory=list)
    blocks: list[LayoutBlock] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    def page_lines(self, page: int) -> list[TextLine]:
        return [line for line in self.lines if line.page == page]

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def reading_order(lines: list[TextLine]) -> list[TextLine]:
    """Top-to-bottom, then left-to-right within each visual row.

    Sorting by raw y alone interleaves a row whose boxes start a pixel apart
    ("Table: 7" before "Cashier: Priya"), so lines are grouped into rows first.
    """
    out: list[TextLine] = []
    for page in sorted({ln.page for ln in lines}):
        pending = sorted((ln for ln in lines if ln.page == page), key=lambda ln: (ln.bbox[1] + ln.bbox[3]) / 2)
        row: list[TextLine] = []
        row_y = 0.0
        for ln in pending:
            cy = (ln.bbox[1] + ln.bbox[3]) / 2
            h = ln.bbox[3] - ln.bbox[1]
            if row and abs(cy - row_y) > 0.5 * h:
                out.extend(sorted(row, key=lambda x: x.bbox[0]))
                row = []
            if not row:
                row_y = cy
            row.append(ln)
        out.extend(sorted(row, key=lambda x: x.bbox[0]))
    return out
