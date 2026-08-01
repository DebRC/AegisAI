from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Index
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

    embeddings: Mapped[list["DocumentChunkEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class DocumentChunkEmbedding(Base):
    """Durable pointer from an authoritative chunk to a derived Qdrant point."""

    __tablename__ = "document_chunk_embeddings"
    __table_args__ = (
        Index("ix_document_chunk_embeddings_chunk_id", "document_chunk_id"),
        CheckConstraint("vector_dimension > 0", name="ck_document_chunk_embeddings_dimension_positive"),
        CheckConstraint("length(point_id) = 36", name="ck_document_chunk_embeddings_point_id_uuid_length"),
        UniqueConstraint(
            "document_chunk_id",
            "provider",
            "model",
            "collection_name",
            name="uq_document_chunk_embeddings_chunk_provider_model_collection",
        ),
        UniqueConstraint(
            "collection_name",
            "point_id",
            name="uq_document_chunk_embeddings_collection_point_id",
        ),
    )

    document_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # These values identify the derived index shape. They are deliberately
    # stored with the point so changing provider/model/collection requires an
    # explicit reindex rather than silently mixing incompatible vectors.
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    collection_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Qdrant accepts UUID point identifiers. The later indexing service derives
    # this value deterministically, enabling idempotent upserts and cleanup.
    point_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )

    vector_dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # A vector is current only when this checksum still matches its chunk.
    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    chunk: Mapped["DocumentChunk"] = relationship(
        back_populates="embeddings",
    )
