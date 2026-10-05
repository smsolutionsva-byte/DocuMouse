"""The processing pipeline for one document.

    original file → page images → document engine (PP-StructureV3)
    → classification → extraction (rules + optional LLM) → validation
    → version 1 → ready for review
"""

from __future__ import annotations

import json
import logging
import traceback

from ..config import get_settings
from ..db import session_scope
from ..duplicates import link_duplicates
from ..llm import get_llm
from ..models import Document, DocumentStatus, utcnow
from ..storage import get_storage
from ..understanding.classify import classify
from ..understanding.extract import extract
from .. import versioning
from .engines import EngineUnavailable, get_engine
from .pages import UnsupportedFile, encode_jpeg, render_pages
from .types import RawDocument

log = logging.getLogger(__name__)


def raw_key(doc_id: str) -> str:
    return f"documents/{doc_id}/engine/document.json"


def _set_status(doc_id: str, status: str) -> None:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is not None:
            doc.status = status


def process_document(doc_id: str) -> None:
    settings = get_settings()
    storage = get_storage()
    try:
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            if doc is None:
                return
            doc.status = DocumentStatus.READING
            doc.error = doc.error_detail = None
            storage_key, content_type, requested = doc.storage_key, doc.content_type, doc.requested_type

        # 1. Reading: page images + the document engine
        pages = render_pages(storage.get(storage_key), content_type, dpi=settings.pdf_render_dpi, max_pages=settings.max_pages)
        engine = get_engine()
        result = engine.process(pages)
        raw = result.document
        page_meta = []
        for page in pages:
            image = result.corrected_pages.get(page.index, page.image)
            key = f"documents/{doc_id}/pages/{page.index}.jpg"
            storage.put(key, encode_jpeg(image))
            page_meta.append({"index": page.index, "width": image.width, "height": image.height, "image_key": key})
        storage.put(raw_key(doc_id), raw.model_dump_json().encode())
        storage.put(f"documents/{doc_id}/engine/native.json", json.dumps(result.native, default=str).encode())
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            doc.pages = page_meta
            doc.engine = f"{raw.engine} {raw.engine_version or ''}".strip()
            doc.status = DocumentStatus.UNDERSTANDING

        # 2. Understanding: what kind of document is this?
        classification = classify(raw)
        # The user's pick wins, but the review screen warns if it looks wrong. Without a pick,
        # the best guess is extracted and a low-confidence guess is put to the user to confirm.
        doc_type = requested or classification.detected_type
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            doc.classification = {**classification.as_dict(), "mismatch_dismissed": False}
            doc.status = DocumentStatus.EXTRACTING

        # 3. Extracting
        data = extract(raw, doc_type, llm=get_llm())
        _set_status(doc_id, DocumentStatus.CHECKING)

        # 4. Checking + first version
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            versioning.commit(s, doc, data, author="system", message="Initial extraction")
            link_duplicates(s, doc)
            doc.status = DocumentStatus.READY
            doc.processed_at = utcnow()
    except UnsupportedFile as exc:
        _fail(doc_id, str(exc) or "DocuMouse can't read this kind of file yet.", None)
    except EngineUnavailable as exc:
        log.error("Document engine unavailable: %s", exc)
        _fail(doc_id, "DocuMouse's reading engine isn't available right now.", str(exc))
    except Exception as exc:  # noqa: BLE001 - surface every failure to the user, never hang
        log.exception("Processing failed for %s", doc_id)
        _fail(doc_id, "Something went wrong while reading this document.", "".join(traceback.format_exception_only(exc)).strip())


def reextract(session, doc: Document, doc_type: str) -> None:
    """Re-run extraction from the stored engine output (no OCR) as a new version."""
    raw = load_raw(doc.id)
    data = extract(raw, doc_type, llm=get_llm())
    from ..understanding.schema import DOC_TYPE_LABELS

    versioning.commit(session, doc, data, author="user", message=f"Changed type to {DOC_TYPE_LABELS[doc_type].lower()}",
                      operations=[{"op": "set_doc_type", "doc_type": doc_type}])


def load_raw(doc_id: str) -> RawDocument:
    return RawDocument.model_validate_json(get_storage().get(raw_key(doc_id)))


def _fail(doc_id: str, message: str, detail: str | None) -> None:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is not None:
            doc.status = DocumentStatus.FAILED
            doc.error = message
            doc.error_detail = detail
