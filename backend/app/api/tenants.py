from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_auth_service, get_tenant_service
from app.models.user import User
from app.schemas.tenant import TenantCreateRequest, TenantMembershipCreateRequest, TenantMembershipResponse, TenantResponse
from app.schemas.token import LoginResponse
from app.security.dependencies import get_current_user
from app.security.dependencies import TenantContext, get_current_tenant_context, require_permission
from app.security.permissions import PermissionCode
from app.services.auth_service import AuthService
from app.services.tenant_service import TenantService


router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("", response_model=list[TenantMembershipResponse])
def list_tenants(
    current_user: User = Depends(get_current_user),
    service: TenantService = Depends(get_tenant_service),
) -> list[TenantMembershipResponse]:
    return [TenantMembershipResponse(tenant=membership.tenant, is_active=membership.is_active) for membership in service.list_active_memberships(current_user.id)]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    request: TenantCreateRequest,
    current_user: User = Depends(get_current_user),
    service: TenantService = Depends(get_tenant_service),
) -> TenantResponse:
    try:
        return service.create_tenant(creator_user_id=current_user.id, name=request.name, slug=request.slug).tenant
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid tenant") from error


@router.post("/{tenant_id}/select", response_model=LoginResponse)
def select_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    try:
        return auth.issue_session(current_user, tenant_id=tenant_id)
    except Exception as error:
        # A tenant switch must not disclose another tenant's existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found") from error


@router.post("/{tenant_id}/memberships", response_model=TenantMembershipResponse, status_code=status.HTTP_201_CREATED)
def add_tenant_member(
    tenant_id: int,
    request: TenantMembershipCreateRequest,
    _: User = Depends(require_permission(PermissionCode.ROLES_ASSIGN)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: TenantService = Depends(get_tenant_service),
) -> TenantMembershipResponse:
    if context.tenant.id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    try:
        membership = service.add_member(tenant_id=tenant_id, user_id=request.user_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from error
    return TenantMembershipResponse(tenant=membership.tenant, is_active=membership.is_active)
