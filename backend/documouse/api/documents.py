from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import versioning
from ..config import get_settings
from ..db import get_session
from ..document_data import DocumentData
from ..editing.assistant import interpret
from ..editing.operations import OperationError, apply_operations, parse_operations
from ..editing.preview import build_preview, describe
from ..export.csv_export import document_csv, library_csv
from ..llm import get_llm
from ..models import Document, DocumentStatus, DocumentVersion, utcnow
from ..processing import runner
from ..processing.pages import SUPPORTED_TYPES, sniff_content_type
from ..processing.pipeline import load_raw, reextract
from ..storage import get_storage
from ..understanding.schema import DOC_TYPES
from ..validation import validate
from . import serializers

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get(session: Session, doc_id: str) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


def _ready(session: Session, doc_id: str) -> tuple[Document, DocumentData]:
    doc = _get(session, doc_id)
    data = versioning.head_data(session, doc)
    if data is None:
        raise HTTPException(409, "This document is still being processed.")
    return doc, data


# ------------------------------------------------------------------ upload & list

@router.post("", status_code=201)
async def upload(
    file: UploadFile = File(...),
    doc_type: str | None = Form(default=None),
    session: Session = Depends(get_session),
):
    settings = get_settings()
    if doc_type in ("", "auto"):
        doc_type = None
    if doc_type is not None and doc_type not in DOC_TYPES:
        raise HTTPException(422, "Unknown document type")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"That file is bigger than {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(422, "That file is empty.")
    content_type = sniff_content_type(data)
    if content_type not in SUPPORTED_TYPES:
        raise HTTPException(415, "DocuMouse reads PDFs and images (JPG, PNG, WebP, TIFF).")

    filename = re.sub(r"[\x00-\x1f/\\]", "_", file.filename or "document")[:200]
    doc = Document(
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key="",
        requested_type=doc_type,
        status=DocumentStatus.QUEUED,
    )
    session.add(doc)
    session.flush()
    doc.storage_key = f"documents/{doc.id}/original.{SUPPORTED_TYPES[content_type]}"
    get_storage().put(doc.storage_key, data)
    same_file = session.scalars(
        select(Document).where(Document.sha256 == doc.sha256, Document.id != doc.id).limit(5)
    ).all()
    if same_file:
        doc.duplicate_of = [{"id": d.id, "filename": d.filename, "reason": "Same file"} for d in same_file]
    session.commit()
    runner.enqueue(doc.id)
    return serializers.summary(doc)


@router.get("")
def list_documents(
    q: str | None = None,
    type: str | None = None,
    status: Literal["needs_review", "ready", "approved", "processing", "failed"] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
):
    stmt = select(Document)
    if q:
        for term in q.lower().split()[:8]:
            stmt = stmt.where(Document.search_text.contains(term) | func.lower(Document.filename).contains(term))
    if type:
        stmt = stmt.where(Document.doc_type == type)
    if status == "needs_review":
        stmt = stmt.where(Document.status == DocumentStatus.READY, Document.review_count > 0)
    elif status == "ready":
        stmt = stmt.where(Document.status == DocumentStatus.READY)
    elif status == "approved":
        stmt = stmt.where(Document.approved_version_id.is_not(None), Document.approved_version_id == Document.head_version_id)
    elif status == "processing":
        stmt = stmt.where(Document.status.in_(DocumentStatus.IN_PROGRESS))
    elif status == "failed":
        stmt = stmt.where(Document.status == DocumentStatus.FAILED)
    if date_from:
        stmt = stmt.where(Document.doc_date >= date_from)
    if date_to:
        stmt = stmt.where(Document.doc_date <= date_to)
    docs = session.scalars(stmt.order_by(Document.created_at.desc()).limit(limit)).all()
    return {"documents": [serializers.summary(d) for d in docs]}


@router.get("/stats")
def stats(session: Session = Depends(get_session)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    count = lambda *where: session.scalar(select(func.count()).select_from(Document).where(*where)) or 0  # noqa: E731
    return {
        "total": count(),
        "needs_review": count(Document.status == DocumentStatus.READY, Document.review_count > 0),
        "processing": count(Document.status.in_(DocumentStatus.IN_PROGRESS)),
        "processed_today": count(Document.processed_at >= since),
    }


@router.get("/export.csv")
def export_library(ids: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Document).where(Document.status == DocumentStatus.READY)
    if ids:
        stmt = stmt.where(Document.id.in_(ids.split(",")[:500]))
    docs = session.scalars(stmt.order_by(Document.doc_date.desc().nulls_last(), Document.created_at.desc())).all()
    return _csv(library_csv(docs), "documouse-documents.csv")


# ------------------------------------------------------------------ one document

@router.get("/{doc_id}")
def get_document(doc_id: str, session: Session = Depends(get_session)):
    return serializers.detail(session, _get(session, doc_id))


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    if doc.status in DocumentStatus.IN_PROGRESS and doc.status != DocumentStatus.QUEUED:
        raise HTTPException(409, "Wait until DocuMouse has finished reading this document.")
    session.delete(doc)
    session.flush()
    get_storage().delete_prefix(f"documents/{doc_id}")
    return Response(status_code=204)


@router.post("/{doc_id}/retry")
def retry(doc_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    if doc.status != DocumentStatus.FAILED:
        raise HTTPException(409, "Only documents that failed can be retried.")
    doc.status = DocumentStatus.QUEUED
    doc.error = doc.error_detail = None
    session.commit()
    runner.enqueue(doc.id)
    return serializers.summary(doc)


@router.get("/{doc_id}/file")
def original_file(doc_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    safe = re.sub(r'["\\]', "_", doc.filename)
    return Response(
        get_storage().get(doc.storage_key),
        media_type=doc.content_type,
        headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "private, max-age=3600"},
    )


@router.get("/{doc_id}/pages/{index}")
def page_image(doc_id: str, index: int, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    page = next((p for p in (doc.pages or []) if p["index"] == index), None)
    if page is None:
        raise HTTPException(404, "Page not found")
    return Response(get_storage().get(page["image_key"]), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{doc_id}/text")
def document_text(doc_id: str, session: Session = Depends(get_session)):
    """The engine's text lines with positions (for "find in document" and unknown documents)."""
    doc = _get(session, doc_id)
    if doc.status != DocumentStatus.READY:
        raise HTTPException(409, "This document is still being processed.")
    raw = load_raw(doc.id)
    return {"engine": raw.engine, "lines": [ln.model_dump() for ln in raw.lines]}


# ------------------------------------------------------------------ editing

class OperationsIn(BaseModel):
    operations: list[dict] = Field(min_length=1)
    base_version_id: str | None = None
    author: Literal["user", "ai"] = "user"
    message: str | None = Field(default=None, max_length=200)


def _parse(ops_raw: list[dict]) -> list:
    try:
        return parse_operations(ops_raw)
    except ValidationError as exc:
        raise HTTPException(422, f"That change isn't valid: {exc.errors()[0].get('msg')}") from exc
    except OperationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{doc_id}/operations/preview")
def preview_operations(doc_id: str, body: OperationsIn, session: Session = Depends(get_session)):
    _, data = _ready(session, doc_id)
    ops = _parse(body.operations)
    try:
        after = apply_operations(data, ops, author=body.author)
    except OperationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "message": describe(ops, data),
        "changes": build_preview(data, after),
        "validation": validate(after).as_dict(),
    }


@router.post("/{doc_id}/operations")
def apply(doc_id: str, body: OperationsIn, session: Session = Depends(get_session)):
    doc, data = _ready(session, doc_id)
    ops = _parse(body.operations)
    try:
        after = apply_operations(data, ops, author=body.author)
        versioning.commit(
            session, doc, after,
            author=body.author,
            message=body.message or describe(ops, data),
            operations=[op.model_dump() for op in ops],
            base_version_id=body.base_version_id,
        )
    except OperationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except versioning.VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return serializers.detail(session, doc)


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@router.post("/{doc_id}/assistant")
def assistant(doc_id: str, body: AssistantIn, session: Session = Depends(get_session)):
    _, data = _ready(session, doc_id)
    proposal = interpret(body.message, data, get_llm())
    result: dict = {"reply": proposal.reply, "source": proposal.source, "operations": [], "preview": None}
    if proposal.operations:
        after = apply_operations(data, proposal.operations, author="ai")
        result.update(
            operations=[op.model_dump() for op in proposal.operations],
            message=describe(proposal.operations, data),
            preview=build_preview(data, after),
            validation=validate(after).as_dict(),
        )
    return result


@router.post("/{doc_id}/undo")
def undo(doc_id: str, session: Session = Depends(get_session)):
    doc, _ = _ready(session, doc_id)
    try:
        versioning.undo(session, doc)
    except versioning.VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return serializers.detail(session, doc)


@router.post("/{doc_id}/redo")
def redo(doc_id: str, session: Session = Depends(get_session)):
    doc, _ = _ready(session, doc_id)
    try:
        versioning.redo(session, doc)
    except versioning.VersionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return serializers.detail(session, doc)


@router.get("/{doc_id}/versions")
def versions(doc_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    chain = versioning.active_chain(session, doc)
    rows = session.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.number.desc())
    ).all()
    return {"versions": [serializers.version_json(v, active=v.id in chain, head=v.id == doc.head_version_id) for v in rows]}


@router.get("/{doc_id}/versions/{version_id}")
def version(doc_id: str, version_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    v = session.get(DocumentVersion, version_id)
    if v is None or v.document_id != doc.id:
        raise HTTPException(404, "Version not found")
    data = DocumentData.model_validate(v.data)
    current = versioning.head_data(session, doc)
    return {
        **serializers.version_json(v, active=v.id in versioning.active_chain(session, doc), head=v.id == doc.head_version_id),
        "data": data.model_dump(mode="json"),
        "schema": serializers.schema_json(data.doc_type),
        "validation": validate(data).as_dict(),
        "changes_from_current": build_preview(current, data) if current else None,
    }


@router.post("/{doc_id}/versions/{version_id}/restore")
def restore(doc_id: str, version_id: str, session: Session = Depends(get_session)):
    doc, _ = _ready(session, doc_id)
    try:
        versioning.restore(session, doc, version_id)
    except versioning.VersionConflict as exc:
        raise HTTPException(404, str(exc)) from exc
    return serializers.detail(session, doc)


class TypeIn(BaseModel):
    doc_type: Literal["invoice", "receipt", "unknown"]


@router.post("/{doc_id}/type")
def change_type(doc_id: str, body: TypeIn, session: Session = Depends(get_session)):
    doc, data = _ready(session, doc_id)
    if data.doc_type != body.doc_type:
        reextract(session, doc, body.doc_type)
    if doc.classification:
        doc.classification = {**doc.classification, "mismatch_dismissed": True}
    return serializers.detail(session, doc)


@router.post("/{doc_id}/classification/dismiss")
def keep_type(doc_id: str, session: Session = Depends(get_session)):
    doc = _get(session, doc_id)
    if doc.classification:
        doc.classification = {**doc.classification, "mismatch_dismissed": True}
    return serializers.detail(session, doc)


# ------------------------------------------------------------------ approve & export

@router.post("/{doc_id}/approve")
def approve(doc_id: str, session: Session = Depends(get_session)):
    doc, _ = _ready(session, doc_id)
    doc.approved_version_id = doc.head_version_id
    doc.approved_at = utcnow()
    return serializers.detail(session, doc)


@router.get("/{doc_id}/export.csv")
def export_document(doc_id: str, layout: Literal["sections", "line_items"] = "sections",
                    session: Session = Depends(get_session)):
    doc, data = _ready(session, doc_id)
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", doc.filename) or "document"
    suffix = "-line-items" if layout == "line_items" else ""
    return _csv(document_csv(data, layout), f"{stem}{suffix}.csv")


def _csv(content: str, filename: str) -> Response:
    safe = re.sub(r'[^A-Za-z0-9._ -]', "_", filename)
    return Response(content.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})
