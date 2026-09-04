from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from fastapi import status

from app.api.dependencies import get_rbac_service
from app.core.exceptions import PermissionNotFoundError
from app.core.exceptions import RoleAlreadyExistsError
from app.core.exceptions import RoleAssignmentAlreadyExistsError
from app.core.exceptions import RoleAssignmentNotFoundError
from app.core.exceptions import RoleNotFoundError
from app.core.exceptions import RolePermissionAlreadyExistsError
from app.core.exceptions import RolePermissionNotFoundError
from app.core.exceptions import SystemRoleModificationError
from app.core.exceptions import UserNotFoundError
from app.schemas.rbac import PermissionResponse
from app.schemas.rbac import RoleCreateRequest
from app.schemas.rbac import RolePermissionResponse
from app.schemas.rbac import RoleResponse
from app.schemas.rbac import UserRoleResponse
from app.services.rbac_service import RbacService
from app.models.user import User
from app.security.dependencies import require_permission
from app.security.dependencies import TenantContext, get_current_tenant_context
from app.security.permissions import PermissionCode


router = APIRouter(prefix="/rbac", tags=["RBAC"])


def _tenant_id(context: TenantContext | None) -> int | None:
    """Return the request tenant, while keeping route functions directly testable."""
    return getattr(getattr(context, "tenant", None), "id", None)


def _service_error_to_http_exception(error: Exception) -> HTTPException:
    if isinstance(error, RoleNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    if isinstance(error, PermissionNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found",
        )

    if isinstance(error, UserNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if isinstance(error, RoleAlreadyExistsError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role already exists",
        )

    if isinstance(error, RoleAssignmentAlreadyExistsError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has this role",
        )

    if isinstance(error, RolePermissionAlreadyExistsError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role already has this permission",
        )

    if isinstance(error, RoleAssignmentNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have this role",
        )

    if isinstance(error, RolePermissionNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role does not have this permission",
        )

    if isinstance(error, SystemRoleModificationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be deleted",
        )

    raise error


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
    dependencies=[Depends(require_permission(PermissionCode.ROLES_READ))],
)
def list_permissions(
    service: RbacService = Depends(get_rbac_service),
):
    return service.list_permissions()


@router.get(
    "/roles",
    response_model=list[RoleResponse],
    dependencies=[Depends(require_permission(PermissionCode.ROLES_READ))],
)
def list_roles(
    service: RbacService = Depends(get_rbac_service),
    context: TenantContext | None = Depends(get_current_tenant_context),
):
    tenant_id = getattr(getattr(context, "tenant", None), "id", None)
    return service.list_roles(tenant_id=tenant_id) if tenant_id is not None else service.list_roles()


@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_role(
    request: RoleCreateRequest,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
):
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        return service.create_role(request.name, request.description, **arguments)
    except RoleAlreadyExistsError as error:
        raise _service_error_to_http_exception(error) from error


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_role(
    role_id: int,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
) -> Response:
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        service.delete_role(role_id, **arguments)
    except (RoleNotFoundError, SystemRoleModificationError) as error:
        raise _service_error_to_http_exception(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/roles/{role_id}/permissions",
    response_model=list[RolePermissionResponse],
    dependencies=[Depends(require_permission(PermissionCode.ROLES_READ))],
)
def list_role_permissions(
    role_id: int,
    service: RbacService = Depends(get_rbac_service),
    context: TenantContext = Depends(get_current_tenant_context),
):
    try:
        tenant_id = _tenant_id(context)
        return service.list_role_permissions(role_id, tenant_id=tenant_id) if tenant_id is not None else service.list_role_permissions(role_id)
    except RoleNotFoundError as error:
        raise _service_error_to_http_exception(error) from error


@router.post(
    "/roles/{role_id}/permissions/{permission_id}",
    response_model=RolePermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_role_permission(
    role_id: int,
    permission_id: int,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
):
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        return service.grant_permission(role_id, permission_id, **arguments)
    except (
        RoleNotFoundError,
        PermissionNotFoundError,
        RolePermissionAlreadyExistsError,
    ) as error:
        raise _service_error_to_http_exception(error) from error


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_role_permission(
    role_id: int,
    permission_id: int,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
) -> Response:
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        service.revoke_permission(role_id, permission_id, **arguments)
    except (RoleNotFoundError, RolePermissionNotFoundError) as error:
        raise _service_error_to_http_exception(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/users/{user_id}/roles",
    response_model=list[UserRoleResponse],
    dependencies=[Depends(require_permission(PermissionCode.USERS_READ))],
)
def list_user_roles(
    user_id: int,
    service: RbacService = Depends(get_rbac_service),
    context: TenantContext = Depends(get_current_tenant_context),
):
    try:
        tenant_id = _tenant_id(context)
        return service.list_user_roles(user_id, tenant_id=tenant_id) if tenant_id is not None else service.list_user_roles(user_id)
    except UserNotFoundError as error:
        raise _service_error_to_http_exception(error) from error


@router.post(
    "/users/{user_id}/roles/{role_id}",
    response_model=UserRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_user_role(
    user_id: int,
    role_id: int,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_ASSIGN)),
    context: TenantContext = Depends(get_current_tenant_context),
):
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        return service.assign_role(user_id, role_id, **arguments)
    except (
        UserNotFoundError,
        RoleNotFoundError,
        RoleAssignmentAlreadyExistsError,
    ) as error:
        raise _service_error_to_http_exception(error) from error


@router.delete(
    "/users/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_user_role(
    user_id: int,
    role_id: int,
    service: RbacService = Depends(get_rbac_service),
    *,
    current_user: User = Depends(require_permission(PermissionCode.ROLES_ASSIGN)),
    context: TenantContext = Depends(get_current_tenant_context),
) -> Response:
    try:
        tenant_id = _tenant_id(context)
        arguments = {"actor_user_id": current_user.id}
        if tenant_id is not None:
            arguments["tenant_id"] = tenant_id
        service.remove_role(user_id, role_id, **arguments)
    except (
        UserNotFoundError,
        RoleNotFoundError,
        RoleAssignmentNotFoundError,
    ) as error:
        raise _service_error_to_http_exception(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
