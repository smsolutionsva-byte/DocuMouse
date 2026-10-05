"""Before/after previews and human-readable descriptions of changes."""

from __future__ import annotations

from ..document_data import DocumentData, TableData
from ..understanding.schema import field_def
from .operations import (
    AddColumn,
    AddRow,
    AddTable,
    ConfirmField,
    DeleteBlankRows,
    DeleteColumn,
    DeleteRows,
    DeleteTable,
    MergeColumns,
    MergeRows,
    MoveColumn,
    RenameColumn,
    RenameTable,
    SetCell,
    SetColumnRole,
    SetField,
    SetRowKind,
    SplitColumn,
    SplitTable,
)


def build_preview(before: DocumentData, after: DocumentData) -> dict:
    """What changes, in a shape the review screen can render as Before → After."""
    fields = []
    for key in dict.fromkeys(list(before.fields) + list(after.fields)):
        b, a = before.fields.get(key), after.fields.get(key)
        bv, av = (b.value if b else None), (a.value if a else None)
        if bv != av:
            fdef = field_def(after.doc_type, key)
            fields.append({"field": key, "label": fdef.label if fdef else key, "kind": fdef.kind if fdef else "text",
                           "before": bv, "after": av})

    tables = []
    before_tables = {t.id: t for t in before.tables}
    after_tables = {t.id: t for t in after.tables}
    for tid in dict.fromkeys(list(before_tables) + list(after_tables)):
        b, a = before_tables.get(tid), after_tables.get(tid)
        if b is not None and a is not None and _table_json(b) == _table_json(a):
            continue
        tables.append({
            "table_id": tid,
            "before": _table_json(b) if b else None,
            "after": _table_json(a) if a else None,
            "changed_rows": _changed_rows(b, a),
        })
    return {"fields": fields, "tables": tables}


def _table_json(t: TableData) -> dict:
    return {
        "title": t.title,
        "columns": [c.model_dump() for c in t.columns],
        "rows": [{"id": r.id, "kind": r.kind, "cells": r.cells} for r in t.rows],
    }


def _changed_rows(b: TableData | None, a: TableData | None) -> list[str]:
    if b is None or a is None:
        return []
    old = {r.id: r.cells for r in b.rows}
    return [r.id for r in a.rows if old.get(r.id) != r.cells]


def describe(ops: list, data: DocumentData) -> str:
    """A short history message like “Corrected vendor” or “Split ‘Qty Price’ into 2 columns”."""
    if not ops:
        return "No changes"
    parts = [_describe_one(op, data) for op in ops]
    unique = list(dict.fromkeys(parts))
    if len(unique) == 1:
        if len(parts) > 1 and isinstance(ops[0], SetCell):
            return f"Edited {len(parts)} cells"
        return unique[0]
    if all(isinstance(op, SetCell) for op in ops):
        return f"Edited {len(ops)} cells"
    if len(unique) == 2:
        return f"{unique[0]}; {unique[1][0].lower()}{unique[1][1:]}"
    return f"{unique[0]} and {len(unique) - 1} more changes"


def _col_name(data: DocumentData, table_id: str, column_id: str) -> str:
    t = data.table(table_id)
    c = t.column(column_id) if t else None
    return c.name if c else column_id


def _describe_one(op, data: DocumentData) -> str:  # noqa: C901
    if isinstance(op, SetField):
        fdef = field_def(data.doc_type, op.field)
        label = fdef.label if fdef else op.field
        return f"Cleared {label.lower()}" if not op.value else f"Corrected {label.lower()}"
    if isinstance(op, ConfirmField):
        fdef = field_def(data.doc_type, op.field)
        return f"Confirmed {(fdef.label if fdef else op.field).lower()}"
    if isinstance(op, SetCell):
        return "Edited a cell"
    if isinstance(op, AddRow):
        return "Added a row"
    if isinstance(op, DeleteRows):
        return "Deleted a row" if len(op.row_ids) == 1 else f"Deleted {len(op.row_ids)} rows"
    if isinstance(op, DeleteBlankRows):
        return "Removed blank rows"
    if isinstance(op, MergeRows):
        return f"Merged {len(op.row_ids)} rows"
    if isinstance(op, SetRowKind):
        return "Marked a row as a total" if op.kind == "summary" else "Marked a row as an item"
    if isinstance(op, AddColumn):
        return f"Added column “{op.name}”"
    if isinstance(op, DeleteColumn):
        return f"Deleted column “{_col_name(data, op.table_id, op.column_id)}”"
    if isinstance(op, RenameColumn):
        return f"Renamed “{_col_name(data, op.table_id, op.column_id)}” to “{op.name}”"
    if isinstance(op, MoveColumn):
        return f"Moved column “{_col_name(data, op.table_id, op.column_id)}”"
    if isinstance(op, SetColumnRole):
        return f"Changed what “{_col_name(data, op.table_id, op.column_id)}” contains"
    if isinstance(op, SplitColumn):
        return f"Split “{_col_name(data, op.table_id, op.column_id)}” into {' | '.join(op.new_columns)}"
    if isinstance(op, MergeColumns):
        names = [_col_name(data, op.table_id, c) for c in op.column_ids]
        return f"Merged {' + '.join(names)} into “{op.name}”"
    if isinstance(op, AddTable):
        return f"Added table “{op.title}”"
    if isinstance(op, SplitTable):
        return "Split a table in two"
    if isinstance(op, RenameTable):
        return f"Renamed a table to “{op.title}”"
    if isinstance(op, DeleteTable):
        t = data.table(op.table_id)
        return f"Deleted table “{t.title if t else op.table_id}”"
    return "Edited the document"
