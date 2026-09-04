"""Tenant-configured lifecycle enforcement for original source documents."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import RetentionPolicyValidationError
from app.models.audit_event import AuditEventOutcome, AuditEventType
from app.models.document import Document
from app.models.retention_policy import RetentionPolicy
from app.repositories.retention_policy_repository import RetentionPolicyRepository
from app.services.audit_event_service import AuditEventService
from app.services.document_service import DocumentService
from app.storage.documents import DocumentStorage


class RetentionService:
    """Keep retention policy configuration separate from the deletion workflow."""

    def __init__(self, db: Session, storage: DocumentStorage):
        self.db = db
        self.policies = RetentionPolicyRepository(db)
        self.audit_events = AuditEventService(db)
        self.documents = DocumentService(db, storage)

    def get_policy(self, tenant_id: int) -> RetentionPolicy:
        return self.policies.get_or_create(tenant_id)

    def update_policy(
        self,
        *,
        tenant_id: int,
        actor_user_id: int,
        document_retention_days: int | None,
    ) -> RetentionPolicy:
        self._validate_days(document_retention_days)
        policy = self.policies.get_or_create(tenant_id)
        policy.document_retention_days = document_retention_days
        self.audit_events.record(
            event_type=AuditEventType.GOVERNANCE_RETENTION_UPDATED,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            target_type="retention_policy",
            target_id=policy.id,
            metadata={"retention_days": document_retention_days},
        )
        self.db.commit()
        self.db.refresh(policy)
        return policy

    def purge_expired_documents(self, *, tenant_id: int, actor_user_id: int | None = None) -> int:
        policy = self.policies.get_for_tenant(tenant_id)
        if policy is None or policy.document_retention_days is None:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=policy.document_retention_days)
        document_ids = self.policies.list_expired_document_ids(tenant_id=tenant_id, cutoff=cutoff)
        # Delete through the established lifecycle so active jobs, extracted
        # text, vectors, audit handling, and source storage stay aligned.
        for document_id in document_ids:
            self.documents.delete_document(
                document_id,
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
            )
        if document_ids:
            self.audit_events.record(
                event_type=AuditEventType.GOVERNANCE_RETENTION_PURGED,
                outcome=AuditEventOutcome.SUCCEEDED,
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
                target_type="retention_policy",
                target_id=policy.id,
                metadata={"purged_count": len(document_ids)},
            )
            self.db.commit()
        return len(document_ids)

    def sweep_all_tenants(self) -> int:
        """Run one idempotent sweep; used only by the trusted periodic worker."""
        return sum(self.purge_expired_documents(tenant_id=policy.tenant_id) for policy in self.policies.list_enabled())

    @staticmethod
    def _validate_days(value: int | None) -> None:
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 36500):
            raise RetentionPolicyValidationError()
