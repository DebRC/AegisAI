from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class ProcessingJobStatus(str, Enum):
    """Operational state of one durable document-processing job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingJob(Base):
    """Durable work record executed asynchronously by a Celery worker."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_document_id_created_at", "document_id", "created_at"),
        Index("ix_processing_jobs_status_queued_at", "status", "queued_at"),
        Index("ix_processing_jobs_broker_task_id", "broker_task_id"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # New pipeline stages can use additional names without a PostgreSQL enum
    # migration. Phase 7 creates only source_integrity jobs.
    job_type: Mapped[str] = mapped_column(
        String(64),
        default="source_integrity",
        server_default="source_integrity",
        nullable=False,
    )

    status: Mapped[ProcessingJobStatus] = mapped_column(
        SqlEnum(
            ProcessingJobStatus,
            name="processing_job_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=ProcessingJobStatus.QUEUED,
        server_default=ProcessingJobStatus.QUEUED.value,
        nullable=False,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    broker_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    document: Mapped["Document"] = relationship(
        back_populates="processing_jobs",
    )

    outbox_events: Mapped[list["ProcessingOutboxEvent"]] = relationship(
        back_populates="processing_job",
        cascade="all, delete-orphan",
    )
