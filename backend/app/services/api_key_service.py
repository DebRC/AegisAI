"""Creation and validation of tenant-scoped machine credentials."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiKeyAuthenticationError, ApiKeyValidationError
from app.models.api_key import ApiKey
from app.models.audit_event import AuditEventOutcome, AuditEventType
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.permission_repository import PermissionRepository
from app.services.audit_event_service import AuditEventService
from app.security.permissions import PermissionCode


@dataclass(frozen=True)
class CreatedApiKey:
    api_key: ApiKey
    plaintext: str


class ApiKeyService:
    """Hash secrets before persistence and constrain scopes to caller authority."""

    _PREFIX = "aegis"

    def __init__(self, db: Session):
        self.db = db
        self.keys = ApiKeyRepository(db)
        self.permissions = PermissionRepository(db)
        self.audit_events = AuditEventService(db)

    def create(
        self,
        *,
        tenant_id: int,
        creator_user_id: int,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> CreatedApiKey:
        normalized_name = self._normalize_name(name)
        normalized_scopes = self._normalize_scopes(scopes)
        self._validate_expiry(expires_at)
        for scope in normalized_scopes:
            if not self.permissions.user_has_permission(
                creator_user_id, scope, tenant_id=tenant_id
            ):
                raise ApiKeyValidationError("Requested scopes exceed the creator's authority")

        # The handle is deliberately non-secret and unique; the 256-bit secret
        # is shown exactly once in the create response.
        prefix = secrets.token_hex(8)
        plaintext = f"{self._PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
        api_key = self.keys.create(
            ApiKey(
                tenant_id=tenant_id,
                created_by_user_id=creator_user_id,
                name=normalized_name,
                key_prefix=prefix,
                secret_hash=self._hash(plaintext),
                scopes=normalized_scopes,
                expires_at=expires_at,
            )
        )
        self.audit_events.record(
            event_type=AuditEventType.GOVERNANCE_API_KEY_CREATED,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=creator_user_id,
            tenant_id=tenant_id,
            target_type="api_key",
            target_id=api_key.id,
            metadata={"api_key_prefix": prefix},
        )
        self.db.commit()
        self.db.refresh(api_key)
        return CreatedApiKey(api_key=api_key, plaintext=plaintext)

    def list_for_tenant(self, tenant_id: int) -> list[ApiKey]:
        return self.keys.list_for_tenant(tenant_id)

    def revoke(self, *, tenant_id: int, api_key_id: int, actor_user_id: int) -> ApiKey:
        api_key = self.keys.get_active_by_id(tenant_id=tenant_id, api_key_id=api_key_id)
        if api_key is None:
            raise ApiKeyValidationError("API key not found")
        api_key.revoked_at = datetime.now(timezone.utc)
        api_key.is_active = False
        self.audit_events.record(
            event_type=AuditEventType.GOVERNANCE_API_KEY_REVOKED,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            target_type="api_key",
            target_id=api_key.id,
            metadata={"api_key_prefix": api_key.key_prefix},
        )
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

    def authenticate(self, presented_key: str) -> ApiKey:
        prefix = self._extract_prefix(presented_key)
        api_key = self.keys.get_by_prefix(prefix)
        now = datetime.now(timezone.utc)
        if (
            api_key is None
            or not api_key.is_active
            or api_key.revoked_at is not None
            or (api_key.expires_at is not None and api_key.expires_at <= now)
            or not hmac.compare_digest(api_key.secret_hash, self._hash(presented_key))
        ):
            raise ApiKeyAuthenticationError()
        self.keys.mark_used(api_key, now)
        self.db.commit()
        return api_key

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not (normalized := name.strip()) or len(normalized) > 100:
            raise ApiKeyValidationError("Invalid API key name")
        return normalized

    @staticmethod
    def _normalize_scopes(scopes: list[str]) -> list[str]:
        if not isinstance(scopes, list) or not scopes:
            raise ApiKeyValidationError("At least one API key scope is required")
        if any(not isinstance(scope, str) for scope in scopes):
            raise ApiKeyValidationError("Invalid API key scopes")
        normalized = sorted(set(scopes))
        if len(normalized) > 20 or not set(normalized).issubset(PermissionCode.values()):
            raise ApiKeyValidationError("Invalid API key scopes")
        return normalized

    @staticmethod
    def _validate_expiry(expires_at: datetime | None) -> None:
        if expires_at is not None and (
            expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc)
        ):
            raise ApiKeyValidationError("API key expiry must be in the future")

    @classmethod
    def _extract_prefix(cls, presented_key: str) -> str:
        parts = presented_key.split("_", 2) if isinstance(presented_key, str) else []
        if len(parts) != 3 or parts[0] != cls._PREFIX or len(parts[1]) != 16 or not parts[2]:
            raise ApiKeyAuthenticationError()
        return parts[1]

    @staticmethod
    def _hash(presented_key: str) -> str:
        # HMAC protects the hash column even if an attacker has candidate data.
        return hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"),
            presented_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
