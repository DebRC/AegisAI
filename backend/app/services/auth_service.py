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

from app.security.jwt import create_access_token
from app.security.jwt import create_refresh_token
from app.security.jwt import refresh_token_expiry

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
