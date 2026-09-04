from dataclasses import dataclass

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Header
from fastapi import Request
from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.db.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.models.api_key import ApiKey
from app.repositories.permission_repository import PermissionRepository
from app.repositories.user_repository import UserRepository
from app.security.constants import TokenType
from app.security.jwt import decode_token
from app.security.permissions import PermissionCode
from app.services.tenant_service import TenantService
from app.services.api_key_service import ApiKeyService
from app.services.rate_limit_service import RateLimitService
from app.core.config import settings
from app.core.exceptions import ApiKeyAuthenticationError
from app.core.exceptions import RateLimitExceededError
from app.core.exceptions import RateLimitUnavailableError

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False,
)

access_token_bearer = HTTPBearer(
    scheme_name="AegisAI access token",
    bearerFormat="JWT",
    description="Paste an access token issued by password login or SSO.",
    auto_error=False,
)


_ADMINISTRATION_PERMISSIONS = frozenset({
    PermissionCode.USERS_READ,
    PermissionCode.USERS_MANAGE,
    PermissionCode.ROLES_READ,
    PermissionCode.ROLES_MANAGE,
    PermissionCode.ROLES_ASSIGN,
    PermissionCode.DOCUMENTS_MANAGE,
    PermissionCode.AUDIT_READ,
})


@dataclass(frozen=True)
class TenantContext:
    """Trusted request scope resolved from a signed token and active membership."""

    user: User
    tenant: Tenant
    membership: TenantMembership
    api_key: ApiKey | None = None


def _access_token_from_credentials(
    token: str | None,
    bearer_credentials: HTTPAuthorizationCredentials | None,
) -> str:
    access_token = getattr(bearer_credentials, "credentials", None) or token
    if access_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return access_token


def _resolve_authenticated_user(access_token: str, db: Session) -> tuple[User, object]:
    try:
        payload = decode_token(access_token)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
    if payload.type != TokenType.ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user = UserRepository(db).get_by_id(payload.sub)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user, payload


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(
        access_token_bearer
    ),
) -> User:
    return _resolve_authenticated_user(_access_token_from_credentials(token, bearer_credentials), db)[0]


def get_current_tenant_context(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(access_token_bearer),
    presented_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> TenantContext:
    if presented_api_key:
        try:
            api_key = ApiKeyService(db).authenticate(presented_api_key)
        except ApiKeyAuthenticationError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key") from error
        user = UserRepository(db).get_by_id(api_key.created_by_user_id)
        membership = (
            TenantService(db).get_active_membership(
                tenant_id=api_key.tenant_id,
                user_id=api_key.created_by_user_id,
            )
        )
        if user is None or not user.is_active or membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return TenantContext(user=user, tenant=membership.tenant, membership=membership, api_key=api_key)
    user, payload = _resolve_authenticated_user(_access_token_from_credentials(token, bearer_credentials), db)
    tenants = TenantService(db)
    membership = (
        tenants.get_active_membership(tenant_id=payload.tenant_id, user_id=user.id)
        if payload.tenant_id is not None
        else tenants.ensure_default_membership(user.id)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant membership is unavailable")
    return TenantContext(user=user, tenant=membership.tenant, membership=membership)


def require_permission(permission: PermissionCode):
    def dependency(
        context: TenantContext | User = Depends(get_current_tenant_context),
        db: Session = Depends(get_db),
        request: Request = None,
    ) -> User:
        # Direct unit calls from earlier phases pass User, Session positional
        # arguments. Runtime requests always receive the resolved context.
        user = context if not hasattr(context, "user") else context.user
        tenant_id = getattr(getattr(context, "tenant", None), "id", None)
        api_key = getattr(context, "api_key", None)
        has_permission = (
            permission.value in api_key.scopes
            if api_key is not None
            else PermissionRepository(db).user_has_permission(
                user.id,
                permission.value,
                tenant_id=tenant_id,
            )
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        # Unit tests call this dependency as a normal function. Production
        # FastAPI requests always provide Request, enabling the Redis guard.
        if request is not None and settings.RATE_LIMIT_ENABLED and tenant_id is not None:
            principal = f"key-{api_key.key_prefix}" if api_key is not None else f"user-{user.id}"
            try:
                decision = RateLimitService().enforce(tenant_id=tenant_id, principal=principal)
            except RateLimitExceededError as error:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Request rate limit exceeded",
                    headers={"Retry-After": "60"},
                ) from error
            except RateLimitUnavailableError as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Request rate limiting is temporarily unavailable",
                ) from error

        return user

    return dependency


def require_administration_permission(permission: PermissionCode):
    """Return the normal RBAC guard only for approved admin capabilities."""
    if permission not in _ADMINISTRATION_PERMISSIONS:
        raise ValueError("Administrative routes require an administration permission")
    return require_permission(permission)
