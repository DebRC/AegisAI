from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant, TenantMembership


class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, tenant_id: int) -> Tenant | None:
        return self.db.scalar(select(Tenant).where(Tenant.id == tenant_id))

    def get_by_slug(self, slug: str) -> Tenant | None:
        return self.db.scalar(select(Tenant).where(Tenant.slug == slug))

    def create(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        self.db.flush()
        self.db.refresh(tenant)
        return tenant

    def get_membership(self, *, tenant_id: int, user_id: int) -> TenantMembership | None:
        return self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )

    def get_active_membership(self, *, tenant_id: int, user_id: int) -> TenantMembership | None:
        return self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
                TenantMembership.is_active.is_(True),
            )
        )

    def list_active_for_user(self, user_id: int) -> list[TenantMembership]:
        return list(
            self.db.scalars(
                select(TenantMembership)
                .join(Tenant)
                .where(TenantMembership.user_id == user_id, TenantMembership.is_active.is_(True), Tenant.is_active.is_(True))
                .order_by(Tenant.name, Tenant.id)
            )
        )

    def create_membership(self, membership: TenantMembership) -> TenantMembership:
        self.db.add(membership)
        self.db.flush()
        self.db.refresh(membership)
        return membership
