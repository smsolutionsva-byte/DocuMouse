"""Rule-based field extraction over the document engine's text + coordinates.

This is the deterministic baseline. It works without any LLM and every value
it returns points at the exact text line it came from. When it is unsure, it
says so through a lower confidence or a note; it never fills in a value that
is not printed on the page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..document_data import FieldValue, Source
from ..processing.types import RawDocument, TextLine
from . import layout
from .parsing import (
    DAYFIRST_CURRENCIES,
    detect_currency,
    find_amounts,
    find_dates,
    find_gstins,
    find_time,
    format_amount,
    looks_like_money,
    numeric_date_order,
)
from .schema import FieldDef, schema_for

_SEPARATORS = re.compile(r"^[\s:#\-–—=.|]+")
_NUMBER_WORDS = re.compile(r"^(?:no|nos|number|num|id|#)\b[\s.:#\-–]*", re.I)
_REFERENCE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/_.#]*\d[A-Za-z0-9\-/_.#]*|\d[A-Za-z0-9\-/_.#]*")

# Phrases that are document furniture rather than a business name.
_NOT_A_NAME = re.compile(
    r"\b(tax\s+invoice|invoice|receipt|bill\s+of\s+supply|original|duplicate|triplicate|copy|"
    r"estimate|quotation|statement|page\s+\d|gstin|pan\b|cin\b|phone|tel\b|mobile|e-?mail|www\.|https?:|"
    r"date|bill\s+to|ship\s+to|billed\s+to|invoice\s+to|customer|buyer|address)\b",
    re.I,
)
_COMPANY_SUFFIX = re.compile(
    r"\b(pvt|private|ltd|limited|llp|llc|inc|corp|corporation|co\.|company|gmbh|s\.?a\.?|plc|"
    r"technologies|technology|solutions|enterprises?|traders|trading|industries|services|"
    r"store|stores|mart|supermarket|restaurant|cafe|café|hotel|pharmacy|labs|studio|agency)\b",
    re.I,
)
_PAYMENT_METHODS = [
    (re.compile(r"\bupi\b|\bgpay\b|google\s*pay|phonepe|paytm", re.I), "UPI"),
    (re.compile(r"\bvisa\b", re.I), "Card (Visa)"),
    (re.compile(r"master\s*card", re.I), "Card (Mastercard)"),
    (re.compile(r"\bamex\b|american\s+express", re.I), "Card (Amex)"),
    (re.compile(r"\brupay\b", re.I), "Card (RuPay)"),
    (re.compile(r"\b(credit|debit)\s+card\b", re.I), "Card"),
    (re.compile(r"\bcard\b", re.I), "Card"),
    (re.compile(r"\bcash\b", re.I), "Cash"),
]


@dataclass
class Candidate:
    value: str
    raw: str
    confidence: float
    lines: list[TextLine]
    hint_rank: int
    order: int
    notes: list[str] = field(default_factory=list)


def _hint_pattern(hint: str) -> re.Pattern[str]:
    words = hint.split()
    body = r"[^A-Za-z0-9%]*".join(re.escape(w) for w in words)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I)


def _excluded(text: str, start: int, end: int, excludes: tuple[str, ...]) -> bool:
    window = text[max(0, start - 14) : end + 14]
    return any(_hint_pattern(ex).search(window) for ex in excludes)


class RuleExtractor:
    def __init__(self, raw: RawDocument):
        self.raw = raw
        self.lines = raw.lines
        self.order = {line.id: i for i, line in enumerate(self.lines)}
        self.currency, self.currency_conf, _ = detect_currency(raw.full_text)
        # Is 04/05/2026 the 4th of May or April 5th? Settle it from the page itself when a
        # date like 25/09/2026 is printed, otherwise from the currency's local convention.
        # Only when neither works is the user asked.
        order = numeric_date_order(raw.full_text)
        if order:
            self.dayfirst, self.date_order_known = order == "dayfirst", True
        elif self.currency in DAYFIRST_CURRENCIES and self.currency_conf >= 0.85:
            self.dayfirst, self.date_order_known = True, True
        else:
            self.dayfirst, self.date_order_known = self.currency != "USD", False

    # ------------------------------------------------------------ public

    def extract(self, doc_type: str) -> dict[str, FieldValue]:
        fields: dict[str, FieldValue] = {}
        for fdef in schema_for(doc_type):
            fields[fdef.key] = self._extract_field(doc_type, fdef)
        return fields

    # ------------------------------------------------------------ dispatch

    def _extract_field(self, doc_type: str, fdef: FieldDef) -> FieldValue:
        if fdef.kind == "currency":
            return self._currency()
        if fdef.kind == "gstin":
            return self._gstin()
        if fdef.key in ("vendor", "merchant"):
            return self._party(fdef)
        if fdef.key == "payment_method":
            return self._payment_method(fdef)
        if fdef.key == "billing_address":
            return self._address_block(fdef)
        if fdef.kind == "time":
            return self._time(fdef)
        candidate = self._best_labelled(fdef)
        if candidate is None and fdef.kind == "date" and fdef.key in ("invoice_date", "date"):
            candidate = self._first_date_near_top()
        return self._to_field(candidate)

    # ------------------------------------------------------------ labelled values

    def _best_labelled(self, fdef: FieldDef) -> Candidate | None:
        candidates: list[Candidate] = []
        for rank, hint in enumerate(fdef.hints):
            pattern = _hint_pattern(hint)
            specificity = 1.0 if len(hint.split()) > 1 else 0.88
            for line in self.lines:
                for m in pattern.finditer(line.text):
                    if _excluded(line.text, m.start(), m.end(), fdef.exclude):
                        continue
                    cand = self._value_for_label(fdef, line, m.end())
                    if cand is None:
                        continue
                    cand.confidence *= specificity
                    cand.hint_rank = rank
                    cand.order = self.order[line.id]
                    candidates.append(cand)
            if candidates:
                break  # the most specific hint that produced a value wins
        if not candidates:
            return None
        # Totals sit at the bottom; most other labels' first occurrence is the right one.
        if fdef.key == "total":
            return max(candidates, key=lambda c: c.order)
        return min(candidates, key=lambda c: c.order)

    def _value_for_label(self, fdef: FieldDef, line: TextLine, label_end: int) -> Candidate | None:
        rest = _SEPARATORS.sub("", line.text[label_end:])
        if fdef.kind == "amount":
            # Money on the label's own line first, then the right-most money on its row
            # (value columns are right-aligned), and only then a bare number on the line.
            cand = self._parse_value(fdef, rest, [line], 0.95, money_only=True)
            if cand:
                return cand
            row = self._row_amount(line)
            if row:
                return row
            cand = self._parse_value(fdef, rest, [line], 0.95)
            if cand:
                return cand
        else:
            cand = self._parse_value(fdef, rest, [line], 0.95)
            if cand:
                return cand
            for neighbour in layout.right_neighbours(line, self.lines)[:3]:
                cand = self._parse_value(fdef, _SEPARATORS.sub("", neighbour.text), [line, neighbour], 0.9)
                if cand:
                    return cand
        for below in layout.lines_below(line, self.lines)[:2]:
            cand = self._parse_value(fdef, below.text, [line, below], 0.75)
            if cand:
                return cand
        return None

    def _row_amount(self, label_line: TextLine) -> Candidate | None:
        row = [o for o in layout.right_neighbours(label_line, self.lines)]
        for line in reversed(row):
            amounts = [a for a in find_amounts(line.text) if looks_like_money(a)]
            if amounts:
                a = amounts[-1]
                return Candidate(format_amount(a.value), a.raw, 0.9 * self._conf([label_line, line]),
                                 [label_line, line], 0, 0)
        return None

    def _parse_value(
        self, fdef: FieldDef, text: str, lines: list[TextLine], placement: float, *, money_only: bool = False
    ) -> Candidate | None:
        text = text.strip()
        if not text:
            return None
        conf = placement * self._conf(lines)
        if fdef.kind == "amount":
            amounts = find_amounts(text)
            money = [a for a in amounts if looks_like_money(a)]
            if money:
                a = money[-1]
            elif len(amounts) == 1 and not money_only:
                a = amounts[0]
                conf *= 0.85
            else:
                return None
            return Candidate(format_amount(a.value), a.raw, conf, lines, 0, 0)
        if fdef.kind == "date":
            dates = find_dates(text, dayfirst=self.dayfirst)
            if not dates:
                return None
            d = dates[0]
            notes = []
            if d.ambiguous and not self.date_order_known:
                conf = min(conf, 0.6)
                notes.append(_ambiguity_note(d.raw, d.value, self.dayfirst))
            return Candidate(d.value.isoformat(), d.raw, conf, lines, 0, 0, notes)
        if fdef.key in ("invoice_number",):
            text = _NUMBER_WORDS.sub("", text)
            m = _REFERENCE_TOKEN.match(text)
            if not m:
                return None
            token = m.group(0).rstrip(".,:;")
            return Candidate(token, token, conf, lines, 0, 0)
        # free text
        value = re.split(r"\s{3,}", text)[0].strip(" :-")
        if len(value) < 2:
            return None
        return Candidate(value, value, conf * 0.9, lines, 0, 0)

    def _first_date_near_top(self) -> Candidate | None:
        for line in self.lines:
            if line.page != 0 or line.bbox[1] > 0.45:
                continue
            dates = find_dates(line.text, dayfirst=self.dayfirst)
            if dates:
                d = dates[0]
                notes = ["No “date” label was found next to this date."]
                if d.ambiguous and not self.date_order_known:
                    notes.append(_ambiguity_note(d.raw, d.value, self.dayfirst))
                return Candidate(d.value.isoformat(), d.raw, 0.55 * self._conf([line]), [line], 99, 0, notes)
        return None

    # ------------------------------------------------------------ special fields

    def _currency(self) -> FieldValue:
        if not self.currency:
            return FieldValue()
        evidence = next((ln for ln in self.lines if self.currency in ln.text or _symbol_in(ln.text, self.currency)), None)
        return FieldValue(
            value=self.currency,
            raw=self.currency,
            confidence=self.currency_conf,
            source=_source([evidence]) if evidence else None,
            origin="ocr",
            notes=[] if self.currency_conf >= 0.85 else ["Currency was inferred from the document, not printed as a code."],
        )

    def _gstin(self) -> FieldValue:
        billing = set(self._billing_line_ids())
        for line in self.lines:
            for gstin in find_gstins(line.text):
                if line.id in billing:
                    continue
                return FieldValue(value=gstin, raw=gstin, confidence=0.9 * line.confidence,
                                  source=_source([line]), origin="ocr")
        return FieldValue()

    def _party(self, fdef: FieldDef) -> FieldValue:
        labelled = self._best_labelled(fdef) if fdef.hints else None
        if labelled and not _NOT_A_NAME.search(labelled.value):
            return self._to_field(labelled)
        billing = set(self._billing_line_ids())
        top = [
            ln for ln in self.lines
            if ln.page == 0 and ln.bbox[1] < 0.35 and ln.id not in billing and re.search(r"[A-Za-z]{2}", ln.text)
        ]
        best: tuple[float, TextLine] | None = None
        tallest = max((layout.height(ln) for ln in top), default=1.0)
        for i, ln in enumerate(top[:14]):
            text = ln.text.strip()
            if _NOT_A_NAME.search(text) or find_dates(text) or len(text) > 60:
                continue
            letters = sum(ch.isalpha() for ch in text)
            if letters < 0.6 * len(text.replace(" ", "")):
                continue
            score = 0.45
            if _COMPANY_SUFFIX.search(text):
                score += 0.3
            score += 0.15 * (layout.height(ln) / tallest)  # big print is usually the business name
            score -= 0.02 * i
            if self._in_title_block(ln):
                score += 0.05
            if best is None or score > best[0]:
                best = (score, ln)
        if best is None:
            return FieldValue()
        score, ln = best
        pieces = self._same_row_pieces(ln)
        text = " ".join(p.text.strip() for p in pieces)
        confidence = min(0.9, score) * min(p.confidence for p in pieces)
        notes = [] if score >= 0.75 else ["Picked from the top of the page — please check."]
        return FieldValue(value=text, raw=text, confidence=round(confidence, 3),
                          source=_source(pieces), origin="ocr", notes=notes)

    def _same_row_pieces(self, line: TextLine) -> list[TextLine]:
        """A name the engine split into adjacent boxes ("THE" | "DAILY GRIND CAFE")."""
        row = layout.row_of(line, self.lines)
        i = row.index(line)
        gap = 1.2 * layout.height(line)
        left, right = i, i
        while left > 0 and row[left].bbox[0] - row[left - 1].bbox[2] < gap and _wordy(row[left - 1].text):
            left -= 1
        while right < len(row) - 1 and row[right + 1].bbox[0] - row[right].bbox[2] < gap and _wordy(row[right + 1].text):
            right += 1
        return row[left : right + 1]

    def _in_title_block(self, line: TextLine) -> bool:
        for block in self.raw.blocks:
            if block.label in ("doc_title", "paragraph_title", "header") and block.page == line.page:
                if layout.inside(line, block.bbox, block.page):
                    return True
        return False

    def _billing_line_ids(self) -> list[str]:
        for line in self.lines:
            m = re.search(r"\b(bill(ed)?\s+to|invoice\s+to|buyer|sold\s+to|customer)\b", line.text, re.I)
            if not m:
                continue
            ids = [line.id]
            ids += [ln.id for ln in layout.lines_below(line, self.lines, max_gap_lines=8)[:6]]
            return ids
        return []

    def _address_block(self, fdef: FieldDef) -> FieldValue:
        for hint in fdef.hints:
            pattern = _hint_pattern(hint)
            for line in self.lines:
                m = pattern.search(line.text)
                if not m:
                    continue
                collected: list[TextLine] = []
                rest = _SEPARATORS.sub("", line.text[m.end():]).strip()
                parts = [rest] if rest else []
                if rest:
                    collected.append(line)
                previous = line
                capped = False
                for below in layout.lines_below(line, self.lines, max_gap_lines=8):
                    if below.bbox[1] - previous.bbox[3] > 1.6 * layout.height(previous):
                        break
                    if re.search(r"\b(ship\s+to|invoice\s+(no|date)|date|gstin|phone|e-?mail|place\s+of\s+supply)\b", below.text, re.I) and parts:
                        break
                    parts.append(below.text.strip())
                    collected.append(below)
                    previous = below
                    if len(parts) >= 5:
                        capped = True
                        break
                if parts:
                    lines = collected or [line]
                    notes = ["This address block is long — check where it ends."] if capped else []
                    return FieldValue(value="\n".join(parts), raw="\n".join(parts),
                                      confidence=round(0.88 * self._conf(lines), 3),
                                      source=_source(lines), origin="ocr", notes=notes)
        return FieldValue()

    def _payment_method(self, fdef: FieldDef) -> FieldValue:
        for line in reversed(self.lines):
            for pattern, label in _PAYMENT_METHODS:
                if pattern.search(line.text):
                    return FieldValue(value=label, raw=line.text.strip(), confidence=round(0.88 * line.confidence, 3),
                                      source=_source([line]), origin="ocr")
        return FieldValue()

    def _time(self, fdef: FieldDef) -> FieldValue:
        for line in self.lines:
            found = find_time(line.text)
            if found:
                value, raw = found
                return FieldValue(value=value, raw=raw, confidence=round(0.85 * line.confidence, 3),
                                  source=_source([line]), origin="ocr")
        return FieldValue()

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _conf(lines: list[TextLine]) -> float:
        return min((ln.confidence for ln in lines), default=0.0)

    def _to_field(self, cand: Candidate | None) -> FieldValue:
        if cand is None:
            return FieldValue()
        # Point at the value's line (the last one), not the label.
        return FieldValue(
            value=cand.value,
            raw=cand.raw,
            confidence=round(cand.confidence, 3),
            source=_source([cand.lines[-1]]),
            origin="ocr",
            notes=cand.notes,
        )


def _wordy(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2}", text)) and not _NOT_A_NAME.search(text) and not find_dates(text)


def _source(lines: list[TextLine | None]) -> Source | None:
    real = [ln for ln in lines if ln is not None]
    if not real:
        return None
    page = real[0].page
    same_page = [ln for ln in real if ln.page == page]
    return Source(page=page, bbox=layout.union_bbox(same_page))


def _symbol_in(text: str, code: str) -> bool:
    from .parsing import CURRENCY_SYMBOLS

    return any(sym in text for sym, c in CURRENCY_SYMBOLS.items() if c == code) or (
        code == "INR" and re.search(r"\bRs\.?", text) is not None
    )


def _ambiguity_note(raw: str, value: date, dayfirst: bool) -> str:
    other = None
    try:
        other = date(value.year, value.day, value.month)
    except ValueError:
        pass
    if other is None:
        return ""
    fmt = "%-d %B %Y"
    return f"“{raw}” could mean {value.strftime(fmt)} or {other.strftime(fmt)}."
