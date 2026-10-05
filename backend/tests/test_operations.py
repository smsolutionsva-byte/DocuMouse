import pytest

from documouse.document_data import DocumentData
from documouse.editing.operations import OperationError, apply_operations, parse_operations, split_value
from documouse.understanding.extract import extract

from .fixtures import invoice_raw


@pytest.fixture()
def data() -> DocumentData:
    return extract(invoice_raw(), "invoice")


def ops(*raw):
    return parse_operations(list(raw))


def test_apply_does_not_mutate_input(data):
    before = data.model_dump()
    apply_operations(data, ops({"op": "set_field", "field": "vendor", "value": "X"}))
    assert data.model_dump() == before


def test_split_and_merge_columns(data):
    t = data.line_items()
    merged = apply_operations(data, ops({"op": "merge_columns", "table_id": t.id,
                                         "column_ids": [t.columns[1].id, t.columns[2].id], "name": "Qty Price"}))
    mt = merged.line_items()
    assert [c.name for c in mt.columns] == ["Item", "Qty Price", "Amount"]
    assert mt.rows[0].cells[mt.columns[1].id] == "2 5,000.00"

    split = apply_operations(merged, ops({"op": "split_column", "table_id": t.id, "column_id": mt.columns[1].id,
                                          "new_columns": ["Quantity", "Price"]}))
    st = split.line_items()
    assert [c.name for c in st.columns] == ["Item", "Quantity", "Price", "Amount"]
    assert [st.rows[0].cells[c.id] for c in st.columns] == ["Wireless Mouse", "2", "5,000.00", "10,000.00"]


def test_split_value_never_drops_text():
    assert split_value("Blue Wireless Mouse 2", 2, None, "first") == ["Blue Wireless Mouse", "2"]
    assert split_value("2 Blue Mouse", 2, None, "last") == ["2", "Blue Mouse"]
    assert split_value("", 3, None) == ["", "", ""]
    assert split_value("a|b", 3, "|") == ["a", "b", ""]


def test_rows_and_tables(data):
    t = data.line_items()
    out = apply_operations(data, ops(
        {"op": "add_row", "table_id": t.id},
        {"op": "add_row", "table_id": t.id, "after_row_id": t.rows[0].id, "cells": {t.columns[0].id: "Mouse pad"}},
    ))
    rows = out.line_items().rows
    assert len(rows) == 4 and rows[1].cells[t.columns[0].id] == "Mouse pad"
    out = apply_operations(out, ops({"op": "delete_blank_rows", "table_id": t.id}))
    assert len(out.line_items().rows) == 3
    out = apply_operations(out, ops({"op": "split_table", "table_id": t.id, "before_row_id": rows[2].id}))
    assert len(out.tables) == 2 and len(out.tables[1].rows) == 1
    out = apply_operations(out, ops({"op": "move_column", "table_id": t.id, "column_id": t.columns[3].id, "to_index": 0}))
    assert out.line_items().columns[0].name == "Amount"


def test_invalid_operations_are_rejected(data):
    with pytest.raises(OperationError):
        apply_operations(data, ops({"op": "set_field", "field": "favourite_colour", "value": "x"}))
    with pytest.raises(OperationError):
        apply_operations(data, ops({"op": "delete_rows", "table_id": "t1", "row_ids": ["nope"]}))
    with pytest.raises(Exception):
        parse_operations([{"op": "run_sql", "sql": "DROP TABLE documents"}])


def test_set_field_canonicalises_and_keeps_unparseable(data):
    out = apply_operations(data, ops({"op": "set_field", "field": "total", "value": "₹ 24,000"}))
    assert out.fields["total"].value == "24000.00" and out.fields["total"].confirmed
    out = apply_operations(data, ops({"op": "set_field", "field": "total", "value": "about twenty"}))
    assert out.fields["total"].value == "about twenty"  # kept, and validation will flag it
