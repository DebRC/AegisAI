from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from sqlalchemy.orm import Session

from app.extraction.processing import NormalizedText
from app.extraction.processing import TextChunk
from app.core.exceptions import DocumentNotFoundError, ProcessingJobNotFoundError, ProcessingJobPersistenceError, ProcessingJobStateError
from app.models.document import DocumentStatus
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentExtraction
from app.models.document_extraction import DocumentChunkEmbedding
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.processing_outbox_event import ProcessingOutboxEvent
from app.models.vector_cleanup_request import VectorCleanupRequest
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_chunk_embedding_repository import DocumentChunkEmbeddingRepository
from app.repositories.document_extraction_repository import DocumentExtractionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.processing_outbox_event_repository import ProcessingOutboxEventRepository
from app.repositories.vector_cleanup_request_repository import VectorCleanupRequestRepository
from app.services.audit_event_service import AuditEventService


@dataclass(frozen=True)
class JobClaim:
    job: ProcessingJob
    claimed: bool


class ProcessingJobService:
    """Coordinate durable job and outbox state with explicit transactions."""

    SOURCE_INTEGRITY_JOB_TYPE = "source_integrity"
    TEXT_EXTRACTION_JOB_TYPE = "text_extraction"
    EMBEDDING_INDEXING_JOB_TYPE = "embedding_indexing"
    VECTOR_CLEANUP_JOB_TYPE = "vector_cleanup"
    EVENT_TYPE = "processing_job.queued"
    EXTRACTION_VERSION = "phase8-v1"

    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.extractions = DocumentExtractionRepository(db)
        self.embeddings = DocumentChunkEmbeddingRepository(db)
        self.jobs = ProcessingJobRepository(db)
        self.outbox_events = ProcessingOutboxEventRepository(db)
        self.vector_cleanup_requests = VectorCleanupRequestRepository(db)
        self.audit_events = AuditEventService(db)

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

    def create_embedding_indexing_job(self, *, document_id: int, now: datetime | None = None) -> ProcessingJob:
        """Create the durable vector-index stage after a successful extraction."""
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return self._create_queued_job(
            document_id=document.id,
            job_type=self.EMBEDDING_INDEXING_JOB_TYPE,
            timestamp=now or self._now(),
        )

    def request_text_reprocessing(
        self,
        *,
        document_id: int,
        actor_user_id: int | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Queue one replacement extraction while retaining current output."""
        document = self.documents.get_active_by_id_for_update(document_id)
        if document is None:
            raise DocumentNotFoundError()
        if (
            document.status != DocumentStatus.READY
            or self.jobs.has_nonterminal_for_document_and_type(
                document_id=document_id,
                job_type=self.TEXT_EXTRACTION_JOB_TYPE,
            )
            or self.jobs.has_nonterminal_for_document_and_types(
                document_id=document_id,
                job_types=[self.EMBEDDING_INDEXING_JOB_TYPE, self.VECTOR_CLEANUP_JOB_TYPE],
            )
        ):
            raise ProcessingJobStateError()
        try:
            job = self._create_queued_job(
                document_id=document.id,
                job_type=self.TEXT_EXTRACTION_JOB_TYPE,
                timestamp=now or self._now(),
            )
            self.audit_events.record(
                event_type=AuditEventType.DOCUMENT_REPROCESS_QUEUED,
                outcome=AuditEventOutcome.SUCCEEDED,
                actor_user_id=actor_user_id,
                target_type="document",
                target_id=document.id,
                tenant_id=document.tenant_id,
            )
            self._commit()
            return job
        except ProcessingJobPersistenceError:
            raise
        except Exception as error:
            self.db.rollback()
            raise ProcessingJobPersistenceError() from error

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

    def claim_text_extraction_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> JobClaim:
        """Claim extraction work and mark its active document as processing."""
        timestamp = now or self._now()
        claimed = self.jobs.claim_queued(
            job_id=job_id,
            now=timestamp,
            expected_job_type=self.TEXT_EXTRACTION_JOB_TYPE,
        )
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        if not claimed:
            return JobClaim(job=job, claimed=False)
        if job.document.deleted_at is not None:
            self._cancel_running_job(job, timestamp)
            self._commit()
            return JobClaim(job=job, claimed=False)
        job.document.status = DocumentStatus.PROCESSING
        job.document.processing_error = None
        self._commit()
        return JobClaim(job=job, claimed=True)

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

    def complete_text_extraction_job(
        self,
        *,
        job_id: int,
        normalized_text: NormalizedText,
        chunks: list[TextChunk],
        now: datetime | None = None,
    ) -> DocumentExtraction:
        """Persist complete output and advance job/document readiness together."""
        job = self._running_job(job_id)
        if job.job_type != self.TEXT_EXTRACTION_JOB_TYPE or not chunks:
            raise ProcessingJobStateError()
        if job.document.deleted_at is not None:
            raise ProcessingJobStateError()
        timestamp = now or self._now()
        extraction = DocumentExtraction(
            document_id=job.document_id,
            normalized_text=normalized_text.text,
            text_sha256=hashlib.sha256(normalized_text.text.encode()).hexdigest(),
            character_count=len(normalized_text.text),
            extractor_version=self.EXTRACTION_VERSION,
            extracted_at=timestamp,
            chunks=[
                DocumentChunk(
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    content_sha256=hashlib.sha256(chunk.content.encode()).hexdigest(),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    source_locations=(
                        [
                            {"kind": location.kind, "index": location.index}
                            for location in chunk.source_locations
                        ]
                        or None
                    ),
                )
                for chunk in chunks
            ],
        )
        try:
            stale_embeddings = self.embeddings.list_by_document_id(job.document_id)
            persisted = self.extractions.replace(extraction)
            job.status = ProcessingJobStatus.SUCCEEDED
            job.finished_at = timestamp
            job.error_message = None
            job.document.status = DocumentStatus.READY
            job.document.processing_error = None
            self._create_queued_job(
                document_id=job.document_id,
                job_type=self.EMBEDDING_INDEXING_JOB_TYPE,
                timestamp=timestamp,
            )
            self._create_vector_cleanup_jobs(
                document_id=job.document_id,
                embeddings=stale_embeddings,
                timestamp=timestamp,
            )
            self._commit()
            return persisted
        except ProcessingJobPersistenceError:
            raise
        except Exception as error:
            self.db.rollback()
            raise ProcessingJobPersistenceError() from error

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

    def claim_embedding_indexing_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> JobClaim:
        """Claim derived indexing work without changing text-extraction readiness."""
        timestamp = now or self._now()
        claimed = self.jobs.claim_queued(
            job_id=job_id,
            now=timestamp,
            expected_job_type=self.EMBEDDING_INDEXING_JOB_TYPE,
        )
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        if not claimed:
            return JobClaim(job=job, claimed=False)
        if job.document.deleted_at is not None:
            self._cancel_running_job(job, timestamp)
            self._commit()
            return JobClaim(job=job, claimed=False)
        self._commit()
        return JobClaim(job=job, claimed=True)

    def complete_embedding_indexing_job(
        self,
        *,
        job_id: int,
        document_extraction_id: int,
        embeddings: list[DocumentChunkEmbedding],
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Persist derived-point pointers and finish an indexing job atomically."""
        job = self._running_job(job_id)
        if job.job_type != self.EMBEDDING_INDEXING_JOB_TYPE or not embeddings:
            raise ProcessingJobStateError()
        if job.document.deleted_at is not None:
            raise ProcessingJobStateError()
        extraction = self.extractions.get_by_document_id(job.document_id)
        if extraction is None or extraction.id != document_extraction_id:
            raise ProcessingJobStateError()
        current_chunks = {chunk.id: chunk for chunk in extraction.chunks}
        if len(current_chunks) != len(embeddings):
            raise ProcessingJobStateError()
        for embedding in embeddings:
            chunk = current_chunks.get(embedding.document_chunk_id)
            if chunk is None or embedding.content_sha256 != chunk.content_sha256:
                raise ProcessingJobStateError()
        try:
            self.embeddings.upsert_many(embeddings)
            job.status = ProcessingJobStatus.SUCCEEDED
            job.finished_at = now or self._now()
            job.error_message = None
            self._commit()
            return job
        except ProcessingJobPersistenceError:
            raise
        except Exception as error:
            self.db.rollback()
            raise ProcessingJobPersistenceError() from error

    def fail_embedding_indexing_job(
        self,
        *,
        job_id: int,
        safe_error: str,
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Fail derived indexing while keeping current extracted text READY."""
        error = self._safe_error(safe_error)
        job = self._running_job(job_id)
        if job.job_type != self.EMBEDDING_INDEXING_JOB_TYPE:
            raise ProcessingJobStateError()
        job.status = ProcessingJobStatus.FAILED
        job.error_message = error
        job.finished_at = now or self._now()
        self._commit()
        return job

    def claim_vector_cleanup_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> JobClaim:
        """Claim cleanup even after a document has been soft deleted."""
        claimed = self.jobs.claim_queued(
            job_id=job_id,
            now=now or self._now(),
            expected_job_type=self.VECTOR_CLEANUP_JOB_TYPE,
        )
        job = self.jobs.get_by_id(job_id)
        if job is None:
            raise ProcessingJobNotFoundError()
        if claimed:
            self._commit()
        return JobClaim(job=job, claimed=claimed)

    def get_vector_cleanup_request(self, *, job_id: int) -> VectorCleanupRequest:
        request = self.vector_cleanup_requests.get_by_processing_job_id(job_id)
        if request is None:
            raise ProcessingJobStateError()
        return request

    def complete_vector_cleanup_job(
        self,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Mark a point-deletion request and its durable job complete together."""
        job = self._running_job(job_id)
        if job.job_type != self.VECTOR_CLEANUP_JOB_TYPE:
            raise ProcessingJobStateError()
        timestamp = now or self._now()
        if not self.vector_cleanup_requests.mark_completed(
            processing_job_id=job_id,
            completed_at=timestamp,
        ):
            raise ProcessingJobStateError()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.finished_at = timestamp
        job.error_message = None
        self._commit()
        return job

    def fail_vector_cleanup_job(
        self,
        *,
        job_id: int,
        safe_error: str,
        now: datetime | None = None,
    ) -> ProcessingJob:
        """Fail derived cleanup without changing the deleted/ready document state."""
        error = self._safe_error(safe_error)
        job = self._running_job(job_id)
        if job.job_type != self.VECTOR_CLEANUP_JOB_TYPE:
            raise ProcessingJobStateError()
        job.status = ProcessingJobStatus.FAILED
        job.error_message = error
        job.finished_at = now or self._now()
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
        if job.job_type not in {
            self.EMBEDDING_INDEXING_JOB_TYPE,
            self.VECTOR_CLEANUP_JOB_TYPE,
        }:
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

    def cancel_running_job(self, *, job_id: int, now: datetime | None = None) -> ProcessingJob:
        """Cancel a claimed job when a late worker observes deleted content."""
        job = self._running_job(job_id)
        self._cancel_running_job(job, now or self._now())
        self._commit()
        return job

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

    def _create_vector_cleanup_jobs(
        self,
        *,
        document_id: int,
        embeddings: list[DocumentChunkEmbedding],
        timestamp: datetime,
    ) -> list[ProcessingJob]:
        """Queue one collection-scoped cleanup request for obsolete point IDs."""
        point_ids_by_collection: dict[str, list[str]] = {}
        for embedding in embeddings:
            point_ids_by_collection.setdefault(embedding.collection_name, []).append(embedding.point_id)

        jobs: list[ProcessingJob] = []
        for collection_name, point_ids in point_ids_by_collection.items():
            cleanup_job = self._create_queued_job(
                document_id=document_id,
                job_type=self.VECTOR_CLEANUP_JOB_TYPE,
                timestamp=timestamp,
            )
            self.vector_cleanup_requests.create(
                VectorCleanupRequest(
                    processing_job_id=cleanup_job.id,
                    collection_name=collection_name,
                    point_ids=sorted(set(point_ids)),
                )
            )
            jobs.append(cleanup_job)
        return jobs

    def queue_vector_cleanup_for_document(
        self,
        *,
        document_id: int,
        now: datetime | None = None,
    ) -> list[ProcessingJob]:
        """Capture current point IDs before a document service removes its extraction."""
        if self.documents.get_active_by_id(document_id) is None:
            raise DocumentNotFoundError()
        return self._create_vector_cleanup_jobs(
            document_id=document_id,
            embeddings=self.embeddings.list_by_document_id(document_id),
            timestamp=now or self._now(),
        )

    @staticmethod
    def _cancel_running_job(job: ProcessingJob, timestamp: datetime) -> None:
        job.status = ProcessingJobStatus.CANCELLED
        job.cancelled_at = timestamp
        job.finished_at = timestamp
        job.error_message = None

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
