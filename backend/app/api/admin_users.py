"""Administrator user-management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_admin_user_service
from app.core.exceptions import AdministratorSelfDeactivationError, UserNotFoundError
from app.models.user import User
from app.schemas.admin import AdminUserListResponse, AdminUserResponse, AdminUserRoleResponse, AdminUserStatusRequest
from app.security.dependencies import require_administration_permission
from app.security.permissions import PermissionCode
from app.services.admin_user_service import AdminUserService


router = APIRouter(prefix="/admin/users", tags=["Administration"])


def _response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[
            AdminUserRoleResponse(
                id=assignment.role.id,
                name=assignment.role.name,
                is_system=assignment.role.is_system,
            )
            for assignment in user.role_assignments
        ],
    )


@router.get("", response_model=AdminUserListResponse)
def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    email_query: str | None = Query(default=None, min_length=1, max_length=255),
    is_active: bool | None = None,
    service: AdminUserService = Depends(get_admin_user_service),
    _: User = Depends(require_administration_permission(PermissionCode.USERS_READ)),
) -> AdminUserListResponse:
    page = service.list_users(
        offset=offset,
        limit=limit,
        email_query=email_query,
        is_active=is_active,
    )
    return AdminUserListResponse(
        items=[_response(user) for user in page.items],
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get("/{user_id}", response_model=AdminUserResponse)
def get_user(
    user_id: int,
    service: AdminUserService = Depends(get_admin_user_service),
    _: User = Depends(require_administration_permission(PermissionCode.USERS_READ)),
) -> AdminUserResponse:
    try:
        return _response(service.get_user(user_id))
    except UserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from error


@router.patch("/{user_id}/status", response_model=AdminUserResponse)
def set_user_status(
    user_id: int,
    request: AdminUserStatusRequest,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: User = Depends(require_administration_permission(PermissionCode.USERS_MANAGE)),
) -> AdminUserResponse:
    try:
        return _response(service.set_active(
            actor_user_id=current_user.id,
            user_id=user_id,
            is_active=request.is_active,
        ))
    except UserNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from error
    except AdministratorSelfDeactivationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Administrators cannot deactivate themselves") from error
