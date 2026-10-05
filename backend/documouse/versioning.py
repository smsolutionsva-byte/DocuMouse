"""Immutable version history with undo, redo and restore.

Versions form a tree. ``Document.head_version_id`` points at the current one.

* A change creates a child of the head and moves the head to it.
* Undo moves the head to its parent. Nothing is deleted.
* Redo moves the head to the most recently created child.
* Restore copies an old version's data into a brand-new version.

The original upload is stored separately and never touched.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .document_data import DocumentData
from .models import Document, DocumentVersion, utcnow
from .understanding.parsing import parse_amount
from .validation import validate


class VersionConflict(RuntimeError):
    """The document changed since the client loaded it (another tab, another person)."""


def head(session: Session, doc: Document) -> DocumentVersion | None:
    if doc.head_version_id is None:
        return None
    return session.get(DocumentVersion, doc.head_version_id)


def head_data(session: Session, doc: Document) -> DocumentData | None:
    version = head(session, doc)
    return DocumentData.model_validate(version.data) if version else None


def commit(
    session: Session,
    doc: Document,
    data: DocumentData,
    *,
    author: str,
    message: str,
    operations: list | None = None,
    base_version_id: str | None = None,
) -> DocumentVersion:
    if base_version_id is not None and base_version_id != doc.head_version_id:
        raise VersionConflict("This document was changed somewhere else. Reload to see the latest version.")
    number = (session.scalar(select(func.max(DocumentVersion.number)).where(DocumentVersion.document_id == doc.id)) or 0) + 1
    version = DocumentVersion(
        document_id=doc.id,
        number=number,
        parent_id=doc.head_version_id,
        author=author,
        message=message[:500],
        operations=operations,
        data=data.model_dump(mode="json"),
    )
    session.add(version)
    session.flush()
    doc.head_version_id = version.id
    refresh_summary(doc, data)
    return version


def can_undo(session: Session, doc: Document) -> bool:
    current = head(session, doc)
    return bool(current and current.parent_id)


def redo_target(session: Session, doc: Document) -> DocumentVersion | None:
    if doc.head_version_id is None:
        return None
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id, DocumentVersion.parent_id == doc.head_version_id)
        .order_by(DocumentVersion.number.desc())
        .limit(1)
    )


def undo(session: Session, doc: Document) -> DocumentVersion:
    current = head(session, doc)
    if current is None or current.parent_id is None:
        raise VersionConflict("There's nothing to undo.")
    parent = session.get(DocumentVersion, current.parent_id)
    assert parent is not None
    doc.head_version_id = parent.id
    refresh_summary(doc, DocumentData.model_validate(parent.data))
    return parent


def redo(session: Session, doc: Document) -> DocumentVersion:
    target = redo_target(session, doc)
    if target is None:
        raise VersionConflict("There's nothing to redo.")
    doc.head_version_id = target.id
    refresh_summary(doc, DocumentData.model_validate(target.data))
    return target


def restore(session: Session, doc: Document, version_id: str) -> DocumentVersion:
    old = session.get(DocumentVersion, version_id)
    if old is None or old.document_id != doc.id:
        raise VersionConflict("That version doesn't exist.")
    return commit(
        session,
        doc,
        DocumentData.model_validate(old.data),
        author="user",
        message=f"Restored version {old.number}",
        operations=[{"op": "restore", "version": old.number}],
    )


def active_chain(session: Session, doc: Document) -> set[str]:
    """Ids of the head and its ancestors: the versions that make up 'now'."""
    versions = {v.id: v for v in session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))}
    chain: set[str] = set()
    current = versions.get(doc.head_version_id or "")
    while current is not None:
        chain.add(current.id)
        current = versions.get(current.parent_id or "")
    return chain


def refresh_summary(doc: Document, data: DocumentData) -> None:
    """Denormalise the head version into searchable/filterable columns."""
    f = data.fields
    get = lambda k: f[k].value if k in f and f[k].value else None  # noqa: E731
    doc.doc_type = data.doc_type
    doc.party = get("vendor") or get("merchant")
    doc.reference = get("invoice_number")
    doc.doc_date = get("invoice_date") or get("date")
    total = get("total")
    doc.total = total if total and parse_amount(total) is not None else None
    doc.currency = get("currency")
    doc.review_count = validate(data).summary["issues"]
    doc.updated_at = utcnow()
    parts = [doc.filename] + [v.value for v in f.values() if v.value]
    for t in data.tables:
        for r in t.rows[:200]:
            parts.extend(v for v in r.cells.values() if v)
    doc.search_text = " ".join(parts).lower()[:20000]
