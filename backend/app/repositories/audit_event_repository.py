"""Append-only persistence boundary for audit events."""

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


class AuditEventRepository:
    """Create audit records without owning the surrounding transaction."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, event: AuditEvent) -> AuditEvent:
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event
