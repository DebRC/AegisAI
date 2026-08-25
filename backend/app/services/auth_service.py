from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType

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
from app.services.audit_event_service import AuditEventService

class AuthService:

    def __init__(
        self,
        db: Session,
    ):

        self.db = db

        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)
        self.audit_events = AuditEventService(db)

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
            self._record_auth_failure(AuditEventType.AUTH_LOGIN_FAILED)
            raise AuthenticationError()

        if not verify_password(

            password,

            user.password_hash,

        ):
            self._record_auth_failure(
                AuditEventType.AUTH_LOGIN_FAILED,
                target_user_id=user.id,
            )
            raise AuthenticationError()

        return self.issue_session(user)

    def issue_session(
        self,
        user: User,
        *,
        success_event_type: AuditEventType = AuditEventType.AUTH_LOGIN_SUCCEEDED,
        failure_event_type: AuditEventType = AuditEventType.AUTH_LOGIN_FAILED,
        metadata: dict[str, str] | None = None,
    ) -> LoginResponse:
        """Issue a local session after any trusted authentication method."""
        if not user.is_active:
            self._record_auth_failure(
                failure_event_type,
                target_user_id=user.id,
                metadata=metadata,
            )
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
        self.audit_events.record(
            event_type=success_event_type,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=user.id,
            target_type="session",
            target_id=refresh_token.id,
            metadata=metadata,
        )

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
        stored = self.refresh_tokens.get_valid_token(refresh_token)
        self.refresh_tokens.revoke_by_token(
            refresh_token
        )
        if stored is not None:
            self.audit_events.record(
                event_type=AuditEventType.AUTH_LOGOUT_SUCCEEDED,
                outcome=AuditEventOutcome.SUCCEEDED,
                actor_user_id=stored.user_id,
                target_type="session",
                target_id=stored.id,
            )

        self._commit()

    def refresh(
        self,
        refresh_token: str,
    ) -> TokenResponse:

        try:
            payload = decode_token(refresh_token)
        except AuthenticationError:
            self._record_auth_failure(AuditEventType.AUTH_REFRESH_FAILED)
            raise

        if payload.type != TokenType.REFRESH:
            self._record_auth_failure(AuditEventType.AUTH_REFRESH_FAILED)
            raise AuthenticationError(
                "Invalid refresh token"
            )

        stored = (
            self.refresh_tokens
            .get_valid_token(refresh_token)
        )

        if stored is None:
            self._record_auth_failure(AuditEventType.AUTH_REFRESH_FAILED)
            raise AuthenticationError(
                "Refresh token revoked"
            )

        user = self.users.get_by_id(
            payload.sub
        )

        if user is None:
            self._record_auth_failure(AuditEventType.AUTH_REFRESH_FAILED)
            raise AuthenticationError(
                "User not found"
            )

        if not user.is_active:

            self.refresh_tokens.revoke_by_token(
                refresh_token
            )
            self.audit_events.record(
                event_type=AuditEventType.AUTH_REFRESH_FAILED,
                outcome=AuditEventOutcome.FAILED,
                target_type="user",
                target_id=payload.sub,
                metadata={"failure_category": "inactive_user"},
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

        replacement = self.refresh_tokens.create(

            RefreshToken(

                token=new_refresh,

                expires_at=refresh_token_expiry(),

                user_id=user.id,

            )
        )
        self.audit_events.record(
            event_type=AuditEventType.AUTH_REFRESH_SUCCEEDED,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=user.id,
            target_type="session",
            target_id=replacement.id,
        )

        self._commit()

        return TokenResponse(

            access_token=access,

            refresh_token=new_refresh,

            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,

        )

    def record_sso_failure(self, *, provider: str, failure_category: str) -> None:
        """Persist a provider-safe failed SSO outcome without provider details."""
        self._record_auth_failure(
            AuditEventType.AUTH_SSO_FAILED,
            metadata={"provider": provider, "failure_category": failure_category},
        )

    def _record_auth_failure(
        self,
        event_type: AuditEventType,
        *,
        target_user_id: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.audit_events.record(
            event_type=event_type,
            outcome=AuditEventOutcome.DENIED,
            target_type="user" if target_user_id is not None else None,
            target_id=target_user_id,
            metadata=metadata or {"failure_category": "invalid_credentials"},
        )
        self._commit()
        
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
