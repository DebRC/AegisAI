from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class DocumentExtraction(Base):
    """The current normalized text produced from one active source document."""

    __tablename__ = "document_extractions"
    __table_args__ = (
        CheckConstraint("character_count > 0", name="ck_document_extractions_character_count_positive"),
        UniqueConstraint("document_id", name="uq_document_extractions_document_id"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    normalized_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    text_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    extractor_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        back_populates="extraction",
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.ordinal",
    )


class DocumentChunk(Base):
    """One ordered, traceable segment of a document's normalized text."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_document_chunks_ordinal_non_negative"),
        CheckConstraint("start_offset >= 0", name="ck_document_chunks_start_offset_non_negative"),
        CheckConstraint("end_offset > start_offset", name="ck_document_chunks_end_offset_after_start"),
        UniqueConstraint("document_extraction_id", "ordinal", name="uq_document_chunks_extraction_ordinal"),
    )

    document_extraction_id: Mapped[int] = mapped_column(
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    start_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_offset: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # A chunk may span source pages or paragraphs. The worker persists a
    # JSON-safe ordered list only when the extractor can provide locations.
    source_locations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    extraction: Mapped["DocumentExtraction"] = relationship(
        back_populates="chunks",
    )
