"""The versioned, user-editable content of a document.

A ``DocumentData`` is what the review screen shows and edits. Every version in
history stores one, as JSON. Values are stored in a canonical form
(amounts like ``"23600.00"``, dates as ISO ``"2026-10-05"``, currency as ISO
codes) and ``raw`` keeps what was printed on the page.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .processing.types import BBox

SCHEMA_VERSION = 1


class Source(BaseModel):
    page: int
    bbox: BBox


class Suggestion(BaseModel):
    value: str
    reason: str


class FieldValue(BaseModel):
    value: str | None = None
    raw: str | None = None
    confidence: float = 0.0
    source: Source | None = None
    # Where the value came from: the document engine + rules, an LLM, or a person.
    origin: Literal["ocr", "llm", "ocr+llm", "user", "ai"] | None = None
    # Set when a person typed or approved the value.
    confirmed: bool = False
    suggestion: Suggestion | None = None
    notes: list[str] = Field(default_factory=list)


class Column(BaseModel):
    id: str
    name: str
    role: str | None = None  # item | description | quantity | unit_price | tax | amount


class Row(BaseModel):
    id: str
    cells: dict[str, str] = Field(default_factory=dict)
    kind: Literal["item", "summary"] = "item"
    source: Source | None = None


class TableData(BaseModel):
    id: str
    title: str
    role: str | None = None  # "line_items" for the invoice/receipt item table
    source: Source | None = None
    columns: list[Column] = Field(default_factory=list)
    rows: list[Row] = Field(default_factory=list)
    next_id: int = 1  # counter for new row/column ids, so ids are never reused

    def column(self, column_id: str) -> Column | None:
        return next((c for c in self.columns if c.id == column_id), None)

    def row(self, row_id: str) -> Row | None:
        return next((r for r in self.rows if r.id == row_id), None)

    def new_id(self, prefix: str) -> str:
        value = f"{prefix}{self.next_id}"
        self.next_id += 1
        return value


class DocumentData(BaseModel):
    schema_version: int = SCHEMA_VERSION
    doc_type: str = "unknown"
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    tables: list[TableData] = Field(default_factory=list)
    next_table_id: int = 1

    def table(self, table_id: str) -> TableData | None:
        return next((t for t in self.tables if t.id == table_id), None)

    def line_items(self) -> TableData | None:
        return next((t for t in self.tables if t.role == "line_items"), None)

    def new_table_id(self) -> str:
        value = f"t{self.next_table_id}"
        self.next_table_id += 1
        return value
