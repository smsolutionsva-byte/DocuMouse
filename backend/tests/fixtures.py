"""Hand-built engine output for tests.

These mirror the shape PP-StructureV3 produces after normalisation, so the
understanding/validation/editing layers can be tested without downloading OCR
models. They are test data only — the app never uses them.
"""

from __future__ import annotations

from documouse.processing.types import LayoutBlock, PageInfo, RawDocument, Table, TextLine


def _line(i: int, text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.98) -> TextLine:
    return TextLine(id=f"p0-l{i}", page=0, text=text, bbox=[x0, y0, x1, y1], confidence=conf)


def invoice_raw(*, total: str = "₹23,600.00") -> RawDocument:
    rows = [
        ("ABC Technologies Pvt Ltd", 0.06, 0.040, 0.46, 0.065),
        ("TAX INVOICE", 0.66, 0.042, 0.94, 0.062),
        ("12 MG Road, Bengaluru 560001", 0.06, 0.070, 0.40, 0.082),
        ("GSTIN: 29ABCDE1234F1ZW", 0.06, 0.086, 0.36, 0.098),
        ("Invoice No: INV-1042", 0.62, 0.090, 0.94, 0.102),
        ("Invoice Date: 05 Oct 2026", 0.62, 0.106, 0.94, 0.118),
        ("Due Date: 04 Nov 2026", 0.62, 0.122, 0.94, 0.134),
        ("Bill To:", 0.06, 0.160, 0.16, 0.172),
        ("Mouse & Cheese Co.", 0.06, 0.176, 0.30, 0.188),
        ("44 Park Street, Kolkata", 0.06, 0.192, 0.32, 0.204),
        ("GSTIN: 19AAACM1234K1ZK", 0.06, 0.208, 0.34, 0.220),
        ("Item", 0.06, 0.260, 0.12, 0.272),
        ("Qty", 0.50, 0.260, 0.55, 0.272),
        ("Rate", 0.64, 0.260, 0.70, 0.272),
        ("Amount", 0.82, 0.260, 0.93, 0.272),
        ("Wireless Mouse", 0.06, 0.285, 0.24, 0.297),
        ("2", 0.52, 0.285, 0.53, 0.297),
        ("5,000.00", 0.63, 0.285, 0.72, 0.297),
        ("10,000.00", 0.82, 0.285, 0.93, 0.297),
        ("Cheese Keyboard", 0.06, 0.305, 0.25, 0.317),
        ("4", 0.52, 0.305, 0.53, 0.317),
        ("2,500.00", 0.63, 0.305, 0.72, 0.317),
        ("10,000.00", 0.82, 0.305, 0.93, 0.317),
        ("Sub Total", 0.60, 0.360, 0.72, 0.372),
        ("20,000.00", 0.82, 0.360, 0.93, 0.372),
        ("CGST @ 9%", 0.60, 0.378, 0.72, 0.390),
        ("1,800.00", 0.84, 0.378, 0.93, 0.390),
        ("SGST @ 9%", 0.60, 0.396, 0.72, 0.408),
        ("1,800.00", 0.84, 0.396, 0.93, 0.408),
        ("Grand Total", 0.60, 0.420, 0.74, 0.434),
        (total, 0.80, 0.420, 0.93, 0.434),
        ("Thank you for your business", 0.30, 0.900, 0.70, 0.912),
    ]
    lines = [_line(i, *row) for i, row in enumerate(rows)]
    table = Table(
        id="p0-t0",
        page=0,
        bbox=[0.05, 0.255, 0.95, 0.320],
        rows=[
            ["Item", "Qty", "Rate", "Amount"],
            ["Wireless Mouse", "2", "5,000.00", "10,000.00"],
            ["Cheese Keyboard", "4", "2,500.00", "10,000.00"],
        ],
        header_rows=0,
    )
    blocks = [LayoutBlock(id="p0-b0", page=0, label="doc_title", bbox=[0.05, 0.035, 0.47, 0.07], text="ABC Technologies Pvt Ltd")]
    return RawDocument(engine="test-double", pages=[PageInfo(index=0, width=1654, height=2339)],
                       lines=lines, blocks=blocks, tables=[table])


def receipt_raw() -> RawDocument:
    rows = [
        ("CORNER CAFE", 0.20, 0.02, 0.80, 0.04),
        ("Receipt #4471", 0.25, 0.05, 0.75, 0.06),
        ("Date: 03/10/2026 Time: 18:42", 0.10, 0.07, 0.90, 0.08),
        ("Cappuccino 2 x 3.50 7.00", 0.10, 0.12, 0.90, 0.13),
        ("Croissant 1 x 2.75 2.75", 0.10, 0.14, 0.90, 0.15),
        ("Subtotal 9.75", 0.10, 0.20, 0.90, 0.21),
        ("VAT 20% 1.95", 0.10, 0.22, 0.90, 0.23),
        ("TOTAL £11.70", 0.10, 0.25, 0.90, 0.26),
        ("Paid by VISA ****1234", 0.10, 0.28, 0.90, 0.29),
        ("Thank you! Visit again", 0.15, 0.33, 0.85, 0.34),
    ]
    lines = [_line(i, *row) for i, row in enumerate(rows)]
    return RawDocument(engine="test-double", pages=[PageInfo(index=0, width=600, height=1800)], lines=lines)
