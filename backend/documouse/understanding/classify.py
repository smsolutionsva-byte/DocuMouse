"""Decide what kind of document this is, with an honest confidence.

Deterministic and explainable: every point of evidence is recorded so the UI
can say *why* DocuMouse thinks a document is an invoice.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..processing.types import RawDocument

# (pattern, weight, human explanation)
_INVOICE_SIGNALS: list[tuple[str, float, str]] = [
    (r"\btax\s+invoice\b", 4.0, "Says “Tax Invoice”"),
    (r"\binvoice\b", 3.0, "Mentions “invoice”"),
    (r"\b(invoice|inv|bill)\s*(no|number|#|num)\b", 3.0, "Has an invoice number"),
    (r"\bbill(ed)?\s+to\b|\binvoice\s+to\b", 2.0, "Has a “Bill to” section"),
    (r"\bdue\s+date\b|\bpayment\s+due\b|\bdue\s+by\b", 2.0, "Has a due date"),
    (r"\bpayment\s+terms\b|\bnet\s+\d{1,2}\b", 1.5, "Mentions payment terms"),
    (r"\bhsn\b|\bsac\b", 2.0, "Lists HSN/SAC codes"),
    (r"\bship\s+to\b", 1.0, "Has a “Ship to” section"),
    (r"\b(ifsc|account\s+(no|number)|bank\s+details|swift|iban)\b", 1.5, "Includes bank details for payment"),
    (r"\bpurchase\s+order\b|\bp\.?o\.?\s*(no|number|#)\b", 1.0, "References a purchase order"),
]
_RECEIPT_SIGNALS: list[tuple[str, float, str]] = [
    (r"\breceipt\b", 3.0, "Mentions “receipt”"),
    (r"\b(cash|change\s+due|change)\b", 1.5, "Mentions cash or change"),
    (r"\btender(ed)?\b", 2.0, "Shows the amount tendered"),
    (r"\b(cashier|till|terminal|pos|register|store\s*#?|counter)\b", 1.5, "Mentions a cashier or till"),
    (r"\b(visa|mastercard|amex|rupay|upi|debit|credit\s+card|card\s+no|card\s+ending)\b", 1.5, "Shows card or UPI payment"),
    (r"\b(auth(orization)?\s*code|approval\s*code|approved|txn\s*id|transaction\s*id|rrn)\b", 1.5, "Has a payment approval code"),
    (r"\bthank\s+you\b|\bvisit\s+again\b|\bcome\s+again\b", 1.0, "Says “thank you” / “visit again”"),
    (r"\b(table\s*(no|#)|server|guests?|covers)\b", 1.0, "Looks like a restaurant bill"),
    (r"\bamount\s+paid\b|\bpaid\b", 1.0, "Shows the amount paid"),
    (r"\b([01]?\d|2[0-3]):[0-5]\d\b", 1.0, "Has a time of purchase"),
]


@dataclass
class Classification:
    detected_type: str
    confidence: float
    scores: dict[str, float]
    signals: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "detected_type": self.detected_type,
            "confidence": round(self.confidence, 3),
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
            "signals": self.signals,
        }


def _score(text: str, signals: list[tuple[str, float, str]]) -> tuple[float, list[str]]:
    total, reasons = 0.0, []
    for pattern, weight, why in signals:
        if re.search(pattern, text, re.IGNORECASE):
            total += weight
            reasons.append(why)
    return total, reasons


def classify(raw: RawDocument) -> Classification:
    text = raw.full_text
    inv, inv_reasons = _score(text, _INVOICE_SIGNALS)
    rec, rec_reasons = _score(text, _RECEIPT_SIGNALS)

    # Till receipts are long and narrow.
    if raw.pages:
        p = raw.pages[0]
        if p.width and p.height / p.width > 2.0:
            rec += 2.0
            rec_reasons.append("Long, narrow paper like a till receipt")

    # "Unknown" competes with a constant prior: weak evidence stays uncertain.
    unknown = 3.0 if text.strip() else 10.0
    raw_scores = {"invoice": inv, "receipt": rec, "unknown": unknown}
    temperature = 2.0
    exp = {k: math.exp(v / temperature) for k, v in raw_scores.items()}
    z = sum(exp.values())
    probs = {k: v / z for k, v in exp.items()}
    detected = max(probs, key=probs.__getitem__)
    return Classification(
        detected_type=detected,
        confidence=probs[detected],
        scores=probs,
        signals={"invoice": inv_reasons, "receipt": rec_reasons},
    )
