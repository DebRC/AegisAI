"""Create validated audit events inside an existing business transaction."""

from collections.abc import Mapping
from typing import TypeAlias

from sqlalchemy.orm import Session

from app.core.exceptions import AuditEventValidationError
from app.models.audit_event import AuditEvent
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.repositories.audit_event_repository import AuditEventRepository


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
    })
    _METADATA_KEYS = frozenset({
        "access_level",
        "content_type",
        "failure_category",
        "previous_access_level",
        "provider",
        "result_count",
    })
    _MAX_METADATA_STRING_LENGTH = 128

    def __init__(self, db: Session):
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
                event_type=event_type,
                outcome=outcome,
                target_type=target_type,
                target_id=target_id,
                metadata_=safe_metadata,
            )
        )

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
