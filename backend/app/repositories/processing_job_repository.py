from datetime import datetime

from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.processing_job import ProcessingJob
from app.models.processing_job import ProcessingJobStatus


class ProcessingJobRepository:
    """Database operations for processing jobs without transaction ownership."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, job: ProcessingJob) -> ProcessingJob:
        self.db.add(job)
        self.db.flush()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: int) -> ProcessingJob | None:
        return self.db.scalar(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )

    def get_by_document_and_id(
        self,
        *,
        document_id: int,
        job_id: int,
    ) -> ProcessingJob | None:
        return self.db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.id == job_id,
                ProcessingJob.document_id == document_id,
            )
        )

    def list_by_document_id(self, document_id: int) -> list[ProcessingJob]:
        return list(
            self.db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
            )
        )

    def has_nonterminal_for_document_and_type(
        self,
        *,
        document_id: int,
        job_type: str,
    ) -> bool:
        return self.db.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == job_type,
                ProcessingJob.status.in_(
                    [ProcessingJobStatus.QUEUED, ProcessingJobStatus.RUNNING]
                ),
            )
            .limit(1)
        ) is not None

    def claim_queued(
        self,
        *,
        job_id: int,
        now: datetime,
        expected_job_type: str | None = None,
    ) -> bool:
        """Atomically claim a queued job; duplicate workers receive ``False``."""
        conditions = [
            ProcessingJob.id == job_id,
            ProcessingJob.status == ProcessingJobStatus.QUEUED,
        ]
        if expected_job_type is not None:
            conditions.append(ProcessingJob.job_type == expected_job_type)
        result = self.db.execute(
            update(ProcessingJob)
            .where(*conditions)
            .values(
                status=ProcessingJobStatus.RUNNING,
                attempt_count=ProcessingJob.attempt_count + 1,
                started_at=now,
                finished_at=None,
                cancelled_at=None,
                error_message=None,
            )
        )
        return result.rowcount == 1

    def cancel_nonterminal_for_document(self, *, document_id: int, now: datetime) -> int:
        """Cancel queued or running jobs before a document's bytes are removed."""
        result = self.db.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.status.in_(
                    [ProcessingJobStatus.QUEUED, ProcessingJobStatus.RUNNING]
                ),
            )
            .values(
                status=ProcessingJobStatus.CANCELLED,
                cancelled_at=now,
                finished_at=now,
                error_message=None,
            )
        )
        return result.rowcount or 0

    def has_nonterminal_for_document_and_types(
        self,
        *,
        document_id: int,
        job_types: list[str],
    ) -> bool:
        return self.db.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type.in_(job_types),
                ProcessingJob.status.in_(
                    [ProcessingJobStatus.QUEUED, ProcessingJobStatus.RUNNING]
                ),
            )
            .limit(1)
        ) is not None

    def update(self) -> None:
        self.db.flush()
