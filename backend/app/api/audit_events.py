"""Administrator-only read access to the append-only audit trail."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from app.api.dependencies import get_audit_query_service
from app.core.exceptions import AuditEventValidationError
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.schemas.audit import AuditEventListResponse
from app.security.dependencies import require_permission
from app.security.dependencies import TenantContext, get_current_tenant_context
from app.security.permissions import PermissionCode
from app.services.audit_query_service import AuditQueryService


router = APIRouter(prefix="/audit-events", tags=["Audit events"])
_TARGET_TYPES = Literal["document", "document_access_grant", "permission", "role", "session", "user", "api_key", "retention_policy"]


@router.get("", response_model=AuditEventListResponse)
def list_audit_events(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    actor_user_id: int | None = Query(default=None, ge=1),
    event_type: AuditEventType | None = None,
    outcome: AuditEventOutcome | None = None,
    target_type: _TARGET_TYPES | None = None,
    target_id: int | None = Query(default=None, ge=1),
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    service: AuditQueryService = Depends(get_audit_query_service),
    _: object = Depends(require_permission(PermissionCode.AUDIT_READ)),
    context: TenantContext | None = Depends(get_current_tenant_context),
) -> AuditEventListResponse:
    try:
        arguments = dict(
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
        tenant_id = getattr(getattr(context, "tenant", None), "id", None)
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        page = service.list_events(**arguments)
    except AuditEventValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid audit-event filter",
        ) from error
    return AuditEventListResponse(
        items=page.items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )
