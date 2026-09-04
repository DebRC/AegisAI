"""Tenant creation, membership lookup, and safe default-tenant migration helpers."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.tenant import Tenant, TenantMembership
from app.models.user_role import UserRole
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository


DEFAULT_TENANT_SLUG = "default"


class TenantService:
    def __init__(self, db: Session):
        self.db = db
        self.tenants = TenantRepository(db)
        self.users = UserRepository(db)

    def ensure_default_membership(self, user_id: int) -> TenantMembership:
        tenant = self.tenants.get_by_slug(DEFAULT_TENANT_SLUG)
        if tenant is None:
            tenant = self.tenants.create(Tenant(slug=DEFAULT_TENANT_SLUG, name="Default organization"))
        membership = self.tenants.get_membership(tenant_id=tenant.id, user_id=user_id)
        if membership is None:
            membership = self.tenants.create_membership(
                TenantMembership(tenant_id=tenant.id, user_id=user_id, is_active=True)
            )
        return membership

    def get_active_membership(self, *, tenant_id: int, user_id: int) -> TenantMembership | None:
        membership = self.tenants.get_active_membership(tenant_id=tenant_id, user_id=user_id)
        if membership is None or not membership.tenant.is_active:
            return None
        return membership

    def list_active_memberships(self, user_id: int) -> list[TenantMembership]:
        return self.tenants.list_active_for_user(user_id)

    def create_tenant(self, *, creator_user_id: int, name: str, slug: str | None = None) -> TenantMembership:
        normalized_name = self._normalize_name(name)
        normalized_slug = self._normalize_slug(slug or normalized_name)
        if self.tenants.get_by_slug(normalized_slug) is not None:
            raise ValueError("Tenant slug already exists")
        tenant = self.tenants.create(Tenant(name=normalized_name, slug=normalized_slug))
        membership = self.tenants.create_membership(
            TenantMembership(tenant_id=tenant.id, user_id=creator_user_id, is_active=True)
        )
        self._clone_default_roles(tenant_id=tenant.id, creator_user_id=creator_user_id)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def add_member(self, *, tenant_id: int, user_id: int) -> TenantMembership:
        """Add an existing active AegisAI identity without assigning any role."""
        tenant = self.tenants.get_by_id(tenant_id)
        user = self.users.get_by_id(user_id)
        if tenant is None or not tenant.is_active or user is None or not user.is_active:
            raise ValueError("Tenant or user not found")
        membership = self.tenants.get_membership(tenant_id=tenant_id, user_id=user_id)
        if membership is not None:
            if not membership.is_active:
                membership.is_active = True
                self.db.commit()
                self.db.refresh(membership)
            return membership
        membership = self.tenants.create_membership(
            TenantMembership(tenant_id=tenant_id, user_id=user_id, is_active=True)
        )
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def _clone_default_roles(self, *, tenant_id: int, creator_user_id: int) -> None:
        default = self.tenants.get_by_slug(DEFAULT_TENANT_SLUG)
        if default is None:
            return
        roles = list(self.db.scalars(select(Role).where(Role.tenant_id == default.id, Role.is_system.is_(True))))
        for role in roles:
            clone = Role(tenant_id=tenant_id, name=role.name, description=role.description, is_system=True)
            self.db.add(clone)
            self.db.flush()
            for assignment in role.permission_assignments:
                self.db.add(RolePermission(role_id=clone.id, permission_id=assignment.permission_id))
            if role.name == "administrator":
                self.db.add(UserRole(user_id=creator_user_id, role_id=clone.id, tenant_id=tenant_id))

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str) or not (value := name.strip()) or len(value) > 255:
            raise ValueError("Invalid tenant name")
        return value

    @staticmethod
    def _normalize_slug(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Invalid tenant slug")
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if not slug or len(slug) > 100:
            raise ValueError("Invalid tenant slug")
        return slug
