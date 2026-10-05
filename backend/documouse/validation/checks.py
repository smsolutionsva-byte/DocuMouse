"""Deterministic checks on extracted data.

Financial values are never trusted just because an extractor (or an LLM)
produced them. These checks do the arithmetic and flag anything that doesn't
add up. They never change a value: they only report.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..document_data import DocumentData, FieldValue, TableData
from ..understanding.parsing import CURRENCY_CODES, CURRENCY_DISPLAY, gstin_checksum_ok, parse_amount
from ..understanding.schema import schema_for

CONFIDENCE_OK = 0.8
CENT = Decimal("0.01")
ROUNDING = Decimal("1.00")  # invoices often round the payable amount to the nearest unit


@dataclass
class Check:
    id: str
    status: str  # pass | warn | fail | info
    title: str
    detail: str = ""
    fields: list[str] = field(default_factory=list)
    table_id: str | None = None


@dataclass
class Validation:
    checks: list[Check]
    fields: dict[str, dict]  # key -> {"status", "reasons"}
    rows: dict[str, dict[str, list[str]]]  # table_id -> row_id -> reasons
    summary: dict

    def as_dict(self) -> dict:
        return {
            "checks": [asdict(c) for c in self.checks],
            "fields": self.fields,
            "rows": self.rows,
            "summary": self.summary,
        }


def format_money(value: Decimal, currency: str | None = None) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value).quantize(CENT)
    whole, frac = f"{value:.2f}".split(".")
    if currency == "INR" and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1]
        grouped = f"{head},{tail}"
    else:
        grouped = f"{int(whole):,}"
    symbol = CURRENCY_DISPLAY.get(currency or "", "")
    return f"{sign}{symbol}{grouped}.{frac}"


def _amount(f: FieldValue | None) -> Decimal | None:
    if f is None or f.value is None:
        return None
    return parse_amount(f.value)


def _iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate(data: DocumentData, *, today: date | None = None) -> Validation:
    today = today or date.today()
    schema = schema_for(data.doc_type)
    fields = data.fields
    currency = fields.get("currency").value if fields.get("currency") else None
    money = lambda v: format_money(v, currency)  # noqa: E731

    checks: list[Check] = []
    reasons: dict[str, list[str]] = defaultdict(list)
    hard: dict[str, bool] = defaultdict(bool)  # format errors stay flagged even after a person confirms
    rows: dict[str, dict[str, list[str]]] = defaultdict(dict)

    # ---------------------------------------------------------- formats
    for fdef in schema:
        f = fields.get(fdef.key)
        if f is None or f.value is None:
            continue
        v = f.value
        if fdef.kind == "amount" and parse_amount(v) is None:
            reasons[fdef.key].append("This isn't a valid amount.")
            hard[fdef.key] = True
        elif fdef.kind == "date":
            d = _iso_date(v)
            if d is None:
                reasons[fdef.key].append("This isn't a valid date.")
                hard[fdef.key] = True
            elif fdef.key != "due_date" and d > today + timedelta(days=1):
                reasons[fdef.key].append("This date is in the future.")
            elif d.year < 2000:
                reasons[fdef.key].append("This date looks unusually old.")
        elif fdef.kind == "currency" and v.upper() not in CURRENCY_CODES:
            reasons[fdef.key].append("This isn't a currency DocuMouse recognises.")
            hard[fdef.key] = True
        elif fdef.kind == "gstin" and not gstin_checksum_ok(v):
            reasons[fdef.key].append("This GSTIN doesn't pass its checksum — a character may be misread.")
        elif fdef.kind == "time" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            reasons[fdef.key].append("This isn't a valid time.")
            hard[fdef.key] = True

    issued = _iso_date(fields["invoice_date"].value) if "invoice_date" in fields else None
    due = _iso_date(fields["due_date"].value) if "due_date" in fields else None
    if issued and due and due < issued:
        reasons["due_date"].append("The due date is before the invoice date.")

    # ---------------------------------------------------------- line items
    items_sum = _check_line_items(data.line_items(), rows, money)

    # ---------------------------------------------------------- totals
    total = _amount(fields.get("total"))
    subtotal = _amount(fields.get("subtotal"))
    discount = _amount(fields.get("discount"))
    cgst, sgst, igst = (_amount(fields.get(k)) for k in ("cgst", "sgst", "igst"))
    tax = _amount(fields.get("tax"))

    if total is not None:
        checks.append(_total_check(total, subtotal, discount, cgst, sgst, igst, tax, items_sum, money))
        if total < 0:
            reasons["total"].append("The total is negative.")
        biggest = _largest_item_amount(data.line_items())
        if biggest is not None and total + ROUNDING < biggest:
            reasons["total"].append(f"The total is smaller than one of the items ({money(biggest)}).")

    if cgst is not None and sgst is not None:
        if abs(cgst - sgst) <= CENT:
            checks.append(Check("gst_split", "pass", "CGST and SGST match", f"{money(cgst)} each", ["cgst", "sgst"]))
        else:
            checks.append(Check("gst_split", "warn", "CGST and SGST should usually be equal",
                                f"CGST is {money(cgst)} but SGST is {money(sgst)}.", ["cgst", "sgst"]))
    if igst is not None and (cgst is not None or sgst is not None):
        checks.append(Check("gst_kind", "warn", "Both IGST and CGST/SGST were found",
                            "An invoice normally charges either IGST or CGST + SGST, not both.", ["igst", "cgst", "sgst"]))

    if items_sum is not None and subtotal is not None:
        lt = data.line_items()
        if abs(items_sum - subtotal) <= CENT:
            checks.append(Check("items_sum", "pass", "Line items add up to the subtotal", money(items_sum),
                                ["subtotal"], lt.id if lt else None))
        elif total is not None and abs(items_sum - total) <= ROUNDING:
            checks.append(Check("items_sum", "pass", "Line items add up to the total", money(items_sum),
                                ["total"], lt.id if lt else None))
        else:
            checks.append(Check("items_sum", "warn", "Line items don't add up to the subtotal",
                                f"The rows add up to {money(items_sum)}, but the subtotal is {money(subtotal)}.",
                                ["subtotal"], lt.id if lt else None))

    corroborated: set[str] = set()
    for c in checks:
        if c.status in ("warn", "fail"):
            for key in c.fields:
                if fields.get(key) is not None and fields[key].value is not None:
                    reasons[key].append(c.title + ".")
        elif c.status == "pass":
            # Numbers that add up exactly are independently confirmed by the arithmetic.
            corroborated.update(c.fields)
    corroborated -= {k for k, r in reasons.items() if r}

    # ---------------------------------------------------------- per-field status
    statuses: dict[str, dict] = {}
    for fdef in schema:
        f = fields.get(fdef.key) or FieldValue()
        why = list(dict.fromkeys(reasons.get(fdef.key, [])))
        if f.value is None:
            status = "missing" if fdef.required else "empty"
            if f.suggestion:
                why.append("There's a suggestion you can use.")
        elif f.confirmed:
            status = "review" if hard[fdef.key] else "verified"
        else:
            # Most specific reason first: what's wrong beats "not sure".
            why.extend(n for n in f.notes if n)
            if f.suggestion:
                why.append(f.suggestion.reason)
            unsure = f.confidence < CONFIDENCE_OK and fdef.key not in corroborated
            if unsure and not why:
                why.append("DocuMouse isn't fully sure about this one.")
            status = "review" if why or unsure else "verified"
        statuses[fdef.key] = {"status": status, "reasons": why}

    verified = sum(1 for s in statuses.values() if s["status"] == "verified")
    review = sum(1 for s in statuses.values() if s["status"] in ("review", "missing"))
    flagged_rows = sum(len(r) for r in rows.values())
    summary = {
        "verified": verified,
        "needs_review": review,
        "flagged_rows": flagged_rows,
        "tables": len(data.tables),
        "checks_passed": sum(1 for c in checks if c.status == "pass"),
        "checks_failed": sum(1 for c in checks if c.status in ("warn", "fail")),
        "issues": review + flagged_rows,
    }
    return Validation(checks=checks, fields=statuses, rows={k: v for k, v in rows.items()}, summary=summary)


def _total_check(total, subtotal, discount, cgst, sgst, igst, tax, items_sum, money) -> Check:
    base, base_name = subtotal, "Subtotal"
    if base is None and items_sum is not None:
        base, base_name = items_sum, "Line items"
    if base is None:
        return Check("total", "info", "Not enough information to check the total",
                     "DocuMouse needs a subtotal or line items to do the arithmetic.", ["total"])

    parts: list[tuple[str, Decimal]] = []
    components = [(n, v) for n, v in (("CGST", cgst), ("SGST", sgst), ("IGST", igst)) if v is not None]
    if components:
        parts.extend(components)
        if tax is not None and abs(tax - sum(v for _, v in components)) > CENT:
            parts.append(("tax", tax))  # e.g. a cess on top of GST
    elif tax is not None:
        parts.append(("tax", tax))
    d = abs(discount) if discount is not None else Decimal(0)

    def describe(include_discount: bool, include: list[tuple[str, Decimal]]) -> tuple[Decimal, str]:
        value = base - (d if include_discount else 0) + sum(v for _, v in include)
        text = f"{base_name} {money(base)}"
        if include_discount and d:
            text += f" − discount {money(d)}"
        for name, v in include:
            text += f" + {name} {money(v)}"
        return value, text

    attempts = [describe(True, parts)]
    if d:
        attempts.append(describe(False, parts))  # discount already applied in the subtotal
    if len(parts) > len(components) and components:
        attempts.append(describe(True, components))  # separate "tax" line was a total of the components

    involved = ["total", "subtotal" if subtotal is not None else None, "discount" if d else None]
    involved += [k for k, v in (("cgst", cgst), ("sgst", sgst), ("igst", igst), ("tax", tax)) if v is not None]
    involved = [k for k in involved if k]

    for expected, text in attempts:
        diff = abs(expected - total)
        if diff <= CENT:
            return Check("total", "pass", "Total checks out", f"{text} = {money(total)}", involved)
        if diff <= ROUNDING:
            return Check("total", "pass", "Total checks out",
                         f"{text} = {money(expected)}, rounded to {money(total)}", involved)
    expected, text = attempts[0]
    return Check(
        "total", "warn", "Total doesn't match the extracted components",
        f"{text} = {money(expected)}, but the total says {money(total)} "
        f"(a difference of {money(abs(expected - total))}).",
        involved,
    )


def _check_line_items(table: TableData | None, rows: dict, money) -> Decimal | None:
    if table is None:
        return None
    role = {c.role: c.id for c in table.columns if c.role}
    q_id, p_id, a_id, t_id = role.get("quantity"), role.get("unit_price"), role.get("amount"), role.get("tax")
    total = Decimal(0)
    all_amounts = a_id is not None
    item_rows = [r for r in table.rows if r.kind == "item"]
    for r in item_rows:
        q = parse_amount(r.cells.get(q_id, "")) if q_id else None
        p = parse_amount(r.cells.get(p_id, "")) if p_id else None
        a = parse_amount(r.cells.get(a_id, "")) if a_id else None
        t = parse_amount(r.cells.get(t_id, "")) if t_id else None
        if q_id and r.cells.get(q_id, "").strip() and q is None:
            rows.setdefault(table.id, {}).setdefault(r.id, []).append("Quantity isn't a number.")
        if a_id and r.cells.get(a_id, "").strip() and a is None:
            rows.setdefault(table.id, {}).setdefault(r.id, []).append("Amount isn't a number.")
        if q is not None and p is not None and a is not None:
            expected = q * p
            tolerance = max(CENT, abs(a) * Decimal("0.005"))
            ok = abs(expected - a) <= tolerance or (t is not None and abs(expected + t - a) <= tolerance)
            if not ok:
                rows.setdefault(table.id, {}).setdefault(r.id, []).append(
                    f"{_plain(q)} × {money(p)} = {money(expected)}, but this row says {money(a)}."
                )
        if a is None:
            all_amounts = False
        else:
            total += a
    if not item_rows or not all_amounts:
        return None
    return total


def _largest_item_amount(table: TableData | None) -> Decimal | None:
    if table is None:
        return None
    amount_col = next((c.id for c in table.columns if c.role == "amount"), None)
    if amount_col is None:
        return None
    values = [parse_amount(r.cells.get(amount_col, "")) for r in table.rows if r.kind == "item"]
    values = [v for v in values if v is not None]
    return max(values) if values else None


def _plain(d: Decimal) -> str:
    return format(d.normalize(), "f") if d == d.to_integral() else str(d)
