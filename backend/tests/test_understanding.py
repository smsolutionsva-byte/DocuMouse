from datetime import date
from decimal import Decimal

from documouse.understanding.classify import classify
from documouse.understanding.extract import extract, reconcile
from documouse.understanding.llm_extract import LLMField, ground
from documouse.understanding.parsing import (
    find_dates,
    gstin_checksum_ok,
    parse_amount,
)
from documouse.understanding.schema import field_def
from documouse.validation import format_money, validate

from .fixtures import invoice_raw, receipt_raw


def test_parse_amount_formats():
    assert parse_amount("₹23,600.00") == Decimal("23600.00")
    assert parse_amount("1,23,456.78") == Decimal("123456.78")
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount("12,50") == Decimal("12.50")
    assert parse_amount("(100.00)") == Decimal("-100.00")
    assert parse_amount("Rs. 500") == Decimal("500")
    assert parse_amount("abc") is None


def test_dates_and_ambiguity():
    [d] = find_dates("Invoice Date: 04/05/2026", dayfirst=True)
    assert d.value == date(2026, 5, 4) and d.ambiguous
    [d] = find_dates("05 Oct 2026")
    assert d.value == date(2026, 10, 5) and not d.ambiguous
    [d] = find_dates("October 4, 2026")
    assert d.value == date(2026, 10, 4)
    [d] = find_dates("25/12/2026")
    assert not d.ambiguous


def test_gstin_checksum():
    assert gstin_checksum_ok("27AAPFU0939F1ZV")
    assert not gstin_checksum_ok("27AAPFU0939F1ZX")


def test_format_money_indian_grouping():
    assert format_money(Decimal("123456.5"), "INR") == "₹1,23,456.50"
    assert format_money(Decimal("1234.5"), "USD") == "$1,234.50"


def test_classifies_invoice_and_receipt():
    inv = classify(invoice_raw())
    assert inv.detected_type == "invoice" and inv.confidence > 0.9
    rec = classify(receipt_raw())
    assert rec.detected_type == "receipt" and rec.confidence > 0.7


def test_invoice_extraction_and_validation():
    data = extract(invoice_raw(), "invoice")
    f = data.fields
    assert f["vendor"].value == "ABC Technologies Pvt Ltd"
    assert f["invoice_number"].value == "INV-1042"
    assert f["invoice_date"].value == "2026-10-05"
    assert f["due_date"].value == "2026-11-04"
    assert f["subtotal"].value == "20000.00"
    assert f["cgst"].value == "1800.00"
    assert f["sgst"].value == "1800.00"
    assert f["total"].value == "23600.00"
    assert f["currency"].value == "INR"
    assert f["gstin"].value == "29ABCDE1234F1ZW"  # the seller's, not the customer's
    assert "Mouse & Cheese Co." in (f["billing_address"].value or "")
    assert f["igst"].value is None  # not invented
    assert f["total"].source is not None

    items = data.line_items()
    assert items is not None
    assert [c.role for c in items.columns] == ["item", "quantity", "unit_price", "amount"]
    assert len(items.rows) == 2

    # Each row points at its own band on the page, not its neighbours'.
    second = items.rows[1].source
    assert second is not None and 0.30 <= second.bbox[1] and second.bbox[3] <= 0.32

    v = validate(data, today=date(2026, 10, 6))
    total_check = next(c for c in v.checks if c.id == "total")
    assert total_check.status == "pass", total_check
    assert next(c for c in v.checks if c.id == "items_sum").status == "pass"
    assert v.fields["total"]["status"] == "verified"
    # CGST/SGST were read with modest confidence, but the arithmetic confirms them.
    assert v.fields["cgst"]["status"] == "verified"


def test_mismatched_total_is_flagged_not_fixed():
    data = extract(invoice_raw(total="₹24,000.00"), "invoice")
    assert data.fields["total"].value == "24000.00"
    v = validate(data, today=date(2026, 10, 6))
    check = next(c for c in v.checks if c.id == "total")
    assert check.status == "warn"
    assert "400.00" in check.detail
    assert v.fields["total"]["status"] == "review"


def test_receipt_extraction():
    data = extract(receipt_raw(), "receipt")
    f = data.fields
    assert f["merchant"].value == "CORNER CAFE"
    assert f["date"].value == "2026-10-03"
    assert f["time"].value == "18:42"
    assert f["total"].value == "11.70"
    assert f["currency"].value == "GBP"
    assert f["payment_method"].value == "Card (Visa)"
    v = validate(data, today=date(2026, 10, 6))
    assert next(c for c in v.checks if c.id == "total").status == "pass"


def test_llm_values_must_be_grounded():
    raw = invoice_raw()
    fdef = field_def("invoice", "total")
    grounded = ground(fdef, "23,600.00", [], raw, dayfirst=True)
    assert grounded.grounded and grounded.value == "23600.00"
    invented = ground(fdef, "99,999.00", [], raw, dayfirst=True)
    assert not invented.grounded and invented.value is None

    rule = extract(raw, "invoice").fields["igst"]
    merged = reconcile(rule, LLMField("igst", None, "1234.00", False, []))
    assert merged.value is None  # never used as a value
    assert merged.suggestion is not None and merged.suggestion.value == "1234.00"
