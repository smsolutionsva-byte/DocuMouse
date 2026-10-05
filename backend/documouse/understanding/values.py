"""Canonical forms for field values, shared by extraction, editing and validation."""

from __future__ import annotations

import re
from datetime import date

from .parsing import (
    CURRENCY_CODES,
    _MONTH_RE,
    _MONTHS,
    currency_from_token,
    find_dates,
    find_time,
    format_amount,
    parse_amount,
)


def canonicalize(kind: str, text: str | None, *, dayfirst: bool = True, reference_year: int | None = None) -> str | None:
    """Return the canonical string for ``text`` or None if it can't be read as ``kind``.

    Used for values typed by people or proposed by an LLM. Text fields are only
    trimmed; structured kinds must parse cleanly.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if kind == "amount":
        value = parse_amount(s)
        return format_amount(value) if value is not None else None
    if kind == "date":
        dates = find_dates(s, dayfirst=dayfirst)
        if dates:
            return dates[0].value.isoformat()
        return _month_day(s, reference_year or date.today().year)
    if kind == "time":
        found = find_time(s)
        return found[0] if found else None
    if kind == "currency":
        token = s.upper()
        if token in CURRENCY_CODES:
            return token
        return currency_from_token(s)
    if kind == "gstin":
        return re.sub(r"\s+", "", s).upper()
    return s


def _month_day(s: str, year: int) -> str | None:
    """'October 4' / '4 Oct' without a year → that day in ``year``."""
    m = re.fullmatch(rf"\s*{_MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*", s, re.I)
    if m:
        month, day = _MONTHS[m.group(1).lower()[:3]], int(m.group(2))
    else:
        m = re.fullmatch(rf"\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_RE}\.?\s*", s, re.I)
        if not m:
            return None
        day, month = int(m.group(1)), _MONTHS[m.group(2).lower()[:3]]
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None
