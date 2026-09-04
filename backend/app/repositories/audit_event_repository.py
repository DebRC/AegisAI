"""Append-only persistence boundary for audit events."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy import select
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

    def list_events(
        self,
        *,
        actor_user_id: int | None,
        event_type: str | None,
        outcome: str | None,
        target_type: str | None,
        target_id: int | None,
        occurred_after: datetime | None,
        occurred_before: datetime | None,
        offset: int,
        limit: int,
        tenant_id: int | None = None,
    ) -> list[AuditEvent]:
        statement = self._filtered_statement(
            actor_user_id=actor_user_id,
            event_type=event_type,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            tenant_id=tenant_id,
        ).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        return list(self.db.scalars(statement.offset(offset).limit(limit)))

    def count_events(self, **filters: object) -> int:
        statement = self._filtered_statement(**filters)
        return self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0

    @staticmethod
    def _filtered_statement(
        *,
        actor_user_id: int | None,
        event_type: str | None,
        outcome: str | None,
        target_type: str | None,
        target_id: int | None,
        occurred_after: datetime | None,
        occurred_before: datetime | None,
        tenant_id: int | None = None,
    ):
        statement = select(AuditEvent)
        if tenant_id is not None:
            statement = statement.where(AuditEvent.tenant_id.in_((tenant_id, None)))
        if actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
        if event_type is not None:
            statement = statement.where(AuditEvent.event_type == event_type)
        if outcome is not None:
            statement = statement.where(AuditEvent.outcome == outcome)
        if target_type is not None:
            statement = statement.where(AuditEvent.target_type == target_type)
        if target_id is not None:
            statement = statement.where(AuditEvent.target_id == target_id)
        if occurred_after is not None:
            statement = statement.where(AuditEvent.occurred_at >= occurred_after)
        if occurred_before is not None:
            statement = statement.where(AuditEvent.occurred_at <= occurred_before)
        return statement
