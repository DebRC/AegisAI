from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class ProcessingOutboxEventStatus(str, Enum):
    """Delivery state for an event that must be sent to the broker."""

    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class ProcessingOutboxEvent(Base):
    """Durable broker-publication request created with a processing job."""

    __tablename__ = "processing_outbox_events"
    __table_args__ = (
        Index(
            "ix_processing_outbox_events_status_available_at",
            "status",
            "available_at",
        ),
        Index(
            "ix_processing_outbox_events_processing_job_id",
            "processing_job_id",
        ),
    )

    processing_job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        default="processing_job.queued",
        server_default="processing_job.queued",
        nullable=False,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    status: Mapped[ProcessingOutboxEventStatus] = mapped_column(
        SqlEnum(
            ProcessingOutboxEventStatus,
            name="processing_outbox_event_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=ProcessingOutboxEventStatus.PENDING,
        server_default=ProcessingOutboxEventStatus.PENDING.value,
        nullable=False,
    )

    publish_attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    broker_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    processing_job: Mapped["ProcessingJob"] = relationship(
        back_populates="outbox_events",
    )
