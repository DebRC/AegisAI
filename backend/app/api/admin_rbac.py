"""Read-only RBAC summaries for administrators."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_admin_rbac_service
from app.models.user import User
from app.schemas.admin import AdminPermissionResponse, AdminRoleResponse
from app.security.dependencies import require_administration_permission
from app.security.permissions import PermissionCode
from app.security.dependencies import TenantContext, get_current_tenant_context
from app.services.admin_rbac_service import AdminRbacService


router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/roles", response_model=list[AdminRoleResponse])
def list_roles(
    service: AdminRbacService = Depends(get_admin_rbac_service),
    _: User = Depends(require_administration_permission(PermissionCode.ROLES_READ)),
    context: TenantContext | None = Depends(get_current_tenant_context),
) -> list[AdminRoleResponse]:
    return [
        AdminRoleResponse(
            id=item.role.id,
            name=item.role.name,
            description=item.role.description,
            is_system=item.role.is_system,
            permission_codes=item.permission_codes,
            user_count=item.user_count,
        )
        for item in (service.list_roles(tenant_id=getattr(getattr(context, "tenant", None), "id", None)) if getattr(getattr(context, "tenant", None), "id", None) is not None else service.list_roles())
    ]


@router.get("/permissions", response_model=list[AdminPermissionResponse])
def list_permissions(
    service: AdminRbacService = Depends(get_admin_rbac_service),
    _: User = Depends(require_administration_permission(PermissionCode.ROLES_READ)),
    context: TenantContext | None = Depends(get_current_tenant_context),
) -> list[AdminPermissionResponse]:
    return [
        AdminPermissionResponse(
            id=item.permission.id,
            code=item.permission.code,
            description=item.permission.description,
            role_count=item.role_count,
        )
        for item in (service.list_permissions(tenant_id=getattr(getattr(context, "tenant", None), "id", None)) if getattr(getattr(context, "tenant", None), "id", None) is not None else service.list_permissions())
    ]
