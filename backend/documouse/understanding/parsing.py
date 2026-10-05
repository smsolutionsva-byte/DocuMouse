"""Deterministic parsers for the values that matter on financial documents.

These never guess. A parser either returns a value it is sure about, or None,
or flags the value as ambiguous so the review screen can ask the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ---------------------------------------------------------------- amounts

CURRENCY_SYMBOLS = {
    "₹": "INR",
    "€": "EUR",
    "£": "GBP",
    "$": "USD",
    "¥": "JPY",
    "₩": "KRW",
    "₽": "RUB",
    "₺": "TRY",
    "₫": "VND",
    "₱": "PHP",
    "฿": "THB",
}
CURRENCY_CODES = {
    "INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD", "JPY", "CNY", "CHF", "NZD",
    "HKD", "SAR", "ZAR", "MYR", "IDR", "THB", "PHP", "KRW", "BRL", "MXN", "SEK", "NOK",
    "DKK", "PLN", "TRY", "RUB", "VND", "BDT", "LKR", "NPR", "PKR", "KES", "NGN", "EGP",
}
CURRENCY_DISPLAY = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}

_AMOUNT_RE = re.compile(
    r"(?<![\w.,])"
    r"(?P<neg>[-−(])?\s*"
    r"(?P<cur>₹|€|£|\$|¥|Rs\.?|INR|USD|EUR|GBP)?\s*"
    r"(?P<num>\d{1,3}(?:[,.\s]\d{2,3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"(?![\w%])",
    re.IGNORECASE,
)


def parse_amount(text: str | None) -> Decimal | None:
    """Parse one amount like ``₹23,600.00``, ``1,23,456.78``, ``12,50`` or ``(100)``."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    negative = s.startswith(("-", "−", "(")) or s.endswith(("-", ")"))
    s = re.sub(r"(?i)\b(rs|inr|usd|eur|gbp|aed|sgd|aud|cad)\b\.?", "", s)
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    s = _normalise_separators(s)
    if s is None:
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def _normalise_separators(s: str) -> str | None:
    s = s.strip(".,")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56 or 1,23,456.78
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):  # 12,50
            s = parts[0] + "." + parts[1]
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        parts = s.split(".")
        if all(len(p) == 3 for p in parts[1:]):  # 1.234.567
            s = "".join(parts)
        elif len(parts[-1]) in (1, 2) and all(len(p) == 3 for p in parts[1:-1]):
            s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            return None
    return s


@dataclass
class AmountMatch:
    value: Decimal
    raw: str
    currency: str | None
    start: int
    end: int


def find_amounts(text: str) -> list[AmountMatch]:
    out: list[AmountMatch] = []
    for m in _AMOUNT_RE.finditer(text):
        num = m.group("num")
        value = parse_amount(num)
        if value is None:
            continue
        if m.group("neg") in ("-", "−", "("):
            value = -value
        cur = m.group("cur")
        out.append(
            AmountMatch(
                value=value,
                raw=m.group(0).strip(),
                currency=currency_from_token(cur) if cur else None,
                start=m.start(),
                end=m.end(),
            )
        )
    return out


def looks_like_money(match: AmountMatch) -> bool:
    """Bare integers like '2' or '2026' are rarely the amount on a label line."""
    return match.currency is not None or "." in match.raw or "," in match.raw


def format_amount(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def currency_from_token(token: str) -> str | None:
    t = token.strip().rstrip(".").upper()
    if token.strip() in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[token.strip()]
    if t == "RS":
        return "INR"
    if t in CURRENCY_CODES:
        return t
    return None


def detect_currency(text: str) -> tuple[str | None, float, str | None]:
    """Return ``(code, confidence, evidence)`` from the whole document text."""
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            return code, 0.95, code
    counts: dict[str, int] = {}
    for symbol, code in CURRENCY_SYMBOLS.items():
        n = text.count(symbol)
        if n:
            counts[code] = counts.get(code, 0) + n
    if re.search(r"\bRs\.?\s*\d", text, re.IGNORECASE):
        counts["INR"] = counts.get("INR", 0) + 2
    if counts:
        code = max(counts, key=counts.__getitem__)
        # "$" is shared by many currencies; only trust it moderately.
        confidence = 0.7 if code == "USD" else 0.9
        return code, confidence, code
    if re.search(r"\b(GSTIN|CGST|SGST|IGST)\b", text, re.IGNORECASE):
        return "INR", 0.75, "GST"
    return None, 0.0, None


# ---------------------------------------------------------------- dates

_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ]
    )
    for m in names
}
_MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

_DATE_PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")),
    ("numeric", re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b")),
    ("d_mon_y", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.,]*{_MONTH_RE}[\s\-/.,']*(\d{{4}}|\d{{2}})\b", re.I)),
    ("mon_d_y", re.compile(rf"\b{_MONTH_RE}[\s\-/.]*(\d{{1,2}})(?:st|nd|rd|th)?[\s,\-/.']*(\d{{4}}|\d{{2}})\b", re.I)),
]


@dataclass
class DateMatch:
    value: date
    raw: str
    ambiguous: bool  # e.g. 04/05/2026 could be April 5 or May 4
    start: int
    end: int


def _year(y: str) -> int:
    n = int(y)
    return n + 2000 if n < 100 else n


def _make(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str, *, dayfirst: bool = True) -> list[DateMatch]:
    out: list[DateMatch] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            ambiguous = False
            if kind == "iso":
                value = _make(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif kind == "numeric":
                a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
                first = _make(y, b, a) if dayfirst else _make(y, a, b)
                second = _make(y, a, b) if dayfirst else _make(y, b, a)
                value = first or second
                ambiguous = bool(first and second and a != b)
            elif kind == "d_mon_y":
                value = _make(_year(m.group(3)), _MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
            else:
                value = _make(_year(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
            if value is None or not (1990 <= value.year <= 2100):
                continue
            taken.append((m.start(), m.end()))
            out.append(DateMatch(value=value, raw=m.group(0).strip(), ambiguous=ambiguous, start=m.start(), end=m.end()))
    out.sort(key=lambda d: d.start)
    return out


def parse_date(text: str | None, *, dayfirst: bool = True) -> date | None:
    if not text:
        return None
    matches = find_dates(str(text), dayfirst=dayfirst)
    return matches[0].value if matches else None


_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?::([0-5]\d))?\s*(am|pm|AM|PM)?\b")


def find_time(text: str) -> tuple[str, str] | None:
    """Return ``(HH:MM, raw)`` for the first plausible clock time."""
    for m in _TIME_RE.finditer(text):
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = (m.group(4) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        # "12.50" without am/pm on a receipt is far more likely money than a time.
        if m.group(0).count(".") and not ampm:
            continue
        return f"{hour:02d}:{minute:02d}", m.group(0).strip()
    return None


# ---------------------------------------------------------------- GSTIN (India)

GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum_ok(gstin: str) -> bool:
    gstin = gstin.strip().upper()
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", gstin):
        return False
    total = 0
    for i, ch in enumerate(gstin[:14]):
        product = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _GST_CHARS[(36 - total % 36) % 36] == gstin[14]


def find_gstins(text: str) -> list[str]:
    # OCR sometimes inserts spaces; collapse them inside 15-char candidates.
    compact = re.sub(r"(?<=[0-9A-Z]) (?=[0-9A-Z])", "", text.upper())
    seen: list[str] = []
    for m in GSTIN_RE.finditer(compact):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def normalise_label(text: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", text.lower()).strip()
