"""JSON shapes the frontend consumes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import versioning
from ..document_data import DocumentData
from ..models import Document, DocumentVersion
from ..pipeline_constants import CONFIDENT_CLASSIFICATION, MISMATCH_CONFIDENCE
from ..understanding.schema import DOC_TYPE_LABELS, schema_for
from ..validation import validate


def summary(doc: Document) -> dict:
    approved = bool(doc.approved_version_id and doc.approved_version_id == doc.head_version_id)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "status": doc.status,
        "error": doc.error,
        "doc_type": doc.doc_type,
        "party": doc.party,
        "reference": doc.reference,
        "doc_date": doc.doc_date,
        "total": doc.total,
        "currency": doc.currency,
        "review_count": doc.review_count,
        "approved": approved,
        "edited_after_approval": bool(doc.approved_version_id and not approved),
        "duplicate_of": doc.duplicate_of or [],
        "page_count": len(doc.pages or []),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
    }


def schema_json(doc_type: str) -> list[dict]:
    return [
        {"key": f.key, "label": f.label, "kind": f.kind, "group": f.group, "required": f.required}
        for f in schema_for(doc_type)
    ]


def classification_json(doc: Document, data: DocumentData | None) -> dict | None:
    c = doc.classification
    if not c:
        return None
    current = data.doc_type if data else doc.doc_type
    detected, confidence = c.get("detected_type"), float(c.get("confidence") or 0)
    mismatch = (
        detected is not None
        and current != detected
        and confidence >= MISMATCH_CONFIDENCE
        and not c.get("mismatch_dismissed")
    )
    uncertain = confidence < CONFIDENT_CLASSIFICATION and not c.get("mismatch_dismissed") and not doc.requested_type
    return {
        **c,
        "current_type": current,
        "detected_label": DOC_TYPE_LABELS.get(detected or "", detected),
        "mismatch": mismatch,
        "uncertain": uncertain and not mismatch,
        "requested_type": doc.requested_type,
    }


def version_json(v: DocumentVersion, *, active: bool, head: bool) -> dict:
    return {
        "id": v.id,
        "number": v.number,
        "parent_id": v.parent_id,
        "author": v.author,
        "message": v.message,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "active": active,
        "head": head,
    }


def detail(session: Session, doc: Document) -> dict:
    data = versioning.head_data(session, doc)
    head = versioning.head(session, doc)
    out = summary(doc)
    out.update(
        {
            "error_detail": doc.error_detail,
            "engine": doc.engine,
            "pages": [
                {"index": p["index"], "width": p["width"], "height": p["height"],
                 "url": f"/api/documents/{doc.id}/pages/{p['index']}"}
                for p in (doc.pages or [])
            ],
            "file_url": f"/api/documents/{doc.id}/file",
            "classification": classification_json(doc, data),
            "schema": schema_json(data.doc_type) if data else [],
            "type_labels": DOC_TYPE_LABELS,
            "data": data.model_dump(mode="json") if data else None,
            "validation": validate(data).as_dict() if data else None,
            "version": {"id": head.id, "number": head.number, "message": head.message} if head else None,
            "can_undo": versioning.can_undo(session, doc),
            "can_redo": versioning.redo_target(session, doc) is not None,
        }
    )
    return out
