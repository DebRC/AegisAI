"""Worker-facing orchestration for durable deletion of obsolete Qdrant points."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.integrations.vector_store.exceptions import VectorStoreOperationError
from app.integrations.vector_store.qdrant_store import QdrantVectorStore
from app.services.processing_job_service import ProcessingJobService


VectorStoreFactory = Callable[[str], QdrantVectorStore]


class VectorCleanupService:
    """Claim and delete one collection-scoped cleanup request idempotently."""

    def __init__(self, db: Session, create_vector_store: VectorStoreFactory) -> None:
        self.jobs = ProcessingJobService(db)
        self.create_vector_store = create_vector_store

    def process(self, processing_job_id: int) -> str:
        """Delete known stale point IDs, including after source soft deletion."""
        claim = self.jobs.claim_vector_cleanup_job(job_id=processing_job_id)
        if not claim.claimed:
            return claim.job.status.value
        try:
            request = self.jobs.get_vector_cleanup_request(job_id=processing_job_id)
            vector_store = self.create_vector_store(request.collection_name)
        except Exception:
            return self._fail(processing_job_id)

        try:
            vector_store.delete_points(request.point_ids)
            self.jobs.complete_vector_cleanup_job(job_id=processing_job_id)
        except VectorStoreOperationError:
            return self._fail(processing_job_id)
        except Exception:
            return self._fail(processing_job_id)
        finally:
            vector_store.close()
        return "succeeded"

    def _fail(self, processing_job_id: int) -> str:
        try:
            self.jobs.fail_vector_cleanup_job(
                job_id=processing_job_id,
                safe_error="Document vectors could not be removed.",
            )
        except Exception:
            return "cancelled"
        return "failed"
