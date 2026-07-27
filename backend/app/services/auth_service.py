from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User

from app.repositories.user_repository import UserRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository

from app.schemas.auth import RegisterRequest
from app.schemas.token import TokenResponse

from app.security.hashing import hash_password
from app.security.hashing import verify_password

from app.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    refresh_token_expiry,
)

from app.security.constants import (
    ACCESS_TOKEN,
    REFRESH_TOKEN,
)

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

        return self.users.create(user)

    def login(
        self,
        email: str,
        password: str,
    ) -> TokenResponse:

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

        self.db.commit()

        return TokenResponse(

            access_token=access,

            refresh_token=refresh,

        )

    def logout(
        self,
        refresh_token: str,
    ):

        self.refresh_tokens.delete_by_token(
            refresh_token
        )

    def refresh(
        self,
        refresh_token: str,
    ) -> TokenResponse:

        payload = decode_token(refresh_token)

        if payload.type != REFRESH_TOKEN:

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

        self.refresh_tokens.delete_by_token(
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

        return TokenResponse(

            access_token=access,

            refresh_token=new_refresh,

        )
        
    def cleanup_expired_tokens(
        self,
    ):

        return self.refresh_tokens.delete_expired(
            datetime.now(
                timezone.utc
            )
        )