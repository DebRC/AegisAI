"""Read-only, validated access to the immutable audit trail."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AuditEventValidationError
from app.models.audit_event import AuditEvent
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.repositories.audit_event_repository import AuditEventRepository


@dataclass(frozen=True)
class AuditEventPage:
    items: list[AuditEvent]
    offset: int
    limit: int
    total: int


class AuditQueryService:
    """Expose bounded, allow-listed audit filters without mutation methods."""

    _TARGET_TYPES = frozenset({"document", "document_access_grant", "permission", "role", "session", "user", "api_key", "retention_policy"})

    def __init__(self, db: Session):
        self.events = AuditEventRepository(db)

    def list_events(
        self,
        *,
        offset: int,
        limit: int,
        actor_user_id: int | None = None,
        event_type: AuditEventType | None = None,
        outcome: AuditEventOutcome | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        tenant_id: int | None = None,
    ) -> AuditEventPage:
        self._validate(
            offset=offset,
            limit=limit,
            actor_user_id=actor_user_id,
            event_type=event_type,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
        filters = {
            "actor_user_id": actor_user_id,
            "event_type": event_type.value if event_type else None,
            "outcome": outcome.value if outcome else None,
            "target_type": target_type,
            "target_id": target_id,
            "occurred_after": occurred_after,
            "occurred_before": occurred_before,
            "tenant_id": tenant_id,
        }
        return AuditEventPage(
            items=self.events.list_events(offset=offset, limit=limit, **filters),
            offset=offset,
            limit=limit,
            total=self.events.count_events(**filters),
        )

    def _validate(self, **filters: object) -> None:
        offset = filters["offset"]
        limit = filters["limit"]
        actor_user_id = filters["actor_user_id"]
        target_type = filters["target_type"]
        target_id = filters["target_id"]
        occurred_after = filters["occurred_after"]
        occurred_before = filters["occurred_before"]
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise AuditEventValidationError()
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise AuditEventValidationError()
        for value in (actor_user_id, target_id):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                raise AuditEventValidationError()
        if target_type is not None and target_type not in self._TARGET_TYPES:
            raise AuditEventValidationError()
        if target_id is not None and target_type is None:
            raise AuditEventValidationError()
        if occurred_after is not None and not isinstance(occurred_after, datetime):
            raise AuditEventValidationError()
        if occurred_before is not None and not isinstance(occurred_before, datetime):
            raise AuditEventValidationError()
        if occurred_after is not None and occurred_before is not None and occurred_after > occurred_before:
            raise AuditEventValidationError()
