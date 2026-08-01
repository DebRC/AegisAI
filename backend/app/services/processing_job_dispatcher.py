from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ProcessingJobPersistenceError
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.processing_outbox_event_repository import ProcessingOutboxEventRepository

PublishJob = Callable[[str, int], str]


@dataclass(frozen=True)
class DispatchSummary:
    published: int
    deferred: int


class ProcessingJobDispatcher:
    """Publish durable events while keeping database transactions short."""

    SAFE_BROKER_ERROR = "Background processing dispatch is temporarily unavailable."

    def __init__(self, db: Session, publish_job: PublishJob):
        self.db = db
        self.jobs = ProcessingJobRepository(db)
        self.events = ProcessingOutboxEventRepository(db)
        self.publish_job = publish_job

    def dispatch_pending(self, *, limit: int = 100, now: datetime | None = None) -> DispatchSummary:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        timestamp = now or datetime.now(timezone.utc)
        published = deferred = 0
        for event_id in self.events.list_publishable_ids(now=timestamp, limit=limit):
            if not self.events.claim_for_publication(event_id=event_id, now=timestamp):
                continue
            self._commit()
            event = self.events.get_by_id(event_id)
            if event is None:
                continue
            job = self.jobs.get_by_id(event.processing_job_id)
            if job is None:
                continue
            try:
                task_id = self.publish_job(job.job_type, job.id)
            except Exception:
                self.events.reschedule_after_failure(event_id=event.id, available_at=timestamp + timedelta(seconds=self._retry_delay(event.publish_attempt_count)), safe_error=self.SAFE_BROKER_ERROR)
                self._commit()
                deferred += 1
                continue
            self.events.mark_published(event_id=event.id, broker_task_id=task_id, now=timestamp)
            job.broker_task_id = task_id
            self._commit()
            published += 1
        return DispatchSummary(published=published, deferred=deferred)

    @staticmethod
    def _retry_delay(attempts: int) -> int:
        return min(2 ** min(max(attempts, 1), 8), 300)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception as error:
            self.db.rollback()
            raise ProcessingJobPersistenceError() from error
