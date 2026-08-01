from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentNotFoundError, ProcessingJobNotFoundError, ProcessingJobPersistenceError, ProcessingJobStateError
from app.models.document import DocumentStatus
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.processing_outbox_event import ProcessingOutboxEvent
from app.repositories.document_repository import DocumentRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.processing_outbox_event_repository import ProcessingOutboxEventRepository


@dataclass(frozen=True)
class JobClaim:
    job: ProcessingJob
    claimed: bool


class ProcessingJobService:
    """Coordinate durable job and outbox state with explicit transactions."""

    SOURCE_INTEGRITY_JOB_TYPE = "source_integrity"
    TEXT_EXTRACTION_JOB_TYPE = "text_extraction"
    EVENT_TYPE = "processing_job.queued"

    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.jobs = ProcessingJobRepository(db)
        self.outbox_events = ProcessingOutboxEventRepository(db)

    def create_source_integrity_job(self, *, document_id: int, now: datetime | None = None) -> ProcessingJob:
        """Add a job and an outbox event, leaving the caller to commit both."""
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        timestamp = now or self._now()
        return self._create_queued_job(
            document_id=document.id,
            job_type=self.SOURCE_INTEGRITY_JOB_TYPE,
            timestamp=timestamp,
        )

    def create_text_extraction_job(self, *, document_id: int, now: datetime | None = None) -> ProcessingJob:
        """Create the next durable pipeline stage and leave the caller to commit."""
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return self._create_queued_job(
            document_id=document.id,
            job_type=self.TEXT_EXTRACTION_JOB_TYPE,
            timestamp=now or self._now(),
        )

    def get_document_job(self, *, document_id: int, job_id: int) -> ProcessingJob:
        job = self.jobs.get_by_document_and_id(document_id=document_id, job_id=job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        return job

    def list_document_jobs(self, document_id: int) -> list[ProcessingJob]:
        if self.documents.get_active_by_id(document_id) is None:
            raise DocumentNotFoundError()
        return self.jobs.list_by_document_id(document_id)

    def claim_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
        expected_job_type: str | None = None,
    ) -> JobClaim:
        """Atomically allow one worker to run a queued job."""
        claimed = self.jobs.claim_queued(
            job_id=job_id,
            now=now or self._now(),
            expected_job_type=expected_job_type,
        )
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        if claimed:
            self._commit()
        return JobClaim(job=job, claimed=claimed)

    def complete_job(self, *, job_id: int, now: datetime | None = None) -> ProcessingJob:
        job = self._running_job(job_id)
        job.status = ProcessingJobStatus.SUCCEEDED
        job.finished_at = now or self._now()
        job.error_message = None
        self._commit()
        return job

    def complete_source_integrity_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Finish source validation and atomically queue text extraction."""
        job = self._running_job(job_id)
        if job.job_type != self.SOURCE_INTEGRITY_JOB_TYPE:
            raise ProcessingJobStateError()
        timestamp = now or self._now()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.finished_at = timestamp
        job.error_message = None
        extraction_job = self._create_queued_job(
            document_id=job.document_id,
            job_type=self.TEXT_EXTRACTION_JOB_TYPE,
            timestamp=timestamp,
        )
        self._commit()
        return extraction_job

    def fail_job(self, *, job_id: int, safe_error: str, now: datetime | None = None) -> ProcessingJob:
        error = self._safe_error(safe_error)
        job = self._running_job(job_id)
        timestamp = now or self._now()
        job.status = ProcessingJobStatus.FAILED
        job.error_message = error
        job.finished_at = timestamp
        job.document.status = DocumentStatus.FAILED
        job.document.processing_error = error
        self._commit()
        return job

    def retry_failed_job(self, *, document_id: int, job_id: int, now: datetime | None = None) -> ProcessingJob:
        job = self.get_document_job(document_id=document_id, job_id=job_id)
        if job.status != ProcessingJobStatus.FAILED:
            raise ProcessingJobStateError()
        timestamp = now or self._now()
        job.status = ProcessingJobStatus.QUEUED
        job.queued_at = timestamp
        job.started_at = job.finished_at = job.cancelled_at = None
        job.error_message = job.broker_task_id = None
        job.document.status = DocumentStatus.PENDING
        job.document.processing_error = None
        self.outbox_events.create(ProcessingOutboxEvent(processing_job_id=job.id, event_type=self.EVENT_TYPE, payload={"processing_job_id": job.id}, available_at=timestamp))
        self._commit()
        return job

    def cancel_document_jobs(self, *, document_id: int, now: datetime | None = None) -> int:
        if self.documents.get_active_by_id(document_id) is None:
            raise DocumentNotFoundError()
        cancelled = self.jobs.cancel_nonterminal_for_document(document_id=document_id, now=now or self._now())
        self.outbox_events.cancel_nonterminal_for_document(document_id=document_id)
        return cancelled

    def _running_job(self, job_id: int) -> ProcessingJob:
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        if job.status != ProcessingJobStatus.RUNNING:
            raise ProcessingJobStateError()
        return job

    def _create_queued_job(
        self,
        *,
        document_id: int,
        job_type: str,
        timestamp: datetime,
    ) -> ProcessingJob:
        job = self.jobs.create(
            ProcessingJob(
                document_id=document_id,
                job_type=job_type,
                queued_at=timestamp,
            )
        )
        self.outbox_events.create(
            ProcessingOutboxEvent(
                processing_job_id=job.id,
                event_type=self.EVENT_TYPE,
                payload={"processing_job_id": job.id},
                available_at=timestamp,
            )
        )
        return job

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception as error:
            self.db.rollback()
            raise ProcessingJobPersistenceError() from error

    @staticmethod
    def _safe_error(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 1000:
            raise ProcessingJobStateError()
        return value.strip()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
