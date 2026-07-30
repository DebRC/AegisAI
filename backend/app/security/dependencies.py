from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.db.database import get_db
from app.models.user import User
from app.repositories.permission_repository import PermissionRepository
from app.repositories.user_repository import UserRepository
from app.security.constants import TokenType
from app.security.jwt import decode_token
from app.security.permissions import PermissionCode

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


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(
        access_token_bearer
    ),
) -> User:
    access_token = getattr(bearer_credentials, "credentials", None) or token
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_token(access_token)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from error

    if payload.type != TokenType.ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user = UserRepository(db).get_by_id(payload.sub)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )

    return user


def require_permission(permission: PermissionCode):
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not PermissionRepository(db).user_has_permission(
            current_user.id,
            permission.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return dependency
