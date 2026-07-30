from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User

from app.repositories.user_repository import UserRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository

from app.schemas.auth import RegisterRequest
from app.schemas.token import LoginResponse
from app.schemas.token import TokenResponse

from app.security.hashing import hash_password
from app.security.hashing import verify_password

from app.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    refresh_token_expiry,
)

from app.security.constants import TokenType
from app.core.config import settings

from app.core.exceptions import AuthenticationError
from app.core.exceptions import UserAlreadyExistsError

class AuthService:

    def __init__(
        self,
        db: Session,
    ):

        self.db = db

        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


    def register(
        self,
        request: RegisterRequest,
    ):

        existing = self.users.get_by_email(
            request.email
        )

        if existing:

            raise UserAlreadyExistsError()

        user = User(

            email=request.email,

            full_name=request.full_name,

            password_hash=hash_password(
                request.password
            ),

        )

        self.users.create(user)
        self._commit()

        return user

    def login(
        self,
        email: str,
        password: str,
    ) -> LoginResponse:

        user = self.users.get_by_email(
            email
        )

        if user is None:

            raise AuthenticationError()

        if not verify_password(

            password,

            user.password_hash,

        ):

            raise AuthenticationError()

        return self.issue_session(user)

    def issue_session(
        self,
        user: User,
    ) -> LoginResponse:
        """Issue a local session after any trusted authentication method."""
        if not user.is_active:
            raise AuthenticationError("Inactive user")

        access = create_access_token(
            user.id
        )

        refresh = create_refresh_token(
            user.id
        )

        refresh_token = RefreshToken(

            token=refresh,

            expires_at=refresh_token_expiry(),

            user_id=user.id,
        )

        self.refresh_tokens.create(refresh_token)

        user.last_login = datetime.now(
            timezone.utc
        )

        self._commit()

        return LoginResponse(

            access_token=access,

            refresh_token=refresh,

            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,

            user=user,

        )

    def logout(
        self,
        refresh_token: str,
    ):

        self.refresh_tokens.revoke_by_token(
            refresh_token
        )

        self._commit()

    def refresh(
        self,
        refresh_token: str,
    ) -> TokenResponse:

        payload = decode_token(refresh_token)

        if payload.type != TokenType.REFRESH:

            raise AuthenticationError(
                "Invalid refresh token"
            )

        stored = (
            self.refresh_tokens
            .get_valid_token(refresh_token)
        )

        if stored is None:

            raise AuthenticationError(
                "Refresh token revoked"
            )

        user = self.users.get_by_id(
            payload.sub
        )

        if user is None:

            raise AuthenticationError(
                "User not found"
            )

        if not user.is_active:

            self.refresh_tokens.revoke_by_token(
                refresh_token
            )
            self._commit()

            raise AuthenticationError(
                "Inactive user"
            )

        self.refresh_tokens.revoke_by_token(
            refresh_token
        )

        access = create_access_token(
            user.id
        )

        new_refresh = create_refresh_token(
            user.id
        )

        self.refresh_tokens.create(

            RefreshToken(

                token=new_refresh,

                expires_at=refresh_token_expiry(),

                user_id=user.id,

            )
        )

        self._commit()

        return TokenResponse(

            access_token=access,

            refresh_token=new_refresh,

            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,

        )
        
    def cleanup_expired_tokens(
        self,
    ):

        deleted_count = self.refresh_tokens.delete_expired(
            datetime.now(
                timezone.utc
            )
        )

        self._commit()

        return deleted_count
