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
from decimal import Decimal, InvalidOperation

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

# Single words that only ever label one thing (unlike "invoice", "tax" or "from").
_UNAMBIGUOUS_LABELS = {"total", "subtotal", "date", "cgst", "sgst", "igst", "utgst", "vat", "gstin", "discount", "time"}
ROUNDING_STEP = Decimal("0.10")  # largest cash-rounding adjustment treated as "the same total"
_SEPARATORS = re.compile(r"^[\s:#\-–—=.|]+")
_NUMBER_WORDS = re.compile(r"^(?:no|nos|number|num|id|#)\b[\s.:#\-–]*", re.I)
_REFERENCE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/_.#]*\d[A-Za-z0-9\-/_.#]*|\d[A-Za-z0-9\-/_.#]*")

# Phrases that are document furniture rather than a business name.
_NOT_A_NAME = re.compile(
    r"\b(tax\s*invoice|invoice|receipt|bill\s+of\s+supply|original|duplicate|triplicate|copy|cash\s*bill|"
    r"estimate|quotation|statement|page\s+\d|gstin|pan\b|cin\b|phone|tel\b|fax\b|mobile|e-?mail|www\.|https?:|"
    r"date|bill\s+to|ship\s+to|billed\s+to|invoice\s+to|customer|buyer|address|cashier|counter|"
    r"(company|co|reg(istration)?|roc|gst(\s*reg)?|br|vat|tax)\s*(no|number|id)\b)|thank\s*you|welcome",
    re.I,
)
# Legal-entity suffixes are the strongest signal; OCR sometimes glues them on ("TAMANDAYA)SDNBHD").
_LEGAL_SUFFIX = re.compile(
    r"(sdn\.?\s*bhd|\bbhd\b|pvt\.?\s*ltd|\bp\.?\s*ltd|\bltd\b|\blimited\b|\bllp\b|\bllc\b|\binc\b\.?|"
    r"\bcorp(oration)?\b|\bgmbh\b|\bplc\b|\bpte\.?\s*ltd|\bco\.\s*\(?m\)?|\bs/b\b)",
    re.I,
)
_COMPANY_SUFFIX = re.compile(
    r"\b(pvt|private|enterprises?|technologies|technology|solutions|traders|trading|industries|services|"
    r"store|stores|mart|supermarket|hypermarket|restaurant|cafe|café|hotel|pharmacy|labs|studio|agency|"
    r"stationery|bakery|marketing|hardware|electrical|motor|optical|kitchen|food|foods)\b|\bs/b\b",
    re.I,
)
# Business addresses often sit right under the name; they aren't the name.
_ADDRESS_WORDS = re.compile(
    r"(jalan|jln)|\b(no\.?\s*\d|lot\s*[\dp]|mukim|kampung|road|rd\.|street|st\.|lane|avenue|floor|flr|level|block|"
    r"taman|tmn|batu|km\s*\d|nagar|sector|plot|suite|building|bldg)\b|\d{5,6}",
    re.I,
)
_OPENING_HOURS = re.compile(r"\b(shopping|opening|business|operating)\s*hours\b|\b\d{3,4}\s*hrs\b|\bmon|\bsun-", re.I)
# "(126926-H)", "(1393S6 X)", " 862725-U": company registration numbers after the name.
_TRAILING_REG = re.compile(r"\s*(?:[（(]\s*[0-9][0-9A-Z\-\s]{4,}[)）]|\s[0-9A-Z]{5,8}-[A-Z])\s*$")
# Words that are never a business name on their own.
_NOT_A_NAME_ALONE = re.compile(r"^\s*(tax|cash(\s*sales?)?|sales?|total|member|customer|counter|qty|item|"
                               r"description|amount|price|welcome|official|original)\s*$", re.I)
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


# Characters OCR commonly confuses in printed labels ("Totai", "T0TAL", "Tota1").
# Only used to *find labels*; values are never altered.
_OCR_CONFUSABLE = {"l": "[l1i|]", "i": "[i1l|]", "o": "[o0]"}


def _tolerant(word: str) -> str:
    return "".join(_OCR_CONFUSABLE.get(ch, re.escape(ch)) for ch in word.lower())


def _hint_pattern(hint: str) -> re.Pattern[str]:
    words = hint.split()
    body = r"[^A-Za-z0-9%]*".join(_tolerant(w) for w in words)
    # A label may be glued to its currency ("TOTALRM21.85") but not to another word ("TOTALLY").
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?!(?!(?:RM|Rs|INR|USD|MYR|SGD|EUR|GBP))[A-Za-z])", re.I)


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
            # "$" alone doesn't mean the US: GST is charged in day-first countries
            # (India, Malaysia, Singapore, Australia, NZ). Either way, the user is asked.
            gst = re.search(r"\bGST\b", raw.full_text, re.I) is not None
            self.dayfirst, self.date_order_known = (self.currency != "USD" or gst), False

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
        # Totals look at every total-like label (a rounded "TOTAL" often follows a more
        # specific "Total incl. GST"); other fields stop at the most specific label found.
        exhaustive = fdef.key == "total"
        for rank, hint in enumerate(fdef.hints):
            pattern = _hint_pattern(hint)
            specificity = 1.0 if len(hint.split()) > 1 or hint in _UNAMBIGUOUS_LABELS else 0.88
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
            if candidates and not exhaustive:
                break  # the most specific hint that produced a value wins
        if not candidates:
            return None
        if fdef.key == "total":
            # 1. The most explicit kind of label present wins ("Total Payable" over "Total incl. GST"
            #    over a bare "Total"): a bill with returns or credits has several totals.
            # A few cents is a rounding adjustment or a tax line, not a total, unless it's all there is.
            if len(candidates) > 1:
                candidates = [c for c in candidates if _decimal(c.value) > ROUNDING_STEP] or candidates
            tier = min(_total_tier(fdef.hints[c.hint_rank]) for c in candidates)
            pool = [c for c in candidates if _total_tier(fdef.hints[c.hint_rank]) == tier]
            # 2. Within that kind, subtotals, tax totals and GST summaries are smaller than the
            #    amount payable, so the largest amount is the total.
            top = max(_decimal(c.value) for c in pool)
            best = max((c for c in pool if _decimal(c.value) == top), key=lambda c: c.order)
            # 3. A total printed later that differs only by cash rounding (65.72 → 65.70) is what
            #    was actually paid, whatever its label.
            later = [c for c in candidates if c.order > best.order and c.value != best.value
                     and abs(_decimal(c.value) - top) <= ROUNDING_STEP
                     and _is_cash_rounded(_decimal(c.value)) and not _is_cash_rounded(top)]
            chosen = max(later, key=lambda c: c.order) if later else best
            chosen = self._rounded_total(chosen) or chosen
            if _decimal(chosen.value) <= ROUNDING_STEP:
                chosen.confidence = min(chosen.confidence, 0.4)  # a few cents: almost certainly mis-read
            # The amount payable is usually printed more than once (total, cash/card line, GST summary).
            repeats = sum(1 for ln in self.lines if any(a.value == _decimal(chosen.value) for a in find_amounts(ln.text)))
            if repeats >= 2:
                chosen.confidence = min(0.97, chosen.confidence + 0.1)
            return chosen
        # Most other labels' first occurrence is the right one.
        return min(candidates, key=lambda c: c.order)

    def _rounded_total(self, total: Candidate) -> Candidate | None:
        """A line like "Rounding 20.00" printed after "TOTAL 19.99" carries the rounded total."""
        value = _decimal(total.value)
        if _is_cash_rounded(value):
            return None
        for line in self.lines[total.order + 1 : total.order + 8]:
            if not re.search(r"(?<![A-Za-z])" + _tolerant("round"), line.text, re.I):
                continue
            row = layout.row_of(line, self.lines)
            for other in reversed(row):
                for a in reversed(find_amounts(other.text)):
                    if (a.value != value and ROUNDING_STEP < a.value and abs(a.value - value) <= ROUNDING_STEP
                            and _is_cash_rounded(a.value)):
                        return Candidate(format_amount(a.value), a.raw, total.confidence, [line, other], total.hint_rank,
                                         self.order[line.id])
        return None

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
            dates = find_dates(text, dayfirst=self.dayfirst, allow_compact=True)
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
        found = [(line, d) for line in self.lines if line.page == 0 for d in find_dates(line.text, dayfirst=self.dayfirst)]
        if not found:
            return None
        line, d = found[0]
        distinct = {x.value for _, x in found}
        notes = []
        if len(distinct) == 1:
            # Only one date anywhere on the page: that's the document's date.
            conf = 0.88 * self._conf([line])
        else:
            conf = 0.55 * self._conf([line])
            notes.append("No “date” label was found next to this date.")
        if d.ambiguous and not self.date_order_known:
            conf = min(conf, 0.6)
            notes.append(_ambiguity_note(d.raw, d.value, self.dayfirst))
        return Candidate(d.value.isoformat(), d.raw, conf, [line], 99, 0, notes)

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
            core = _TRAILING_REG.sub("", text)
            letters = sum(ch.isalpha() for ch in core)
            if letters < 0.6 * len(core.replace(" ", "")) or _OPENING_HOURS.search(text):
                continue
            if letters < 4 or _NOT_A_NAME_ALONE.match(core) or re.match(r"\s*cash\s*sales?\b", core, re.I):
                continue
            # A street address is never the business name; "Not detected" is better.
            if _ADDRESS_WORDS.search(core) and re.search(r"\d", core) and not _LEGAL_SUFFIX.search(core):
                continue
            score = 0.45
            if _LEGAL_SUFFIX.search(text):
                score += 0.35
            elif _COMPANY_SUFFIX.search(text):
                score += 0.2
            if _ADDRESS_WORDS.search(text):
                score -= 0.25
            if text == text.lower():
                score -= 0.2  # business names are printed in caps or title case; this is usually handwriting
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
        above = self._wrapped_name_line(ln)
        if above is not None:
            pieces = [above, *pieces]
        else:
            below = self._name_continues_below(ln)
            if below is not None:
                pieces = [*pieces, below]
        text = _TRAILING_REG.sub("", " ".join(p.text.strip() for p in pieces)).strip()
        confidence = min(0.9, score) * min(p.confidence for p in pieces)
        notes = [] if score >= 0.75 else ["Picked from the top of the page — please check."]
        return FieldValue(value=text, raw=text, confidence=round(confidence, 3),
                          source=_source(pieces), origin="ocr", notes=notes)

    def _same_row_pieces(self, line: TextLine) -> list[TextLine]:
        """A name the engine split into adjacent boxes ("THE" | "DAILY GRIND CAFE")."""
        row = layout.row_of(line, self.lines)
        i = row.index(line)
        h = layout.height(line)
        gap = 1.2 * h

        def joins(other: TextLine) -> bool:
            # Same print size; stamps and handwriting next to the name are usually not.
            return _wordy(other.text) and 0.7 <= layout.height(other) / h <= 1.4

        left, right = i, i
        while left > 0 and row[left].bbox[0] - row[left - 1].bbox[2] < gap and joins(row[left - 1]):
            left -= 1
        while right < len(row) - 1 and row[right + 1].bbox[0] - row[right].bbox[2] < gap and joins(row[right + 1]):
            right += 1
        return row[left : right + 1]

    def _wrapped_name_line(self, line: TextLine) -> TextLine | None:
        """The first half of a long name that wrapped onto two lines:
        "LIAN CHI PU TIAN VEGETARIAN" / "RESTAURANT SDN BHD"."""
        h = layout.height(line)
        above = [
            o for o in self.lines
            if o.page == line.page and o is not line and 0 <= line.bbox[1] - o.bbox[3] <= 0.6 * h
            and layout.x_overlap(o, line) > 0.5 * min(o.bbox[2] - o.bbox[0], line.bbox[2] - line.bbox[0])
        ]
        if len(above) != 1:
            return None
        o = above[0]
        text = _TRAILING_REG.sub("", line.text)
        suffix = _LEGAL_SUFFIX.search(text)
        starts_generic = re.match(r"\s*(restaurant|sdn|bhd|pvt|private|ltd|limited|enterprise|trading|"
                                  r"marketing|co\.?|company|&|and)\b", text, re.I)
        # "STATIONERY SDN BHD": only one or two words before the legal suffix means the
        # rest of the name is on the line above.
        short_before_suffix = suffix is not None and len(text[: suffix.start()].split()) <= 2
        if ((starts_generic or short_before_suffix) and _wordy(o.text) and not _ADDRESS_WORDS.search(o.text)
                and not _LEGAL_SUFFIX.search(o.text) and 0.7 <= layout.height(o) / h <= 1.4
                and o.text.upper() == o.text):
            return o
        return None

    def _name_continues_below(self, line: TextLine) -> TextLine | None:
        """ "EIGHT OUNCE" / "COFFEE CO.", "TEO HENG STATIONERY" / "& BOOKS"."""
        if _LEGAL_SUFFIX.search(line.text):
            return None
        h = layout.height(line)
        below = [
            o for o in self.lines
            if o.page == line.page and o is not line and 0 <= o.bbox[1] - line.bbox[3] <= 0.6 * h
            and layout.x_overlap(o, line) > 0.3 * min(o.bbox[2] - o.bbox[0], line.bbox[2] - line.bbox[0])
        ]
        if len(below) != 1:
            return None
        o = below[0]
        text = _TRAILING_REG.sub("", o.text)
        continues = re.match(r"\s*(&|and)\b", text, re.I) or (
            (_LEGAL_SUFFIX.search(text) or _COMPANY_SUFFIX.search(text)) and len(text.split()) <= 3
        )
        if (continues and _wordy(text) and not _ADDRESS_WORDS.search(text) and 0.7 <= layout.height(o) / h <= 1.4
                and o.text.upper() == o.text):
            return o
        return None

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
                # A time printed next to the date is the time of purchase.
                beside_date = bool(find_dates(line.text, dayfirst=self.dayfirst)) or re.search(r"\btime\b", line.text, re.I)
                base = 0.92 if beside_date else 0.8
                return FieldValue(value=value, raw=raw, confidence=round(base * line.confidence, 3),
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


# "Net amount" is not here: on GST summaries it means the amount before tax.
_PAYABLE_LABELS = ("grand total", "total payable", "net payable", "amount payable", "amount due", "total due",
                   "balance due", "nett total", "net total", "rounded total", "total amount", "total amt",
                   "invoice total")
_INCLUSIVE_LABELS = ("total incl", "total inclusive", "total sales", "total inr")


def _total_tier(hint: str) -> int:
    if hint in _PAYABLE_LABELS:
        return 0
    if hint in _INCLUSIVE_LABELS:
        return 1
    return 2


def _is_cash_rounded(value: Decimal) -> bool:
    """Cash totals are rounded to the smallest coin: 0.05 (MYR, SGD...), 0.10 or a whole unit."""
    return value % Decimal("0.05") == 0


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal(0)


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
    ) or (code == "MYR" and re.search(r"\bRM\b", text) is not None)


def _ambiguity_note(raw: str, value: date, dayfirst: bool) -> str:
    other = None
    try:
        other = date(value.year, value.day, value.month)
    except ValueError:
        pass
    if other is None:
        return ""
    val_str = f"{value.day} {value.strftime('%B %Y')}"
    other_str = f"{other.day} {other.strftime('%B %Y')}"
    return f"“{raw}” could mean {val_str} or {other_str}."
