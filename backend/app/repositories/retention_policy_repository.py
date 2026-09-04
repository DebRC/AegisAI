from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.retention_policy import RetentionPolicy


class RetentionPolicyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_tenant(self, tenant_id: int) -> RetentionPolicy | None:
        return self.db.scalar(
            select(RetentionPolicy).where(RetentionPolicy.tenant_id == tenant_id)
        )

    def get_or_create(self, tenant_id: int) -> RetentionPolicy:
        policy = self.get_for_tenant(tenant_id)
        if policy is None:
            policy = RetentionPolicy(tenant_id=tenant_id)
            self.db.add(policy)
            self.db.flush()
            self.db.refresh(policy)
        return policy

    def list_enabled(self) -> list[RetentionPolicy]:
        return list(
            self.db.scalars(
                select(RetentionPolicy).where(
                    RetentionPolicy.document_retention_days.is_not(None)
                )
            )
        )

    def list_expired_document_ids(self, *, tenant_id: int, cutoff) -> list[int]:
        return list(
            self.db.scalars(
                select(Document.id)
                .where(
                    Document.tenant_id == tenant_id,
                    Document.deleted_at.is_(None),
                    Document.created_at < cutoff,
                )
                .order_by(Document.id)
            )
        )
