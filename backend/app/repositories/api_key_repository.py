from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, api_key: ApiKey) -> ApiKey:
        self.db.add(api_key)
        self.db.flush()
        self.db.refresh(api_key)
        return api_key

    def get_by_prefix(self, prefix: str) -> ApiKey | None:
        return self.db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))

    def get_active_by_id(self, *, tenant_id: int, api_key_id: int) -> ApiKey | None:
        return self.db.scalar(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.tenant_id == tenant_id,
                ApiKey.is_active.is_(True),
                ApiKey.revoked_at.is_(None),
            )
        )

    def list_for_tenant(self, tenant_id: int) -> list[ApiKey]:
        return list(
            self.db.scalars(
                select(ApiKey)
                .where(ApiKey.tenant_id == tenant_id)
                .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
            )
        )

    def mark_used(self, api_key: ApiKey, occurred_at: datetime) -> None:
        api_key.last_used_at = occurred_at
        self.db.flush()
