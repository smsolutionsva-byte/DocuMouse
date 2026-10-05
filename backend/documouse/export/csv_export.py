"""CSV exports that open cleanly in Excel, Google Sheets and Numbers.

Amounts are written as plain numbers and dates as YYYY-MM-DD so spreadsheets
treat them as numbers and dates. A UTF-8 BOM makes Excel show ₹/€ correctly.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable

from ..document_data import DocumentData
from ..models import Document
from ..understanding.schema import schema_for

BOM = "﻿"
_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")


def _safe(value: str | None) -> str:
    """Neutralise spreadsheet formula injection without mangling negative numbers."""
    if value is None:
        return ""
    value = str(value)
    if value and value[0] in "=+-@\t\r" and not _NUMERIC.match(value):
        return "'" + value
    return value


def _writer() -> tuple[io.StringIO, csv.writer]:
    buf = io.StringIO()
    buf.write(BOM)
    return buf, csv.writer(buf, lineterminator="\r\n")


def document_csv(data: DocumentData, layout: str = "sections") -> str:
    """``sections``: fields, then each table. ``line_items``: one row per item with the
    document's key fields repeated, ready for a spreadsheet or accounting import."""
    buf, w = _writer()
    fields = [(f.label, (data.fields.get(f.key).value if data.fields.get(f.key) else None)) for f in schema_for(data.doc_type)]

    if layout == "line_items":
        table = data.line_items() or (data.tables[0] if data.tables else None)
        keys = [(label, value) for label, value in fields if label in
                ("Vendor", "Merchant", "Invoice number", "Invoice date", "Date", "Currency")]
        if table is None:
            w.writerow([label for label, _ in fields])
            w.writerow([_safe(v) for _, v in fields])
            return buf.getvalue()
        w.writerow([label for label, _ in keys] + [c.name for c in table.columns])
        for row in table.rows:
            if row.kind == "summary":
                continue
            w.writerow([_safe(v) for _, v in keys] + [_safe(row.cells.get(c.id, "")) for c in table.columns])
        return buf.getvalue()

    if fields:
        w.writerow(["Field", "Value"])
        for label, value in fields:
            w.writerow([label, _safe(value)])
    for table in data.tables:
        if fields or table is not data.tables[0]:
            w.writerow([])
        w.writerow([table.title])
        w.writerow([c.name for c in table.columns])
        for row in table.rows:
            w.writerow([_safe(row.cells.get(c.id, "")) for c in table.columns])
    return buf.getvalue()


LIBRARY_COLUMNS = [
    ("Document", lambda d: d.filename),
    ("Type", lambda d: d.doc_type),
    ("Vendor / merchant", lambda d: d.party),
    ("Number", lambda d: d.reference),
    ("Date", lambda d: d.doc_date),
    ("Total", lambda d: d.total),
    ("Currency", lambda d: d.currency),
    ("Needs review", lambda d: str(d.review_count)),
    ("Approved", lambda d: "yes" if d.approved_version_id and d.approved_version_id == d.head_version_id else "no"),
]


def library_csv(documents: Iterable[Document]) -> str:
    """One row per document — the "pile of invoices into one spreadsheet" export."""
    buf, w = _writer()
    w.writerow([name for name, _ in LIBRARY_COLUMNS])
    for doc in documents:
        w.writerow([_safe(get(doc)) for _, get in LIBRARY_COLUMNS])
    return buf.getvalue()
