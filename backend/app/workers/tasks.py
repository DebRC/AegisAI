"""Celery tasks for durable document-processing jobs."""

import hashlib

from app.core.exceptions import ProcessingJobStateError
from app.core.config import settings
from app.db.database import SessionLocal
from app.embeddings.factory import create_embedding_provider
from app.extraction.processing import TextChunker
from app.extraction.processing import TextNormalizer
from app.extraction.registry import TextExtractorRegistry
from app.models.document import Document
from app.services.processing_job_service import ProcessingJobService
from app.services.processing_job_dispatcher import ProcessingJobDispatcher
from app.services.embedding_indexing_service import EmbeddingIndexingService
from app.services.vector_cleanup_service import VectorCleanupService
from app.services.retention_service import RetentionService
from app.services.text_extraction_service import TextExtractionService
from app.integrations.vector_store.qdrant_client import create_qdrant_client
from app.integrations.vector_store.qdrant_store import QdrantVectorStore
from app.storage.documents import DocumentStorageError, LocalDocumentStorage
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_source_integrity_check")
def run_source_integrity_check(processing_job_id: int) -> dict[str, str]:
    """Verify stored source bytes without advancing the document to READY."""
    db = SessionLocal()
    try:
        service = ProcessingJobService(db)
        claim = service.claim_job(
            job_id=processing_job_id,
            expected_job_type=ProcessingJobService.SOURCE_INTEGRITY_JOB_TYPE,
        )
        if not claim.claimed:
            return {"status": claim.job.status.value}

        document = db.get(Document, claim.job.document_id)
        if document is None or document.deleted_at is not None:
            return {"status": "cancelled"}

        storage = LocalDocumentStorage(
            settings.DOCUMENT_STORAGE_PATH,
            settings.DOCUMENT_MAX_UPLOAD_BYTES,
        )
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            for chunk in storage.iter_chunks(document.storage_key):
                size_bytes += len(chunk)
                digest.update(chunk)
        except DocumentStorageError:
            service.fail_job(
                job_id=processing_job_id,
                safe_error="The stored source document could not be read.",
            )
            return {"status": "failed"}

        if size_bytes != document.size_bytes or digest.hexdigest() != document.sha256:
            service.fail_job(
                job_id=processing_job_id,
                safe_error="The stored source document failed its integrity check.",
            )
            return {"status": "failed"}

        try:
            service.complete_source_integrity_job(job_id=processing_job_id)
        except ProcessingJobStateError:
            return {"status": "cancelled"}
        return {"status": "succeeded"}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_text_extraction")
def run_text_extraction(processing_job_id: int) -> dict[str, str]:
    """Extract, normalize, chunk, and persist one document outside HTTP."""
    db = SessionLocal()
    try:
        service = TextExtractionService(
            db,
            LocalDocumentStorage(
                settings.DOCUMENT_STORAGE_PATH,
                settings.DOCUMENT_MAX_UPLOAD_BYTES,
            ),
            TextExtractorRegistry(settings.DOCUMENT_MAX_EXTRACTED_TEXT_CHARACTERS),
            TextNormalizer(),
            TextChunker(
                settings.DOCUMENT_CHUNK_TARGET_CHARACTERS,
                settings.DOCUMENT_CHUNK_OVERLAP_CHARACTERS,
            ),
            settings.DOCUMENT_MAX_EXTRACTED_TEXT_CHARACTERS,
        )
        return {"status": service.process(processing_job_id)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_embedding_indexing")
def run_embedding_indexing(processing_job_id: int) -> dict[str, str]:
    """Generate and persist derived vectors for one current document extraction."""
    db = SessionLocal()
    try:
        service = EmbeddingIndexingService(
            db,
            settings,
            create_provider=lambda: create_embedding_provider(settings),
            create_vector_store=lambda: QdrantVectorStore(
                create_qdrant_client(settings),
                settings,
            ),
        )
        return {"status": service.process(processing_job_id)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_vector_cleanup")
def run_vector_cleanup(processing_job_id: int) -> dict[str, str]:
    """Remove obsolete derived points through a durable cleanup request."""
    db = SessionLocal()
    try:
        service = VectorCleanupService(
            db,
            create_vector_store=lambda collection_name: QdrantVectorStore(
                create_qdrant_client(settings),
                settings,
                collection_name=collection_name,
            ),
        )
        return {"status": service.process(processing_job_id)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.dispatch_processing_outbox")
def dispatch_processing_outbox() -> dict[str, int]:
    """Publish a bounded batch of durable jobs from PostgreSQL to Redis."""
    db = SessionLocal()
    try:
        dispatcher = ProcessingJobDispatcher(
            db,
            publish_job=_publish_processing_job,
        )
        summary = dispatcher.dispatch_pending()
        return {"published": summary.published, "deferred": summary.deferred}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_retention_sweep")
def run_retention_sweep() -> dict[str, int]:
    """Apply enabled tenant retention policies outside an HTTP request."""
    db = SessionLocal()
    try:
        service = RetentionService(
            db,
            LocalDocumentStorage(
                settings.DOCUMENT_STORAGE_PATH,
                settings.DOCUMENT_MAX_UPLOAD_BYTES,
            ),
        )
        return {"purged_count": service.sweep_all_tenants()}
    finally:
        db.close()


def _publish_processing_job(job_type: str, processing_job_id: int) -> str:
    """Route each supported durable pipeline stage to its Celery task."""
    if job_type == ProcessingJobService.SOURCE_INTEGRITY_JOB_TYPE:
        return run_source_integrity_check.delay(processing_job_id).id
    if job_type == ProcessingJobService.TEXT_EXTRACTION_JOB_TYPE:
        return run_text_extraction.delay(processing_job_id).id
    if job_type == ProcessingJobService.EMBEDDING_INDEXING_JOB_TYPE:
        return run_embedding_indexing.delay(processing_job_id).id
    if job_type == ProcessingJobService.VECTOR_CLEANUP_JOB_TYPE:
        return run_vector_cleanup.delay(processing_job_id).id
    raise ValueError("No worker task is registered for this processing job type")
