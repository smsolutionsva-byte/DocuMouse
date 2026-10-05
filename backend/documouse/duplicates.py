"""Spot documents that look like ones already uploaded. Never deletes anything."""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Document, DocumentStatus


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def find_duplicates(session: Session, doc: Document) -> list[dict]:
    conditions = [Document.sha256 == doc.sha256]
    if doc.reference:
        conditions.append(Document.reference == doc.reference)
    if doc.party and doc.total:
        conditions.append(Document.total == doc.total)
    candidates = session.scalars(
        select(Document).where(Document.id != doc.id, Document.status != DocumentStatus.FAILED, or_(*conditions)).limit(200)
    )
    found: list[dict] = []
    for other in candidates:
        if other.sha256 == doc.sha256:
            found.append({"id": other.id, "filename": other.filename, "reason": "Same file"})
            continue
        same_party = bool(doc.party and other.party and _norm(doc.party) == _norm(other.party))
        if doc.reference and other.reference and _norm(doc.reference) == _norm(other.reference) and doc.doc_type == other.doc_type:
            if same_party or not (doc.party and other.party):
                found.append({"id": other.id, "filename": other.filename, "reason": "Same invoice number" + (" and vendor" if same_party else "")})
                continue
        if same_party and doc.total and doc.total == other.total and doc.doc_date and doc.doc_date == other.doc_date:
            found.append({"id": other.id, "filename": other.filename, "reason": "Same vendor, date and total"})
    return found


def link_duplicates(session: Session, doc: Document) -> None:
    """Flag ``doc`` and every earlier look-alike, so both sides show the warning."""
    found = find_duplicates(session, doc)
    doc.duplicate_of = found or None
    for match in found:
        other = session.get(Document, match["id"])
        if other is None:
            continue
        existing = list(other.duplicate_of or [])
        if not any(d["id"] == doc.id for d in existing):
            # Reassign (not append) so the JSON column is marked as changed.
            other.duplicate_of = existing + [{"id": doc.id, "filename": doc.filename, "reason": match["reason"]}]
