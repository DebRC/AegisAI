"""Persistence boundary for durable derived-vector cleanup requests."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vector_cleanup_request import VectorCleanupRequest


class VectorCleanupRequestRepository:
    """Read and complete cleanup requests without owning transactions."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, request: VectorCleanupRequest) -> VectorCleanupRequest:
        self.db.add(request)
        self.db.flush()
        self.db.refresh(request)
        return request

    def get_by_processing_job_id(self, processing_job_id: int) -> VectorCleanupRequest | None:
        return self.db.scalar(
            select(VectorCleanupRequest).where(
                VectorCleanupRequest.processing_job_id == processing_job_id
            )
        )

    def mark_completed(self, *, processing_job_id: int, completed_at: datetime) -> bool:
        request = self.get_by_processing_job_id(processing_job_id)
        if request is None:
            return False
        request.completed_at = completed_at
        self.db.flush()
        return True
