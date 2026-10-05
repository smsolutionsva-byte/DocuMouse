"""Turn a plain-language request into proposed operations.

    user request → LLM (or simple patterns) → structured operations
    → validated here → previewed → applied only after the user approves

The assistant never writes anything. It returns operations that the API
validates, previews and only applies when the user clicks Approve.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from ..document_data import DocumentData
from ..llm.base import LLMError, LLMProvider
from ..understanding.schema import DOC_TYPE_LABELS, schema_for
from .operations import OperationError, apply_operations, parse_operations

log = logging.getLogger(__name__)

MAX_ROWS_IN_PROMPT = 80


@dataclass
class Proposal:
    reply: str
    operations: list = field(default_factory=list)
    source: str = "rules"  # rules | llm


OPERATIONS_HELP = """Available operations (use the exact ids from the document):
{"op":"set_field","field":"<field key>","value":"<new value or null>"}   dates as YYYY-MM-DD, amounts as plain numbers
{"op":"confirm_field","field":"<field key>"}
{"op":"set_cell","table_id":"t1","row_id":"r3","column_id":"c2","value":"..."}
{"op":"add_row","table_id":"t1","after_row_id":"r3 or null","cells":{"c1":"..."}}
{"op":"delete_rows","table_id":"t1","row_ids":["r3"]}
{"op":"delete_blank_rows","table_id":"t1"}
{"op":"merge_rows","table_id":"t1","row_ids":["r3","r4"],"separator":" "}
{"op":"set_row_kind","table_id":"t1","row_id":"r9","kind":"item|summary"}
{"op":"add_column","table_id":"t1","name":"...","after_column_id":"c2 or null"}
{"op":"delete_column","table_id":"t1","column_id":"c2"}
{"op":"rename_column","table_id":"t1","column_id":"c2","name":"..."}
{"op":"move_column","table_id":"t1","column_id":"c2","to_index":0}
{"op":"set_column_role","table_id":"t1","column_id":"c2","role":"item|description|quantity|unit_price|tax|amount|null"}
{"op":"split_column","table_id":"t1","column_id":"c2","new_columns":["Quantity","Price"],"separator":null,"keep_extra":"first|last"}
{"op":"merge_columns","table_id":"t1","column_ids":["c2","c3"],"name":"...","separator":" "}
{"op":"add_table","title":"...","columns":["..."],"line_items":false}
{"op":"split_table","table_id":"t1","before_row_id":"r7","title":"..."}
{"op":"rename_table","table_id":"t1","title":"..."}
{"op":"delete_table","table_id":"t1"}"""

SYSTEM_PROMPT = f"""You help a non-technical person fix the data DocuMouse extracted from a document.
Turn their request into operations from the list below. Return JSON only:
{{"reply": "<one short, friendly sentence saying what you'll change, or a short question if unclear>",
  "operations": [ ... ]}}
Rules:
- Only use the operations listed. Never invent ids; use ids shown in the document state.
- Do the smallest change that satisfies the request. Do not change anything else.
- If the request is ambiguous or impossible, return no operations and ask one short question.
- Row numbers the user mentions are 1-based positions as shown (#1, #2, ...).
- For split_column, "keep_extra":"first" keeps leftover words in the first new column
  (e.g. "Blue Mouse 2" → Item | Qty), "last" keeps them in the last column.

{OPERATIONS_HELP}"""


def document_state(data: DocumentData) -> str:
    lines = [f"Document type: {DOC_TYPE_LABELS.get(data.doc_type, data.doc_type)}", "Fields:"]
    for fdef in schema_for(data.doc_type):
        f = data.fields.get(fdef.key)
        lines.append(f"  {fdef.key} ({fdef.label}): {json.dumps(f.value if f else None, ensure_ascii=False)}")
    for t in data.tables:
        cols = ", ".join(f"{c.id}={json.dumps(c.name, ensure_ascii=False)}" + (f"[{c.role}]" if c.role else "") for c in t.columns)
        lines.append(f"Table {t.id} “{t.title}” columns: {cols}")
        for i, r in enumerate(t.rows[:MAX_ROWS_IN_PROMPT], start=1):
            cells = " | ".join(f"{cid}:{json.dumps(r.cells.get(c.id, ''), ensure_ascii=False)}" for c in t.columns for cid in [c.id])
            lines.append(f"  #{i} {r.id}{' (total row)' if r.kind == 'summary' else ''}: {cells}")
        if len(t.rows) > MAX_ROWS_IN_PROMPT:
            lines.append(f"  … {len(t.rows) - MAX_ROWS_IN_PROMPT} more rows")
    return "\n".join(lines)


def interpret(message: str, data: DocumentData, llm: LLMProvider | None) -> Proposal:
    message = message.strip()
    if not message:
        return Proposal("Tell me what to change — for example “the vendor is Acme Technologies”.")
    if llm is not None:
        proposal = _interpret_llm(message, data, llm)
        if proposal is not None:
            return proposal
    return interpret_rules(message, data)


def _interpret_llm(message: str, data: DocumentData, llm: LLMProvider) -> Proposal | None:
    user = f"Document state:\n{document_state(data)}\n\nRequest: {message}"
    try:
        response = llm.complete_json(SYSTEM_PROMPT, user, max_tokens=1500)
    except LLMError:
        log.warning("Assistant LLM call failed; falling back to simple commands", exc_info=True)
        return None
    reply = str(response.get("reply") or "").strip()[:400]
    raw_ops = response.get("operations") or []
    try:
        ops = parse_operations(raw_ops)
        apply_operations(data, ops, author="ai")  # dry run: ids and arguments must make sense
    except (ValidationError, OperationError, TypeError) as exc:
        log.info("Assistant proposed invalid operations: %s", exc)
        return Proposal("I couldn't turn that into a safe change. Could you say it a little differently?", [], "llm")
    return Proposal(reply or ("Here's what I'd change." if ops else "I'm not sure what to change."), ops, "llm")


# ------------------------------------------------------------------ simple patterns (no LLM)

_FIELD_SYNONYMS = {
    "vendor": ("vendor", "vendor name", "seller", "supplier", "company", "company name", "from"),
    "merchant": ("merchant", "store", "shop", "merchant name", "restaurant"),
    "invoice_number": ("invoice number", "invoice no", "invoice #", "invoice num", "inv no", "bill number", "number"),
    "invoice_date": ("invoice date", "date", "bill date", "issue date"),
    "date": ("date", "purchase date"),
    "due_date": ("due date", "due"),
    "total": ("total", "grand total", "total amount", "amount due", "amount"),
    "subtotal": ("subtotal", "sub total", "sub-total"),
    "discount": ("discount",),
    "tax": ("tax", "vat", "total tax"),
    "cgst": ("cgst",),
    "sgst": ("sgst",),
    "igst": ("igst",),
    "currency": ("currency",),
    "gstin": ("gstin", "gst number", "gst no"),
    "billing_address": ("billing address", "bill to", "billed to", "customer", "address"),
    "payment_method": ("payment method", "payment", "paid with", "paid by"),
    "time": ("time",),
}

HELP = ("Without an AI provider I understand simple requests like “change the vendor to Acme”, "
        "“delete blank rows”, “delete row 3”, “rename column Rate to Price” or “split Qty Price into Qty and Price”.")


def _field_for(phrase: str, data: DocumentData) -> str | None:
    phrase = re.sub(r"[^a-z0-9# ]+", " ", phrase.lower()).strip()
    phrase = re.sub(r"^(the|my|this)\s+", "", phrase)
    phrase = re.sub(r"\s+(name|value|field)$", "", phrase) if phrase not in ("vendor name", "company name") else phrase
    keys = [f.key for f in schema_for(data.doc_type)]
    for key in keys:
        if phrase in _FIELD_SYNONYMS.get(key, ()) or phrase == key.replace("_", " "):
            return key
    return None


def _clean_value(value: str) -> str:
    return value.strip().strip("\"'“”‘’").rstrip(".!").strip()


def _target_table(data: DocumentData):
    return data.line_items() or (data.tables[0] if data.tables else None)


def _column_by_name(table, name: str):
    n = name.strip().lower().strip("\"'“”")
    exact = [c for c in table.columns if c.name.lower() == n]
    if exact:
        return exact[0]
    partial = [c for c in table.columns if n and (n in c.name.lower() or c.name.lower() in n)]
    return partial[0] if len(partial) == 1 else None


def interpret_rules(message: str, data: DocumentData) -> Proposal:  # noqa: C901
    text = " ".join(message.split())
    low = text.lower()
    table = _target_table(data)

    # “delete blank/empty rows”
    if re.search(r"\b(delete|remove|drop|clear)\b.*\b(blank|empty)\s+rows?\b", low):
        if table is None:
            return Proposal("There's no table to clean up.")
        return Proposal("I'll remove the blank rows.", [_op({"op": "delete_blank_rows", "table_id": table.id})])

    # “delete row 3” / “remove rows 2 and 4”
    m = re.search(r"\b(delete|remove|drop)\s+rows?\s+([\d,\s]+(?:and\s+\d+)?)", low)
    if m and table is not None:
        numbers = [int(n) for n in re.findall(r"\d+", m.group(2))]
        ids = [table.rows[n - 1].id for n in numbers if 1 <= n <= len(table.rows)]
        if not ids:
            return Proposal(f"{table.title} has {len(table.rows)} rows — which one should I delete?")
        label = "row " + ", ".join(str(n) for n in numbers)
        return Proposal(f"I'll delete {label}.", [_op({"op": "delete_rows", "table_id": table.id, "row_ids": ids})])

    # “rename column Rate to Price”
    m = re.search(r"\brename\s+(?:the\s+)?(?:column\s+)?[\"'“]?(.+?)[\"'”]?\s+(?:column\s+)?to\s+[\"'“]?(.+?)[\"'”]?$", text, re.I)
    if m and table is not None:
        col = _column_by_name(table, m.group(1))
        if col is not None:
            new = _clean_value(m.group(2))
            return Proposal(f"I'll rename “{col.name}” to “{new}”.",
                            [_op({"op": "rename_column", "table_id": table.id, "column_id": col.id, "name": new})])

    # “split Qty Price into Qty and Price” / “you merged quantity and price, separate them”
    m = re.search(r"\b(?:split|separate)\s+(?:the\s+)?(?:column\s+)?[\"'“]?(.+?)[\"'”]?\s+(?:column\s+)?into\s+(.+)$", text, re.I)
    merged = re.search(r"\bmerged\s+(?:the\s+)?([\w ]+?)\s+(?:and|&|with)\s+([\w ]+?)(?:[.,!]|\s+(?:col|column)|$)", text, re.I)
    if table is not None and (m or (merged and re.search(r"\b(separate|split|unmerge|fix)\b", low))):
        if m:
            col = _column_by_name(table, m.group(1))
            names = [_clean_value(p) for p in re.split(r"\s*(?:,|\band\b|&|\|)\s*", m.group(2)) if _clean_value(p)]
        else:
            a, b = merged.group(1).strip(), merged.group(2).strip()
            col = _column_by_name(table, f"{a} {b}") or _column_by_name(table, a) or _column_by_name(table, b)
            names = [a.title(), b.title()]
        if col is None:
            return Proposal("Which column should I split? Tell me its name as shown in the table.")
        if len(names) < 2:
            return Proposal("What should the new columns be called? For example “into Qty and Price”.")
        return Proposal(f"I'll split “{col.name}” into {' and '.join(names)}.",
                        [_op({"op": "split_column", "table_id": table.id, "column_id": col.id, "new_columns": names})])

    # “merge columns A and B”
    m = re.search(r"\b(?:merge|combine|join)\s+(?:the\s+)?(?:columns?\s+)?[\"'“]?(.+?)[\"'”]?\s+(?:and|&|with)\s+[\"'“]?(.+?)[\"'”]?(?:\s+columns?)?$", text, re.I)
    if m and table is not None:
        a, b = _column_by_name(table, m.group(1)), _column_by_name(table, m.group(2))
        if a and b and a.id != b.id:
            return Proposal(f"I'll merge “{a.name}” and “{b.name}” into one column.",
                            [_op({"op": "merge_columns", "table_id": table.id, "column_ids": [a.id, b.id],
                                  "name": f"{a.name} {b.name}"})])

    # “split the table at row 5”
    m = re.search(r"\bsplit\s+(?:this|the)?\s*table\b(?:.*?\brow\s+(\d+))?", low)
    if m and table is not None:
        if not m.group(1):
            return Proposal("Where should I split it? Say something like “split the table at row 5”.")
        n = int(m.group(1))
        if not 2 <= n <= len(table.rows):
            return Proposal(f"Pick a row between 2 and {len(table.rows)}.")
        return Proposal(f"I'll start a new table at row {n}.",
                        [_op({"op": "split_table", "table_id": table.id, "before_row_id": table.rows[n - 1].id})])

    # “delete the column X”
    m = re.search(r"\b(?:delete|remove|drop)\s+(?:the\s+)?column\s+[\"'“]?(.+?)[\"'”]?$", text, re.I)
    if m and table is not None:
        col = _column_by_name(table, m.group(1))
        if col is not None:
            return Proposal(f"I'll delete the “{col.name}” column.",
                            [_op({"op": "delete_column", "table_id": table.id, "column_id": col.id})])

    # “add a row”
    if re.search(r"\badd\s+(?:a\s+|an\s+|one\s+)?(?:new\s+|empty\s+|blank\s+)?row\b", low) and table is not None:
        return Proposal("I'll add an empty row at the end.", [_op({"op": "add_row", "table_id": table.id})])

    # Field corrections
    patterns = [
        r"^(?:please\s+)?(?:change|set|update|make|correct|fix)\s+(?:the\s+)?(?P<field>.+?)\s+(?:to|as|=)\s+(?P<value>.+)$",
        r"^(?:the\s+)?(?P<field>.+?)\s+(?:is|was)\s+(?:wrong|incorrect|not right)[.,!;:]*\s*(?:it'?s|it is|it should be|should be|actually|=)\s+(?P<value>.+)$",
        r"^(?:the\s+)?(?P<field>.+?)\s+(?:should be|is actually|is)\s+(?P<value>.+)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        key = _field_for(m.group("field"), data)
        if key is None:
            continue
        value = _clean_value(m.group("value"))
        label = next(f.label for f in schema_for(data.doc_type) if f.key == key)
        return Proposal(f"I'll change {label.lower()} to “{value}”.",
                        [_op({"op": "set_field", "field": key, "value": value})])

    return Proposal(HELP)


def _op(raw: dict):
    return parse_operations([raw])[0]
