"""What DocuMouse extracts for each document type.

Adding a document type means adding a schema here (plus label hints for the
rule-based extractor). Nothing else in the pipeline is type-specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FieldKind = Literal["text", "multiline", "amount", "date", "time", "currency", "gstin"]
DocType = Literal["invoice", "receipt", "unknown"]
DOC_TYPES: tuple[str, ...] = ("invoice", "receipt", "unknown")
DOC_TYPE_LABELS = {"invoice": "Invoice", "receipt": "Receipt", "unknown": "Other document"}


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    kind: FieldKind
    group: str
    required: bool = False
    # Label text that typically precedes the value on the page (lower-case, normalised).
    hints: tuple[str, ...] = field(default_factory=tuple)
    # Hints that must NOT match (e.g. "sub total" must not be read as "total").
    exclude: tuple[str, ...] = field(default_factory=tuple)


INVOICE_FIELDS: tuple[FieldDef, ...] = (
    FieldDef("vendor", "Vendor", "text", "From", required=True,
             hints=("from", "seller", "supplier", "vendor", "sold by", "billed by")),
    FieldDef("gstin", "GSTIN", "gstin", "From", hints=("gstin", "gst no", "gst number", "gstin uin")),
    FieldDef("invoice_number", "Invoice number", "text", "Invoice", required=True,
             hints=("invoice no", "invoice number", "invoice #", "invoice id", "inv no", "bill no",
                    "bill number", "invoice", "inv"),
             exclude=("invoice date", "invoice dt", "invoice to", "tax invoice", "invoice amount", "invoice total")),
    FieldDef("invoice_date", "Invoice date", "date", "Invoice", required=True,
             hints=("invoice date", "date of invoice", "inv date", "bill date", "issue date", "date of issue",
                    "invoice dt", "dated", "date"),
             exclude=("due date", "due", "payment date", "order date", "delivery date", "supply date")),
    FieldDef("due_date", "Due date", "date", "Invoice", hints=("due date", "payment due", "due by", "due on", "pay by")),
    FieldDef("currency", "Currency", "currency", "Invoice"),
    FieldDef("billing_address", "Billed to", "multiline", "Invoice",
             hints=("bill to", "billed to", "billing address", "invoice to", "customer", "buyer", "sold to")),
    FieldDef("subtotal", "Subtotal", "amount", "Amounts",
             hints=("sub total", "subtotal", "taxable value", "taxable amount", "total before tax", "net amount",
                    "amount before tax", "total taxable value")),
    FieldDef("discount", "Discount", "amount", "Amounts", hints=("discount", "less discount")),
    FieldDef("cgst", "CGST", "amount", "Amounts", hints=("cgst", "central gst", "central tax")),
    FieldDef("sgst", "SGST", "amount", "Amounts", hints=("sgst", "utgst", "state gst", "state tax")),
    FieldDef("igst", "IGST", "amount", "Amounts", hints=("igst", "integrated gst", "integrated tax")),
    FieldDef("tax", "Tax", "amount", "Amounts",
             hints=("total tax", "tax amount", "vat", "sales tax", "gst", "tax"),
             exclude=("cgst", "sgst", "igst", "utgst", "before tax", "taxable", "tax invoice", "incl", "excl",
                      "tax id", "tax no", "gstin")),
    FieldDef("total", "Total", "amount", "Amounts", required=True,
             hints=("grand total", "total amount", "amount due", "total due", "balance due", "invoice total",
                    "net payable", "amount payable", "total payable", "total inr", "total"),
             exclude=("sub total", "subtotal", "total tax", "total before tax", "total taxable", "total qty",
                      "total quantity", "total items", "total discount")),
)

RECEIPT_FIELDS: tuple[FieldDef, ...] = (
    FieldDef("merchant", "Merchant", "text", "From", required=True),
    FieldDef("date", "Date", "date", "Purchase", required=True, hints=("date", "dated", "txn date", "bill date")),
    FieldDef("time", "Time", "time", "Purchase", hints=("time",)),
    FieldDef("payment_method", "Paid with", "text", "Purchase",
             hints=("payment method", "payment mode", "paid by", "paid via", "tender", "mode of payment")),
    FieldDef("currency", "Currency", "currency", "Purchase"),
    FieldDef("subtotal", "Subtotal", "amount", "Amounts", hints=("sub total", "subtotal", "net amount", "taxable")),
    FieldDef("discount", "Discount", "amount", "Amounts", hints=("discount", "savings", "you saved")),
    FieldDef("cgst", "CGST", "amount", "Amounts", hints=("cgst", "central gst", "central tax")),
    FieldDef("sgst", "SGST", "amount", "Amounts", hints=("sgst", "utgst", "state gst", "state tax")),
    FieldDef("igst", "IGST", "amount", "Amounts", hints=("igst", "integrated gst", "integrated tax")),
    FieldDef("tax", "Tax", "amount", "Amounts",
             hints=("total tax", "tax", "vat", "gst", "sales tax"),
             exclude=("cgst", "sgst", "igst", "utgst", "before tax", "taxable", "incl", "excl", "tax id", "gstin")),
    FieldDef("total", "Total", "amount", "Amounts", required=True,
             hints=("grand total", "total amount", "amount paid", "total paid", "net payable", "total due",
                    "balance due", "total"),
             exclude=("sub total", "subtotal", "total tax", "total qty", "total items", "total savings",
                      "total discount")),
)

SCHEMAS: dict[str, tuple[FieldDef, ...]] = {
    "invoice": INVOICE_FIELDS,
    "receipt": RECEIPT_FIELDS,
    "unknown": (),
}

# Column roles for line-item tables. Header hints are matched against normalised header text.
COLUMN_ROLES: dict[str, tuple[str, ...]] = {
    "item": ("item", "items", "product", "particulars", "goods", "service", "services", "item name", "name"),
    "description": ("description", "desc", "details", "item description", "description of goods"),
    "quantity": ("qty", "quantity", "qnty", "units", "nos", "hrs", "hours"),
    "unit_price": ("unit price", "price", "rate", "unit cost", "price per unit", "rate per unit", "unit rate", "mrp"),
    "tax": ("tax", "gst", "vat", "tax amount", "gst amount", "cgst", "sgst", "igst"),
    "amount": ("amount", "total", "line total", "net amount", "value", "taxable value", "total amount"),
}
LINE_ITEM_FIELDS = ("item", "description", "quantity", "unit_price", "tax", "amount")


def schema_for(doc_type: str) -> tuple[FieldDef, ...]:
    return SCHEMAS.get(doc_type, ())


def field_def(doc_type: str, key: str) -> FieldDef | None:
    return next((f for f in schema_for(doc_type) if f.key == key), None)
