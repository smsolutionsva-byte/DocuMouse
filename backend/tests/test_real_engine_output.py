"""Regression tests on *recorded* PaddleOCR output.

`fixtures_real/*.raw.json` is what PaddleOCR 3.7 / PP-StructureV3 (PaddlePaddle 3.2.2,
CPU, "fast" preset) actually produced for the documents in `samples/`, normalised by
`PaddleStructureEngine`. Re-record with `python tests/record_engine_output.py` after
changing the engine adapter or upgrading PaddleOCR.
"""

from datetime import date
from pathlib import Path

import pytest

from documouse.processing.types import RawDocument
from documouse.understanding.classify import classify
from documouse.understanding.extract import extract
from documouse.validation import validate

FIXTURES = Path(__file__).parent / "fixtures_real"


def load(name: str) -> RawDocument:
    return RawDocument.model_validate_json((FIXTURES / f"{name}.raw.json").read_bytes())


INVOICE_EXPECTED = {
    "vendor": "Nimbus Cloud Services Pvt Ltd",
    "gstin": "29AABCN1234M1ZD",
    "invoice_number": "NCS/2026/0417",
    "invoice_date": "2026-09-12",
    "due_date": "2026-10-12",
    "currency": "INR",
    "subtotal": "22100.00",
    "cgst": "1989.00",
    "sgst": "1989.00",
    "total": "26078.00",
    "igst": None,
    "discount": None,
}


@pytest.mark.parametrize("name", ["nimbus_invoice", "nimbus_invoice_scan"])
def test_real_invoice(name):
    raw = load(name)
    c = classify(raw)
    assert c.detected_type == "invoice" and c.confidence > 0.9

    data = extract(raw, "invoice")
    for key, expected in INVOICE_EXPECTED.items():
        assert data.fields[key].value == expected, key
    assert data.fields["billing_address"].value.startswith("Mouse & Cheese Traders")

    items = data.line_items()
    assert items is not None and len(items.rows) == 4
    roles = {c.role: c.id for c in items.columns}
    assert items.rows[0].cells[roles["description"]] == "Cloud hosting - Standard plan (Sep)"
    assert [r.cells[roles["amount"]] for r in items.rows] == ["12,000.00", "5,000.00", "1,500.00", "3,600.00"]

    v = validate(data, today=date(2026, 10, 5))
    assert {c.id: c.status for c in v.checks} == {"total": "pass", "gst_split": "pass", "items_sum": "pass"}
    assert v.summary["needs_review"] == 0, v.fields


def test_real_receipt_without_ruled_table():
    raw = load("daily_grind_receipt")
    assert classify(raw).detected_type == "receipt"
    data = extract(raw, "receipt")
    f = data.fields
    assert f["merchant"].value == "THE DAILY GRIND CAFE"  # joined from two engine boxes
    assert f["date"].value == "2026-10-03"  # 03/10/2026 on a ₹ receipt is day-first
    assert f["time"].value == "18:42"
    assert f["payment_method"].value == "UPI"
    assert (f["subtotal"].value, f["cgst"].value, f["sgst"].value, f["total"].value) == ("950.00", "23.75", "23.75", "997.50")

    items = data.line_items()
    assert items is not None
    roles = {c.role: c.id for c in items.columns}
    assert [(r.cells[roles["item"]], r.cells[roles["quantity"]], r.cells[roles["amount"]]) for r in items.rows] == [
        ("Cappuccino", "2", "360.00"),
        ("Masala Chai xl", "", "90.00"),  # the engine read "x1" as "xl"; kept as printed
        ("Blueberry Muffin", "2", "280.00"),
        ("Paneer Sandwich xl", "", "220.00"),
    ]
    v = validate(data, today=date(2026, 10, 5))
    assert {c.id: c.status for c in v.checks} == {"total": "pass", "gst_split": "pass", "items_sum": "pass"}
