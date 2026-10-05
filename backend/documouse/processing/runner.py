"""In-process background worker.

A thread pool is enough for the MVP: documents are queued in the database, so a
restart simply picks up whatever was in flight. When processing needs to scale
out, this is the one module to swap for a real queue (e.g. RQ, Celery, Arq).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import Document, DocumentStatus
from .pipeline import process_document

log = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=get_settings().processing_workers, thread_name_prefix="documouse")
    return _executor


def enqueue(doc_id: str) -> None:
    _pool().submit(process_document, doc_id)


def resume_pending() -> int:
    with session_scope() as s:
        ids = list(s.scalars(select(Document.id).where(Document.status.in_(DocumentStatus.IN_PROGRESS)).order_by(Document.created_at)))
        for doc in s.scalars(select(Document).where(Document.id.in_(ids))):
            doc.status = DocumentStatus.QUEUED
    for doc_id in ids:
        enqueue(doc_id)
    if ids:
        log.info("Resumed %d unfinished documents", len(ids))
    return len(ids)


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
