from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole


class PermissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, permission_id: int) -> Permission | None:
        return self.db.scalar(
            select(Permission).where(Permission.id == permission_id)
        )

    def get_by_code(self, code: str) -> Permission | None:
        return self.db.scalar(
            select(Permission).where(Permission.code == code)
        )

    def list(self) -> list[Permission]:
        return list(
            self.db.scalars(
                select(Permission).order_by(Permission.code)
            )
        )

    def user_has_permission(self, user_id: int, permission_code: str) -> bool:
        permission_id = self.db.scalar(
            select(Permission.id)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .join(
                UserRole,
                UserRole.role_id == RolePermission.role_id,
            )
            .where(
                UserRole.user_id == user_id,
                Permission.code == permission_code,
            )
            .limit(1)
        )

        return permission_id is not None
