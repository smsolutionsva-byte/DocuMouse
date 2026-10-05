"""Compare a second reading with the extracted data, field by field.

Never changes a value. Disagreement flags the field and offers the second reading as a
one-click suggestion; a value only the second reader found is offered, not filled in.

Agreement counts as confirmation only when the second reader chose the value on its own
(a vision model). An OCR-style reading goes through DocuMouse's own rules, so when the
rules pick the wrong line, both readings agree on the same wrong value: its agreement
only shows the characters were read the same way. Such a reader can flag, not confirm.
"""

from __future__ import annotations

import re

from ..document_data import DocumentData, SecondOpinion, Suggestion
from ..understanding.parsing import parse_amount
from ..understanding.rules import RuleExtractor
from ..understanding.values import canonicalize
from .base import KEY_FIELDS, SecondReading

_KINDS = {"name": "text", "date": "date", "total": "amount"}


def key_values(reading: SecondReading, doc_type: str) -> dict[str, str | None]:
    """The second reader's canonical value for each key field of ``doc_type``, by field key."""
    roles = KEY_FIELDS.get(doc_type)
    if not roles:
        return {}
    if reading.raw is not None:
        fields = RuleExtractor(reading.raw).extract(doc_type)
        return {key: fields[key].value if key in fields else None for key in roles.values()}
    out: dict[str, str | None] = {}
    for role, key in roles.items():
        value = reading.values.get(role)
        if role == "name" and value:
            value = " ".join(value.split())
        out[key] = canonicalize(_KINDS[role], value, dayfirst=True)
    return out


def same_value(role: str, a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    if role == "total":
        x, y = parse_amount(a), parse_amount(b)
        return x is not None and x == y
    if role == "name":
        # "SDN. BHD." and "SDN BHD" are the same name; "SDN BHO" is not.
        return _letters(a) == _letters(b)
    return a == b


def _letters(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", text.upper())


def apply_second_reading(data: DocumentData, reading: SecondReading) -> DocumentData:
    roles = KEY_FIELDS.get(data.doc_type)
    if not roles:
        return data
    second = key_values(reading, data.doc_type)
    out = data.model_copy(deep=True)
    for role, key in roles.items():
        field = out.fields.get(key)
        if field is None or field.confirmed or field.origin in ("user", "ai"):
            continue  # a person already decided
        other = second.get(key)
        agrees = same_value(role, field.value, other)
        field.second_opinion = SecondOpinion(reader=reading.reader, value=other, agrees=agrees,
                                             confirms=agrees and reading.raw is None)
        if other is None or agrees:
            # Not finding a value is no evidence against one: the field keeps its own status.
            continue
        if field.value is None:
            reason = f"{reading.reader} found this. Check it against the document before using it."
        else:
            field.notes.insert(0, f"A second reading ({reading.reader}) disagrees. Please check this one.")
            reason = f"What {reading.reader} read."
        if field.suggestion is None:
            field.suggestion = Suggestion(value=other, reason=reason)
    return out
