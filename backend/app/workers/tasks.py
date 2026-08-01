"""Celery tasks for durable document-processing jobs."""

import hashlib

from app.core.exceptions import ProcessingJobStateError
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.services.processing_job_service import ProcessingJobService
from app.storage.documents import DocumentStorageError, LocalDocumentStorage
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_source_integrity_check")
def run_source_integrity_check(processing_job_id: int) -> dict[str, str]:
    """Verify stored source bytes without advancing the document to READY."""
    db = SessionLocal()
    try:
        service = ProcessingJobService(db)
        claim = service.claim_job(job_id=processing_job_id)
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
            service.complete_job(job_id=processing_job_id)
        except ProcessingJobStateError:
            return {"status": "cancelled"}
        return {"status": "succeeded"}
    finally:
        db.close()
