from datetime import datetime

from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.processing_job import ProcessingJob
from app.models.processing_outbox_event import ProcessingOutboxEvent
from app.models.processing_outbox_event import ProcessingOutboxEventStatus


class ProcessingOutboxEventRepository:
    """Database operations for durable broker-publication requests."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, event: ProcessingOutboxEvent) -> ProcessingOutboxEvent:
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event

    def get_by_id(self, event_id: int) -> ProcessingOutboxEvent | None:
        return self.db.scalar(
            select(ProcessingOutboxEvent).where(ProcessingOutboxEvent.id == event_id)
        )

    def list_publishable_ids(self, *, now: datetime, limit: int) -> list[int]:
        return list(
            self.db.scalars(
                select(ProcessingOutboxEvent.id)
                .where(
                    ProcessingOutboxEvent.status
                    == ProcessingOutboxEventStatus.PENDING,
                    ProcessingOutboxEvent.available_at <= now,
                )
                .order_by(
                    ProcessingOutboxEvent.available_at.asc(),
                    ProcessingOutboxEvent.id.asc(),
                )
                .limit(limit)
            )
        )

    def claim_for_publication(self, *, event_id: int, now: datetime) -> bool:
        """Atomically reserve one pending event for a broker call."""
        result = self.db.execute(
            update(ProcessingOutboxEvent)
            .where(
                ProcessingOutboxEvent.id == event_id,
                ProcessingOutboxEvent.status
                == ProcessingOutboxEventStatus.PENDING,
                ProcessingOutboxEvent.available_at <= now,
            )
            .values(
                status=ProcessingOutboxEventStatus.PUBLISHING,
                locked_at=now,
                publish_attempt_count=(
                    ProcessingOutboxEvent.publish_attempt_count + 1
                ),
                last_error=None,
            )
        )
        return result.rowcount == 1

    def mark_published(
        self,
        *,
        event_id: int,
        broker_task_id: str,
        now: datetime,
    ) -> bool:
        result = self.db.execute(
            update(ProcessingOutboxEvent)
            .where(
                ProcessingOutboxEvent.id == event_id,
                ProcessingOutboxEvent.status
                == ProcessingOutboxEventStatus.PUBLISHING,
            )
            .values(
                status=ProcessingOutboxEventStatus.PUBLISHED,
                broker_task_id=broker_task_id,
                published_at=now,
                locked_at=None,
                last_error=None,
            )
        )
        return result.rowcount == 1

    def reschedule_after_failure(
        self,
        *,
        event_id: int,
        available_at: datetime,
        safe_error: str,
    ) -> bool:
        result = self.db.execute(
            update(ProcessingOutboxEvent)
            .where(
                ProcessingOutboxEvent.id == event_id,
                ProcessingOutboxEvent.status
                == ProcessingOutboxEventStatus.PUBLISHING,
            )
            .values(
                status=ProcessingOutboxEventStatus.PENDING,
                available_at=available_at,
                locked_at=None,
                last_error=safe_error,
            )
        )
        return result.rowcount == 1

    def cancel_nonterminal_for_document(self, *, document_id: int) -> int:
        result = self.db.execute(
            update(ProcessingOutboxEvent)
            .where(
                ProcessingOutboxEvent.processing_job_id.in_(
                    select(ProcessingJob.id).where(
                        ProcessingJob.document_id == document_id
                    )
                ),
                ProcessingOutboxEvent.status.in_(
                    [
                        ProcessingOutboxEventStatus.PENDING,
                        ProcessingOutboxEventStatus.PUBLISHING,
                    ]
                ),
            )
            .values(
                status=ProcessingOutboxEventStatus.CANCELLED,
                locked_at=None,
            )
        )
        return result.rowcount or 0
