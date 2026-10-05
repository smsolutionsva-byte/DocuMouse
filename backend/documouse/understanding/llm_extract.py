"""Optional LLM pass that maps engine output to fields, then gets fact-checked.

The LLM sees the text lines PaddleOCR produced (with ids) and must cite the
line ids each value came from. Every value is then checked against those lines
deterministically. A value that can't be found in the document is never used as
a field value; at most it becomes a visible suggestion.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..llm.base import LLMError, LLMProvider
from ..processing.types import RawDocument, TextLine
from .parsing import find_amounts, find_dates, normalise_label, parse_amount
from .schema import DOC_TYPE_LABELS, FieldDef, schema_for
from .values import canonicalize

log = logging.getLogger(__name__)

MAX_LINES = 400

SYSTEM_PROMPT = """You read OCR output of business documents and return JSON only.
Rules:
- Use only text that appears in the OCR lines. Never calculate, guess or infer a value.
- For every field return {"value": <string or null>, "lines": [<ids of the lines it came from>]}.
- If a field is not clearly present, return null for value.
- Amounts: copy the number as printed (e.g. "23,600.00"). Dates: copy as printed.
- vendor/merchant is the business that issued the document, not the customer."""


@dataclass
class LLMField:
    key: str
    value: str | None  # canonical value, only when grounded
    proposed: str | None  # what the model said, canonicalised if possible
    grounded: bool
    lines: list[TextLine]


def _describe_fields(fields: tuple[FieldDef, ...]) -> str:
    kinds = {
        "amount": "number as printed",
        "date": "date as printed",
        "currency": "ISO 4217 code, e.g. INR",
        "gstin": "15-character GSTIN",
        "multiline": "text, may span lines",
        "time": "time as printed",
        "text": "text",
    }
    return "\n".join(f'- "{f.key}": {f.label} ({kinds[f.kind]})' for f in fields)


def _ocr_listing(raw: RawDocument) -> str:
    rows = [f"[{ln.id}] {ln.text}" for ln in raw.lines[:MAX_LINES]]
    return "\n".join(rows)


def llm_extract(raw: RawDocument, doc_type: str, llm: LLMProvider, *, dayfirst: bool) -> dict[str, LLMField]:
    fields = schema_for(doc_type)
    if not fields:
        return {}
    user = (
        f"Document type: {DOC_TYPE_LABELS.get(doc_type, doc_type)}\n\n"
        f"Fields to extract:\n{_describe_fields(fields)}\n\n"
        f"OCR lines (id, text), in reading order:\n{_ocr_listing(raw)}\n\n"
        'Respond as {"fields": {"<field key>": {"value": ..., "lines": [...]}, ...}}'
    )
    try:
        response = llm.complete_json(SYSTEM_PROMPT, user)
    except LLMError:
        log.warning("LLM extraction failed; continuing with rule-based results", exc_info=True)
        return {}
    payload = response.get("fields") if isinstance(response.get("fields"), dict) else response
    by_id = {ln.id: ln for ln in raw.lines}
    out: dict[str, LLMField] = {}
    for fdef in fields:
        item = payload.get(fdef.key)
        if isinstance(item, dict):
            value, cited = item.get("value"), item.get("lines") or []
        else:
            value, cited = item, []
        if value in (None, "", []) or not isinstance(value, (str, int, float)):
            continue
        value = str(value).strip()
        cited_lines = [by_id[i] for i in cited if isinstance(i, str) and i in by_id]
        out[fdef.key] = ground(fdef, value, cited_lines, raw, dayfirst=dayfirst)
    return out


def ground(fdef: FieldDef, value: str, cited: list[TextLine], raw: RawDocument, *, dayfirst: bool) -> LLMField:
    """Check the model's value against the document text."""
    canonical = canonicalize(fdef.kind, value, dayfirst=dayfirst)
    if fdef.kind == "multiline":
        pieces = [p.strip(" ,") for p in re.split(r"[\n,]+", value) if len(p.strip(" ,")) >= 2]
        pool = cited or raw.lines
        evidence = []
        for piece in pieces:
            hit = next((ln for ln in pool if _supports("text", piece, piece, ln.text, dayfirst)), None)
            if hit and hit not in evidence:
                evidence.append(hit)
        found = sum(1 for piece in pieces if any(_supports("text", piece, piece, ln.text, dayfirst) for ln in evidence))
        grounded = bool(pieces) and found >= 0.7 * len(pieces)
        return LLMField(fdef.key, canonical if grounded else None, canonical, grounded, evidence)
    evidence = [ln for ln in cited if _supports(fdef.kind, value, canonical, ln.text, dayfirst)]
    if not evidence:
        # The model may have cited the wrong line; look for the value anywhere.
        evidence = [ln for ln in raw.lines if _supports(fdef.kind, value, canonical, ln.text, dayfirst)][:1]
    grounded = bool(evidence) and canonical is not None
    return LLMField(
        key=fdef.key,
        value=canonical if grounded else None,
        proposed=canonical or value,
        grounded=grounded,
        lines=evidence,
    )


def _supports(kind: str, value: str, canonical: str | None, text: str, dayfirst: bool) -> bool:
    if kind == "amount":
        target = parse_amount(value)
        return target is not None and any(abs(a.value) == abs(target) for a in find_amounts(text))
    if kind == "date":
        if canonical is None:
            return False
        for d in find_dates(text, dayfirst=dayfirst):
            alternatives = {d.value.isoformat()}
            if d.ambiguous:
                alternatives.add(d.value.replace(month=d.value.day, day=d.value.month).isoformat())
            if canonical in alternatives:
                return True
        return False
    if kind == "currency":
        return bool(canonical) and (canonical in text.upper() or _currency_symbol_present(canonical, text))
    if kind == "gstin":
        return re.sub(r"\s+", "", value).upper() in re.sub(r"\s+", "", text).upper()
    a, b = normalise_label(value), normalise_label(text)
    if not a:
        return False
    if a in b:
        return True
    # Multi-line values (addresses) are checked line by line elsewhere; allow light OCR noise here.
    return len(a) >= 4 and SequenceMatcher(None, a, b).ratio() >= 0.88


def _currency_symbol_present(code: str, text: str) -> bool:
    from .parsing import CURRENCY_SYMBOLS

    return any(sym in text for sym, c in CURRENCY_SYMBOLS.items() if c == code) or (
        code == "INR" and re.search(r"\bRs\.?", text) is not None
    )


def debug_dump(fields: dict[str, LLMField]) -> str:  # pragma: no cover - debugging helper
    return json.dumps({k: {"value": v.value, "proposed": v.proposed, "grounded": v.grounded} for k, v in fields.items()})
