"""The complete set of changes anyone (a person or the AI) can make to a document.

The backend owns this list. The AI assistant can only *propose* operations
from it; they are validated here, previewed, and applied only after a person
approves. There is no way to run arbitrary code or SQL through an operation.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from ..document_data import Column, DocumentData, FieldValue, Row, TableData
from ..understanding.schema import COLUMN_ROLES, field_def
from ..understanding.values import canonicalize


class OperationError(ValueError):
    """An operation that doesn't make sense for this document (shown to the user)."""


# ------------------------------------------------------------------ fields

class SetField(BaseModel):
    op: Literal["set_field"] = "set_field"
    field: str
    value: str | None


class ConfirmField(BaseModel):
    op: Literal["confirm_field"] = "confirm_field"
    field: str


# ------------------------------------------------------------------ cells & rows

class SetCell(BaseModel):
    op: Literal["set_cell"] = "set_cell"
    table_id: str
    row_id: str
    column_id: str
    value: str


class AddRow(BaseModel):
    op: Literal["add_row"] = "add_row"
    table_id: str
    after_row_id: str | None = None  # None → append at the end
    cells: dict[str, str] = Field(default_factory=dict)


class DeleteRows(BaseModel):
    op: Literal["delete_rows"] = "delete_rows"
    table_id: str
    row_ids: list[str] = Field(min_length=1)


class DeleteBlankRows(BaseModel):
    op: Literal["delete_blank_rows"] = "delete_blank_rows"
    table_id: str


class MergeRows(BaseModel):
    """Join rows that the document engine split apart (e.g. a wrapped description)."""

    op: Literal["merge_rows"] = "merge_rows"
    table_id: str
    row_ids: list[str] = Field(min_length=2)
    separator: str = " "


class SetRowKind(BaseModel):
    op: Literal["set_row_kind"] = "set_row_kind"
    table_id: str
    row_id: str
    kind: Literal["item", "summary"]


# ------------------------------------------------------------------ columns

class AddColumn(BaseModel):
    op: Literal["add_column"] = "add_column"
    table_id: str
    name: str = Field(min_length=1, max_length=80)
    after_column_id: str | None = None


class DeleteColumn(BaseModel):
    op: Literal["delete_column"] = "delete_column"
    table_id: str
    column_id: str


class RenameColumn(BaseModel):
    op: Literal["rename_column"] = "rename_column"
    table_id: str
    column_id: str
    name: str = Field(min_length=1, max_length=80)


class MoveColumn(BaseModel):
    op: Literal["move_column"] = "move_column"
    table_id: str
    column_id: str
    to_index: int = Field(ge=0)


class SetColumnRole(BaseModel):
    op: Literal["set_column_role"] = "set_column_role"
    table_id: str
    column_id: str
    role: str | None


class SplitColumn(BaseModel):
    """Split one column into several, e.g. "2 ₹100" → Quantity | Price."""

    op: Literal["split_column"] = "split_column"
    table_id: str
    column_id: str
    new_columns: list[str] = Field(min_length=2, max_length=6)
    separator: str | None = None  # None → any whitespace
    # Which end gets the single pieces when a cell has more parts than columns.
    keep_extra: Literal["first", "last"] = "first"


class MergeColumns(BaseModel):
    op: Literal["merge_columns"] = "merge_columns"
    table_id: str
    column_ids: list[str] = Field(min_length=2)
    name: str = Field(min_length=1, max_length=80)
    separator: str = " "


# ------------------------------------------------------------------ tables

class AddTable(BaseModel):
    op: Literal["add_table"] = "add_table"
    title: str = Field(default="Line items", max_length=80)
    columns: list[str] = Field(min_length=1, max_length=20)
    line_items: bool = False


class SplitTable(BaseModel):
    op: Literal["split_table"] = "split_table"
    table_id: str
    before_row_id: str  # this row and everything after it moves to the new table
    title: str | None = None


class RenameTable(BaseModel):
    op: Literal["rename_table"] = "rename_table"
    table_id: str
    title: str = Field(min_length=1, max_length=80)


class DeleteTable(BaseModel):
    op: Literal["delete_table"] = "delete_table"
    table_id: str


OPERATION_MODELS = (
    SetField, ConfirmField, SetCell, AddRow, DeleteRows, DeleteBlankRows, MergeRows, SetRowKind,
    AddColumn, DeleteColumn, RenameColumn, MoveColumn, SetColumnRole, SplitColumn, MergeColumns,
    AddTable, SplitTable, RenameTable, DeleteTable,
)
Operation = Annotated[Union[OPERATION_MODELS], Field(discriminator="op")]  # type: ignore[valid-type]
OperationList = TypeAdapter(list[Operation])

MAX_OPERATIONS = 200


def parse_operations(raw: object) -> list:
    ops = OperationList.validate_python(raw)
    if len(ops) > MAX_OPERATIONS:
        raise OperationError("Too many changes at once.")
    return ops


# ------------------------------------------------------------------ apply

def apply_operations(data: DocumentData, ops: list, *, author: str = "user") -> DocumentData:
    """Return a new ``DocumentData`` with ``ops`` applied; ``data`` is untouched."""
    out = data.model_copy(deep=True)
    for op in ops:
        _apply(out, op, author)
    return out


def _table(data: DocumentData, table_id: str) -> TableData:
    table = data.table(table_id)
    if table is None:
        raise OperationError(f"There's no table “{table_id}”.")
    return table


def _column(table: TableData, column_id: str) -> Column:
    col = table.column(column_id)
    if col is None:
        raise OperationError(f"There's no column “{column_id}” in {table.title}.")
    return col


def _row(table: TableData, row_id: str) -> Row:
    row = table.row(row_id)
    if row is None:
        raise OperationError(f"There's no row “{row_id}” in {table.title}.")
    return row


def _apply(data: DocumentData, op, author: str) -> None:  # noqa: C901 - a flat dispatch is clearest here
    origin = "ai" if author == "ai" else "user"

    if isinstance(op, SetField):
        fdef = field_def(data.doc_type, op.field)
        if fdef is None:
            raise OperationError(f"“{op.field}” isn't a field on this {data.doc_type}.")
        current = data.fields.get(op.field) or FieldValue()
        reference_year = None
        if current.value and fdef.kind == "date" and re.match(r"\d{4}", current.value):
            reference_year = int(current.value[:4])
        dayfirst = (data.fields.get("currency") or FieldValue()).value != "USD"
        if op.value is None or not op.value.strip():
            data.fields[op.field] = FieldValue(origin=origin, confirmed=True, confidence=1.0)
            return
        canonical = canonicalize(fdef.kind, op.value, dayfirst=dayfirst, reference_year=reference_year)
        data.fields[op.field] = FieldValue(
            # Keep what the person typed if it can't be parsed; validation will flag it.
            value=canonical if canonical is not None else op.value.strip(),
            raw=op.value.strip(),
            confidence=1.0,
            source=current.source,
            origin=origin,
            confirmed=True,
        )
        return

    if isinstance(op, ConfirmField):
        if field_def(data.doc_type, op.field) is None:
            raise OperationError(f"“{op.field}” isn't a field on this {data.doc_type}.")
        current = data.fields.get(op.field) or FieldValue()
        current.confirmed = True
        current.suggestion = None
        data.fields[op.field] = current
        return

    if isinstance(op, SetCell):
        table = _table(data, op.table_id)
        _column(table, op.column_id)
        _row(table, op.row_id).cells[op.column_id] = op.value
        return

    if isinstance(op, AddRow):
        table = _table(data, op.table_id)
        for cid in op.cells:
            _column(table, cid)
        row = Row(id=table.new_id("r"), cells={c.id: op.cells.get(c.id, "") for c in table.columns})
        if op.after_row_id is None:
            table.rows.append(row)
        else:
            index = table.rows.index(_row(table, op.after_row_id))
            table.rows.insert(index + 1, row)
        return

    if isinstance(op, DeleteRows):
        table = _table(data, op.table_id)
        for rid in op.row_ids:
            _row(table, rid)
        drop = set(op.row_ids)
        table.rows = [r for r in table.rows if r.id not in drop]
        return

    if isinstance(op, DeleteBlankRows):
        table = _table(data, op.table_id)
        table.rows = [r for r in table.rows if any(v.strip() for v in r.cells.values())]
        return

    if isinstance(op, MergeRows):
        table = _table(data, op.table_id)
        rows = [_row(table, rid) for rid in op.row_ids]
        rows.sort(key=table.rows.index)
        first = rows[0]
        for col in table.columns:
            parts = [r.cells.get(col.id, "").strip() for r in rows]
            first.cells[col.id] = op.separator.join(p for p in parts if p)
        drop = {r.id for r in rows[1:]}
        table.rows = [r for r in table.rows if r.id not in drop]
        return

    if isinstance(op, SetRowKind):
        _row(_table(data, op.table_id), op.row_id).kind = op.kind
        return

    if isinstance(op, AddColumn):
        table = _table(data, op.table_id)
        col = Column(id=table.new_id("c"), name=op.name.strip())
        index = len(table.columns) if op.after_column_id is None else table.columns.index(_column(table, op.after_column_id)) + 1
        table.columns.insert(index, col)
        for r in table.rows:
            r.cells[col.id] = ""
        return

    if isinstance(op, DeleteColumn):
        table = _table(data, op.table_id)
        col = _column(table, op.column_id)
        if len(table.columns) == 1:
            raise OperationError("A table needs at least one column. Delete the table instead.")
        table.columns.remove(col)
        for r in table.rows:
            r.cells.pop(col.id, None)
        return

    if isinstance(op, RenameColumn):
        _column(_table(data, op.table_id), op.column_id).name = op.name.strip()
        return

    if isinstance(op, MoveColumn):
        table = _table(data, op.table_id)
        col = _column(table, op.column_id)
        table.columns.remove(col)
        table.columns.insert(min(op.to_index, len(table.columns)), col)
        return

    if isinstance(op, SetColumnRole):
        if op.role is not None and op.role not in COLUMN_ROLES:
            raise OperationError(f"“{op.role}” isn't a column type DocuMouse knows.")
        table = _table(data, op.table_id)
        col = _column(table, op.column_id)
        if op.role is not None:
            for other in table.columns:
                if other.role == op.role:
                    other.role = None
        col.role = op.role
        return

    if isinstance(op, SplitColumn):
        table = _table(data, op.table_id)
        col = _column(table, op.column_id)
        n = len(op.new_columns)
        new_cols = [Column(id=table.new_id("c"), name=name.strip() or f"Part {i + 1}") for i, name in enumerate(op.new_columns)]
        index = table.columns.index(col)
        table.columns[index : index + 1] = new_cols
        for r in table.rows:
            parts = split_value(r.cells.pop(col.id, ""), n, op.separator, op.keep_extra)
            for c, part in zip(new_cols, parts):
                r.cells[c.id] = part
        return

    if isinstance(op, MergeColumns):
        table = _table(data, op.table_id)
        cols = [_column(table, cid) for cid in op.column_ids]
        if len({c.id for c in cols}) != len(cols):
            raise OperationError("Pick different columns to merge.")
        merged = Column(id=table.new_id("c"), name=op.name.strip())
        index = min(table.columns.index(c) for c in cols)
        for r in table.rows:
            parts = [r.cells.pop(c.id, "").strip() for c in cols]
            r.cells[merged.id] = op.separator.join(p for p in parts if p)
        table.columns = [c for c in table.columns if c not in cols]
        table.columns.insert(index, merged)
        return

    if isinstance(op, AddTable):
        if op.line_items and data.line_items() is not None:
            raise OperationError("This document already has a line items table.")
        table = TableData(id=data.new_table_id(), title=op.title.strip() or "Table",
                          role="line_items" if op.line_items else None)
        for name in op.columns:
            table.columns.append(Column(id=table.new_id("c"), name=name.strip() or "Column"))
        _guess_roles(table)
        data.tables.insert(0 if op.line_items else len(data.tables), table)
        return

    if isinstance(op, SplitTable):
        table = _table(data, op.table_id)
        row = _row(table, op.before_row_id)
        index = table.rows.index(row)
        if index == 0:
            raise OperationError("Pick a row below the first one to split the table there.")
        new = TableData(
            id=data.new_table_id(),
            title=(op.title or f"{table.title} (part 2)").strip(),
            columns=[c.model_copy() for c in table.columns],
            rows=table.rows[index:],
            next_id=table.next_id,
            source=table.source,
        )
        table.rows = table.rows[:index]
        data.tables.insert(data.tables.index(table) + 1, new)
        return

    if isinstance(op, RenameTable):
        _table(data, op.table_id).title = op.title.strip()
        return

    if isinstance(op, DeleteTable):
        table = _table(data, op.table_id)
        data.tables.remove(table)
        return

    raise OperationError(f"Unsupported operation: {getattr(op, 'op', op)!r}")


def split_value(value: str, n: int, separator: str | None, keep_extra: str = "first") -> list[str]:
    """Split ``value`` into exactly ``n`` parts, never dropping text."""
    value = value.strip()
    if not value:
        return [""] * n
    pieces = value.split(separator) if separator else value.split()
    pieces = [p.strip() for p in pieces]
    if len(pieces) <= n:
        return pieces + [""] * (n - len(pieces))
    joiner = separator if separator else " "
    if keep_extra == "first":
        head = joiner.join(pieces[: len(pieces) - n + 1])
        return [head] + pieces[len(pieces) - n + 1 :]
    tail = joiner.join(pieces[n - 1 :])
    return pieces[: n - 1] + [tail]


def _guess_roles(table: TableData) -> None:
    from ..understanding.tables import _role_for

    used: set[str] = set()
    for col in table.columns:
        role, _ = _role_for(col.name)
        if role in COLUMN_ROLES and role not in used:
            col.role = role
            used.add(role)
