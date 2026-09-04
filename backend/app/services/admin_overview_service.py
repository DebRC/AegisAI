"""Bounded aggregate data for the administrator operational overview."""

from dataclasses import dataclass
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.audit_event import AuditEvent
from app.models.document import Document, DocumentStatus
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.user import User
from app.models.tenant import TenantMembership

@dataclass(frozen=True)
class AdminOverview:
    total_users: int
    active_users: int
    documents_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    recent_events: list[AuditEvent]

class AdminOverviewService:
    def __init__(self, db: Session): self.db = db
    def get_overview(self, *, tenant_id: int | None = None) -> AdminOverview:
        document_statement = select(Document.status, func.count(Document.id)).where(Document.deleted_at.is_(None))
        if tenant_id is not None:
            document_statement = document_statement.where(Document.tenant_id == tenant_id)
        document_counts = dict(self.db.execute(document_statement.group_by(Document.status)).all())
        job_statement = select(ProcessingJob.status, func.count(ProcessingJob.id))
        if tenant_id is not None:
            job_statement = job_statement.join(Document).where(Document.tenant_id == tenant_id)
        job_counts = dict(self.db.execute(job_statement.group_by(ProcessingJob.status)).all())
        users_statement = select(func.count(User.id))
        active_users_statement = select(func.count(User.id)).where(User.is_active.is_(True))
        events_statement = select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(20)
        if tenant_id is not None:
            users_statement = users_statement.join(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
            active_users_statement = active_users_statement.join(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.is_active.is_(True))
            events_statement = events_statement.where(AuditEvent.tenant_id == tenant_id)
        return AdminOverview(
            total_users=self.db.scalar(users_statement) or 0,
            active_users=self.db.scalar(active_users_statement) or 0,
            documents_by_status={state.value: document_counts.get(state, 0) for state in DocumentStatus},
            jobs_by_status={state.value: job_counts.get(state, 0) for state in ProcessingJobStatus},
            recent_events=list(self.db.scalars(events_statement)),
        )
