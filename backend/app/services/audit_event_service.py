"""Create validated audit events inside an existing business transaction."""

from collections.abc import Mapping
from typing import TypeAlias

from sqlalchemy.orm import Session

from app.core.exceptions import AuditEventValidationError
from app.models.audit_event import AuditEvent
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.tenant_service import DEFAULT_TENANT_SLUG


AuditMetadataValue: TypeAlias = str | int | float | bool | None


class AuditEventService:
    """Validate safe event data while leaving commit ownership to the caller."""

    _TARGET_TYPES = frozenset({
        "document",
        "document_access_grant",
        "permission",
        "role",
        "session",
        "user",
        "api_key",
        "retention_policy",
    })
    _METADATA_KEYS = frozenset({
        "access_level",
        "content_type",
        "failure_category",
        "permission_id",
        "previous_access_level",
        "provider",
        "result_count",
        "role_id",
        "api_key_prefix",
        "purged_count",
        "retention_days",
    })
    _MAX_METADATA_STRING_LENGTH = 128

    def __init__(self, db: Session):
        self.db = db
        self.events = AuditEventRepository(db)

    def record(
        self,
        *,
        event_type: AuditEventType,
        outcome: AuditEventOutcome,
        actor_user_id: int | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        metadata: Mapping[str, AuditMetadataValue] | None = None,
        tenant_id: int | None = None,
    ) -> AuditEvent:
        """Add one safe event without committing the caller's transaction."""
        self._validate_event_type(event_type)
        self._validate_outcome(outcome)
        self._validate_actor_id(actor_user_id)
        self._validate_target(target_type, target_id)
        safe_metadata = self._validate_metadata(metadata)
        return self.events.create(
            AuditEvent(
                actor_user_id=actor_user_id,
                tenant_id=tenant_id or self._default_tenant_id(),
                event_type=event_type,
                outcome=outcome,
                target_type=target_type,
                target_id=target_id,
                metadata_=safe_metadata,
            )
        )

    def _default_tenant_id(self) -> int | None:
        """Keep legacy call sites safe while explicit request paths pass tenant_id."""
        tenant = TenantRepository(self.db).get_by_slug(DEFAULT_TENANT_SLUG)
        return tenant.id if tenant is not None else None

    def record_best_effort(self, **kwargs: object) -> None:
        """Persist read telemetry without allowing audit availability to affect access."""
        try:
            self.record(**kwargs)
            self.db.commit()
        except Exception:
            self.db.rollback()

    @staticmethod
    def _validate_event_type(event_type: AuditEventType) -> None:
        if not isinstance(event_type, AuditEventType):
            raise AuditEventValidationError()

    @staticmethod
    def _validate_outcome(outcome: AuditEventOutcome) -> None:
        if not isinstance(outcome, AuditEventOutcome):
            raise AuditEventValidationError()

    @staticmethod
    def _validate_actor_id(actor_user_id: int | None) -> None:
        if actor_user_id is not None and (
            not isinstance(actor_user_id, int)
            or isinstance(actor_user_id, bool)
            or actor_user_id <= 0
        ):
            raise AuditEventValidationError()

    def _validate_target(self, target_type: str | None, target_id: int | None) -> None:
        if target_type is None and target_id is None:
            return
        if (
            target_type not in self._TARGET_TYPES
            or not isinstance(target_id, int)
            or isinstance(target_id, bool)
            or target_id <= 0
        ):
            raise AuditEventValidationError()

    def _validate_metadata(
        self,
        metadata: Mapping[str, AuditMetadataValue] | None,
    ) -> dict[str, AuditMetadataValue]:
        if metadata is None:
            return {}
        if not isinstance(metadata, Mapping) or not set(metadata).issubset(self._METADATA_KEYS):
            raise AuditEventValidationError()

        safe_metadata: dict[str, AuditMetadataValue] = {}
        for key, value in metadata.items():
            if not isinstance(key, str) or not key:
                raise AuditEventValidationError()
            if isinstance(value, str):
                if len(value) > self._MAX_METADATA_STRING_LENGTH:
                    raise AuditEventValidationError()
            elif not isinstance(value, (int, float, bool)) and value is not None:
                raise AuditEventValidationError()
            safe_metadata[key] = value
        return safe_metadata
