from fastapi import APIRouter, Depends
from app.api.dependencies import get_admin_overview_service
from app.models.user import User
from app.schemas.admin import AdminOverviewResponse
from app.security.dependencies import require_administration_permission
from app.security.permissions import PermissionCode
from app.services.admin_overview_service import AdminOverviewService

router = APIRouter(prefix="/admin", tags=["Administration"])
@router.get("/overview", response_model=AdminOverviewResponse)
def overview(service: AdminOverviewService = Depends(get_admin_overview_service), _: User = Depends(require_administration_permission(PermissionCode.USERS_READ)), __: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE)), ___: User = Depends(require_administration_permission(PermissionCode.AUDIT_READ))) -> AdminOverviewResponse:
    item = service.get_overview()
    return AdminOverviewResponse(total_users=item.total_users, active_users=item.active_users, documents_by_status=item.documents_by_status, jobs_by_status=item.jobs_by_status, recent_event_count=len(item.recent_events))
