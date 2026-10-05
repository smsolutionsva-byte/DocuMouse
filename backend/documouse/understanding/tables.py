"""Turn engine tables into editable tables and find the line items.

Table *recognition* (structure, cells) is done by PP-StructureV3. This module
only decides which table holds the line items and what each column means.
"""

from __future__ import annotations

import re

from ..document_data import Column, Row, Source, TableData
from ..processing.types import RawDocument, Table
from . import layout
from .parsing import normalise_label, parse_amount
from .schema import COLUMN_ROLES

_EXTRA_ROLES: dict[str, tuple[str, ...]] = {
    "index": ("s no", "sl no", "sr no", "sno", "no", "#", "s n", "sr", "sl"),
    "code": ("hsn", "sac", "hsn sac", "hsn code", "sku", "code", "item code"),
    "tax_rate": ("gst rate", "tax rate", "gst %", "tax %", "rate %", "gst%", "tax%", "%"),
}
_ALL_ROLES = {**COLUMN_ROLES, **_EXTRA_ROLES}
_SUMMARY_ROW = re.compile(
    r"^\s*(sub\s*-?\s*total|grand\s+total|total|tax|cgst|sgst|igst|utgst|vat|gst|discount|"
    r"round(ing)?\s*off|amount\s+due|balance|shipping|freight|delivery|net\s+amount|amount\s+in\s+words)\b",
    re.I,
)


def _role_for(header: str) -> tuple[str | None, int]:
    """Best role for a header, with match strength (length of the matched hint)."""
    norm = normalise_label(header)
    if not norm:
        return None, 0
    best: tuple[str | None, int] = (None, 0)
    for role, hints in _ALL_ROLES.items():
        for hint in hints:
            h = normalise_label(hint) if hint not in ("#", "%") else hint
            if not h:
                continue
            if norm == h:
                strength = 100 + len(h)
            elif re.search(rf"(?<![a-z0-9]){re.escape(h)}(?![a-z0-9])", norm) or (h in ("%",) and h in norm):
                strength = len(h)
            else:
                continue
            if strength > best[1]:
                best = (role, strength)
    return best


def _is_header_row(cells: list[str]) -> bool:
    filled = [c for c in cells if c.strip()]
    if not filled:
        return False
    numeric = sum(1 for c in filled if parse_amount(c) is not None and not re.search(r"[A-Za-z]{3}", c))
    known = sum(1 for c in filled if _role_for(c)[0] is not None)
    return numeric <= len(filled) // 3 and known >= max(1, len(filled) // 3)


def _assign_roles(headers: list[str]) -> list[str | None]:
    scored = [_role_for(h) for h in headers]
    roles: list[str | None] = [None] * len(headers)
    # Each role goes to its strongest column; "amount" prefers the right-most column on ties.
    for role in _ALL_ROLES:
        best_idx, best_strength = None, 0
        for i, (r, strength) in enumerate(scored):
            if r != role:
                continue
            if strength > best_strength or (strength == best_strength and role == "amount"):
                best_idx, best_strength = i, strength
        if best_idx is not None:
            roles[best_idx] = role
    return roles


def _line_item_score(roles: list[str | None]) -> int:
    present = set(r for r in roles if r)
    has_label = bool(present & {"item", "description"})
    has_numbers = bool(present & {"quantity", "unit_price", "amount"})
    if not (has_label and has_numbers):
        return 0
    return len(present & {"item", "description", "quantity", "unit_price", "amount", "tax"})


def build_tables(raw: RawDocument, *, want_line_items: bool) -> list[TableData]:
    tables: list[TableData] = []
    line_items: TableData | None = None
    line_item_signature: list[str | None] | None = None
    best_score = 0
    next_table = 1

    for table in raw.tables:
        grid = table.rows
        if not grid:
            continue
        width = max(len(r) for r in grid)
        grid = [r + [""] * (width - len(r)) for r in grid]
        header_count = table.header_rows or (1 if _is_header_row(grid[0]) else 0)
        if header_count:
            headers = [" ".join(grid[r][c] for r in range(header_count) if grid[r][c]).strip() for c in range(width)]
        else:
            headers = [""] * width
        roles = _assign_roles(headers) if header_count else [None] * width
        body = grid[header_count:]

        # A line-item table that continues on the next page repeats its header: merge it.
        if want_line_items and line_items is not None and roles == line_item_signature and header_count:
            _append_rows(line_items, body, raw, table)
            continue

        data = TableData(id=f"t{next_table}", title="Table", source=Source(page=table.page, bbox=table.bbox))
        next_table += 1
        for c in range(width):
            name = headers[c] or f"Column {c + 1}"
            data.columns.append(Column(id=data.new_id("c"), name=name, role=roles[c]))
        _append_rows(data, body, raw, table)
        _drop_empty_columns(data)

        score = _line_item_score([col.role for col in data.columns]) if want_line_items else 0
        if score > best_score:
            best_score = score
            line_items = data
            line_item_signature = roles
        tables.append(data)

    if line_items is not None:
        line_items.role = "line_items"
        line_items.title = "Line items"
        # Show the line items first.
        tables.remove(line_items)
        tables.insert(0, line_items)
    for i, t in enumerate(tables):
        if t.role is None:
            t.title = f"Table {i + 1}" if line_items is None else f"Other table {i}"
    return tables


def _append_rows(data: TableData, body: list[list[str]], raw: RawDocument, table: Table) -> None:
    table_lines = [ln for ln in raw.lines if layout.inside(ln, table.bbox, table.page)]
    for cells in body:
        if not any(c.strip() for c in cells):
            continue
        row = Row(id=data.new_id("r"))
        for col, value in zip(data.columns, cells):
            row.cells[col.id] = value.strip()
        first = next((c for c in cells if c.strip()), "")
        role_of = {col.id: col.role for col in data.columns}
        item_text = next((row.cells[cid] for cid, role in role_of.items() if role in ("item", "description") and row.cells.get(cid)), "")
        filled = sum(1 for c in cells if c.strip())
        if _SUMMARY_ROW.match(first) and (filled <= 3 or not item_text or _SUMMARY_ROW.match(item_text)):
            row.kind = "summary"
        row.source = _row_source(cells, table_lines, table.page)
        data.rows.append(row)


def _row_source(cells: list[str], lines, page: int) -> Source | None:
    """Where this row sits on the page: the text lines of its cells, on the same band."""
    wanted = [normalise_label(c) for c in cells if len(normalise_label(c)) >= 2]
    if not wanted:
        return None

    def hits(w: str):
        return [ln for ln in lines if (n := normalise_label(ln.text)) and (n == w or (len(n) >= 4 and n in w))]

    # Anchor on the most distinctive cell (fewest matches, then longest text), e.g. the item name,
    # so values repeated on other rows ("10,000.00") don't drag the box across the table.
    candidates = sorted(((hits(w), w) for w in wanted), key=lambda hw: (len(hw[0]) or 99, -len(hw[1])))
    if not candidates or not candidates[0][0]:
        return None
    anchor = candidates[0][0][0]
    tolerance = 0.6 * layout.height(anchor)
    band = [anchor]
    for found, _ in candidates[1:]:
        band.extend(ln for ln in found if abs(layout.center_y(ln) - layout.center_y(anchor)) <= tolerance and ln not in band)
    return Source(page=page, bbox=layout.union_bbox(band))


def _drop_empty_columns(data: TableData) -> None:
    keep = []
    for col in data.columns:
        if col.name.startswith("Column ") and not any(r.cells.get(col.id, "").strip() for r in data.rows):
            continue
        keep.append(col)
    data.columns = keep
    ids = {c.id for c in keep}
    for r in data.rows:
        r.cells = {k: v for k, v in r.cells.items() if k in ids}
