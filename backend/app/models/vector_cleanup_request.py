"""Durable Qdrant point-deletion work associated with one processing job."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VectorCleanupRequest(Base):
    """A collection-scoped, retryable list of obsolete derived point IDs."""

    __tablename__ = "vector_cleanup_requests"
    __table_args__ = (
        UniqueConstraint("processing_job_id", name="uq_vector_cleanup_requests_processing_job_id"),
    )

    processing_job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    collection_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # UUIDs are sufficient to delete derived points. Chunk text and document
    # metadata must not be copied into durable cleanup payloads.
    point_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processing_job: Mapped["ProcessingJob"] = relationship()
