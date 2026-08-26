"""Read-only RBAC summaries for the administrative control plane."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole
from app.repositories.permission_repository import PermissionRepository
from app.repositories.role_repository import RoleRepository


@dataclass(frozen=True)
class AdminRoleSummary:
    role: Role
    permission_codes: list[str]
    user_count: int


@dataclass(frozen=True)
class AdminPermissionSummary:
    permission: Permission
    role_count: int


class AdminRbacService:
    """Provide safe RBAC summaries without duplicating mutation logic."""

    def __init__(self, db: Session):
        self.db = db
        self.roles = RoleRepository(db)
        self.permissions = PermissionRepository(db)

    def list_roles(self) -> list[AdminRoleSummary]:
        roles = self.roles.list()
        role_permissions = self.db.execute(
            select(RolePermission.role_id, Permission.code)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .order_by(RolePermission.role_id, Permission.code)
        ).all()
        permission_codes: dict[int, list[str]] = {role.id: [] for role in roles}
        for role_id, code in role_permissions:
            permission_codes.setdefault(role_id, []).append(code)
        user_counts = dict(self.db.execute(
            select(UserRole.role_id, func.count(UserRole.id)).group_by(UserRole.role_id)
        ).all())
        return [
            AdminRoleSummary(role, permission_codes[role.id], user_counts.get(role.id, 0))
            for role in roles
        ]

    def list_permissions(self) -> list[AdminPermissionSummary]:
        role_counts = dict(self.db.execute(
            select(RolePermission.permission_id, func.count(RolePermission.id))
            .group_by(RolePermission.permission_id)
        ).all())
        return [
            AdminPermissionSummary(permission, role_counts.get(permission.id, 0))
            for permission in self.permissions.list()
        ]
