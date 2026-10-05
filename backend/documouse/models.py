from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentStatus:
    """Processing stages, in order. The UI maps each to friendly copy."""

    QUEUED = "queued"
    READING = "reading"  # document engine (PaddleOCR / PP-StructureV3)
    UNDERSTANDING = "understanding"  # classification
    EXTRACTING = "extracting"  # field + table extraction
    CHECKING = "checking"  # deterministic validation
    READY = "ready"
    FAILED = "failed"

    IN_PROGRESS = (QUEUED, READING, UNDERSTANDING, EXTRACTING, CHECKING)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # The original upload. Never modified or deleted by processing or editing.
    storage_key: Mapped[str] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.QUEUED, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What the user picked at upload ("invoice", "receipt") or None for auto-detect.
    requested_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {"detected_type", "confidence", "scores", "mismatch_dismissed"}
    classification: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # [{"index", "width", "height", "image_key"}]
    pages: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)

    head_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Set when a person approves the extracted data. If the head moves on afterwards,
    # the UI shows the document as "edited since approval".
    approved_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Denormalised from the head version so the library can search and filter cheaply.
    doc_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    party: Mapped[str | None] = mapped_column(String(512), nullable=True)  # vendor / merchant
    reference: Mapped[str | None] = mapped_column(String(256), nullable=True)  # invoice number
    doc_date: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ISO date
    total: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    search_text: Mapped[str] = mapped_column(Text, default="")
    duplicate_of: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", order_by="DocumentVersion.number", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    """An immutable snapshot of the extracted data.

    History is a tree: undo moves the document's head to the parent, redo moves it
    back to the most recent child, and a new edit after an undo starts a new branch.
    Nothing is ever overwritten.
    """

    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    author: Mapped[str] = mapped_column(String(16))  # system | user | ai
    message: Mapped[str] = mapped_column(String(512))
    operations: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    data: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")
