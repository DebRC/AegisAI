"""Safe, read-only audit API representations."""

from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType


class AuditEventResponse(BaseModel):
    id: int
    actor_user_id: int | None
    event_type: AuditEventType
    outcome: AuditEventOutcome
    occurred_at: datetime
    target_type: str | None
    target_id: int | None
    metadata: dict[str, str | int | float | bool | None] = Field(validation_alias="metadata_")

    model_config = ConfigDict(from_attributes=True)


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    offset: int
    limit: int
    total: int
