from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.core.exceptions import ProcessingJobNotFoundError
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services.processing_job_service import ProcessingJobService

@dataclass(frozen=True)
class AdminJobPage:
    items: list[ProcessingJob]
    offset: int
    limit: int
    total: int

class AdminProcessingJobService:
    def __init__(self, db: Session):
        self.jobs = ProcessingJobRepository(db)
        self.processing = ProcessingJobService(db)
    def list_jobs(self, *, offset: int, limit: int, status: ProcessingJobStatus | None) -> AdminJobPage:
        if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Invalid page")
        return AdminJobPage(self.jobs.list_for_administration(offset=offset, limit=limit, status=status), offset, limit, self.jobs.count_for_administration(status=status))
    def get_job(self, job_id: int) -> ProcessingJob:
        job = self.jobs.get_by_id(job_id)
        if job is None: raise ProcessingJobNotFoundError()
        return job
    def retry_job(self, job_id: int) -> ProcessingJob:
        job = self.get_job(job_id)
        return self.processing.retry_failed_job(document_id=job.document_id, job_id=job.id)
    def cancel_job(self, job_id: int) -> ProcessingJob:
        return self.processing.cancel_running_job(job_id=job_id)
