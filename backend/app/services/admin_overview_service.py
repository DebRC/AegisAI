"""Bounded aggregate data for the administrator operational overview."""

from dataclasses import dataclass
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.audit_event import AuditEvent
from app.models.document import Document, DocumentStatus
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.user import User

@dataclass(frozen=True)
class AdminOverview:
    total_users: int
    active_users: int
    documents_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    recent_events: list[AuditEvent]

class AdminOverviewService:
    def __init__(self, db: Session): self.db = db
    def get_overview(self) -> AdminOverview:
        document_counts = dict(self.db.execute(select(Document.status, func.count(Document.id)).where(Document.deleted_at.is_(None)).group_by(Document.status)).all())
        job_counts = dict(self.db.execute(select(ProcessingJob.status, func.count(ProcessingJob.id)).group_by(ProcessingJob.status)).all())
        return AdminOverview(
            total_users=self.db.scalar(select(func.count(User.id))) or 0,
            active_users=self.db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0,
            documents_by_status={state.value: document_counts.get(state, 0) for state in DocumentStatus},
            jobs_by_status={state.value: job_counts.get(state, 0) for state in ProcessingJobStatus},
            recent_events=list(self.db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(20))),
        )
