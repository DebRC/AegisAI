"""Read-only, payload-safe visibility into a document's current vector state."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DocumentNotFoundError
from app.models.processing_job import ProcessingJobStatus
from app.repositories.document_chunk_embedding_repository import DocumentChunkEmbeddingRepository
from app.repositories.document_extraction_repository import DocumentExtractionRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services.processing_job_service import ProcessingJobService


IndexingStatus = Literal["not_started", "queued", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class DocumentEmbeddingStatus:
    """Safe summary; no vector payload, Qdrant identity, or broker information."""

    document_id: int
    total_chunks: int
    indexed_chunks: int
    indexing_status: IndexingStatus
    indexing_attempt_count: int
    indexing_error: str | None
    cleanup_pending_count: int


class DocumentEmbeddingStatusService:
    """Calculate current vector progress from PostgreSQL's authoritative records."""

    def __init__(self, db: Session, configuration: Settings):
        self.configuration = configuration
        self.documents = DocumentRepository(db)
        self.extractions = DocumentExtractionRepository(db)
        self.embeddings = DocumentChunkEmbeddingRepository(db)
        self.jobs = ProcessingJobRepository(db)

    def get_status(self, document_id: int) -> DocumentEmbeddingStatus:
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        extraction = self.extractions.get_by_document_id(document_id)
        total_chunks = len(extraction.chunks) if extraction is not None else 0
        latest_job = self.jobs.get_latest_by_document_and_type(
            document_id=document_id,
            job_type=ProcessingJobService.EMBEDDING_INDEXING_JOB_TYPE,
        )
        return DocumentEmbeddingStatus(
            document_id=document_id,
            total_chunks=total_chunks,
            indexed_chunks=self.embeddings.count_current_chunks_by_document_id(
                document_id=document_id,
                provider=self.configuration.EMBEDDING_PROVIDER,
                model=self.configuration.EMBEDDING_MODEL,
                collection_name=self.configuration.QDRANT_COLLECTION_NAME,
            ),
            indexing_status=(latest_job.status.value if latest_job is not None else "not_started"),
            indexing_attempt_count=latest_job.attempt_count if latest_job is not None else 0,
            indexing_error=latest_job.error_message if latest_job is not None else None,
            cleanup_pending_count=self.jobs.count_nonterminal_for_document_and_type(
                document_id=document_id,
                job_type=ProcessingJobService.VECTOR_CLEANUP_JOB_TYPE,
            ),
        )
