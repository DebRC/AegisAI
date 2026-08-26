"""Immutable, security-relevant audit events."""

from datetime import datetime
from datetime import timezone
from enum import Enum

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class AuditEventOutcome(str, Enum):
    """Safe, stable result classes for a security-relevant action."""

    SUCCEEDED = "succeeded"
    DENIED = "denied"
    FAILED = "failed"


class AuditEventType(str, Enum):
    """Published Phase 13 event taxonomy; additions require a migration."""

    AUTH_LOGIN_SUCCEEDED = "auth.login.succeeded"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_SSO_SUCCEEDED = "auth.sso.succeeded"
    AUTH_SSO_FAILED = "auth.sso.failed"
    AUTH_REFRESH_SUCCEEDED = "auth.refresh.succeeded"
    AUTH_REFRESH_FAILED = "auth.refresh.failed"
    AUTH_LOGOUT_SUCCEEDED = "auth.logout.succeeded"
    RBAC_ROLE_CREATED = "rbac.role.created"
    RBAC_ROLE_DELETED = "rbac.role.deleted"
    RBAC_ROLE_PERMISSION_GRANTED = "rbac.role_permission.granted"
    RBAC_ROLE_PERMISSION_REVOKED = "rbac.role_permission.revoked"
    RBAC_USER_ROLE_ASSIGNED = "rbac.user_role.assigned"
    RBAC_USER_ROLE_REMOVED = "rbac.user_role.removed"
    ADMIN_USER_ACTIVATED = "admin.user.activated"
    ADMIN_USER_DEACTIVATED = "admin.user.deactivated"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_RENAMED = "document.renamed"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_REPROCESS_QUEUED = "document.reprocess_queued"
    DOCUMENT_ACCESS_GRANT_CREATED = "document.access_grant.created"
    DOCUMENT_ACCESS_GRANT_UPDATED = "document.access_grant.updated"
    DOCUMENT_ACCESS_GRANT_REVOKED = "document.access_grant.revoked"
    DOCUMENT_READ = "document.read"
    RETRIEVAL_SEARCH = "retrieval.search"
    CHAT_REQUEST = "chat.request"


class AuditEvent(Base):
    """One append-only, data-minimized audit record."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "(target_type IS NULL) = (target_id IS NULL)",
            name="ck_audit_events_target_fields_paired",
        ),
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_actor_user_id_occurred_at", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_target_type_target_id_occurred_at", "target_type", "target_id", "occurred_at"),
        Index("ix_audit_events_event_type_occurred_at", "event_type", "occurred_at"),
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        SqlEnum(
            AuditEventType,
            name="audit_event_type",
            values_callable=lambda event_types: [event_type.value for event_type in event_types],
            create_constraint=True,
        ),
        nullable=False,
    )
    outcome: Mapped[AuditEventOutcome] = mapped_column(
        SqlEnum(
            AuditEventOutcome,
            name="audit_event_outcome",
            values_callable=lambda outcomes: [outcome.value for outcome in outcomes],
            create_constraint=True,
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict, nullable=False)

    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])
