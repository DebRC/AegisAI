from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role_permission import RolePermission


class RolePermissionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, assignment: RolePermission) -> RolePermission:
        self.db.add(assignment)
        self.db.flush()
        self.db.refresh(assignment)
        return assignment

    def get_by_role_and_permission(
        self,
        role_id: int,
        permission_id: int,
    ) -> RolePermission | None:
        return self.db.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )

    def list_by_role_id(self, role_id: int) -> list[RolePermission]:
        return list(
            self.db.scalars(
                select(RolePermission)
                .where(RolePermission.role_id == role_id)
                .order_by(RolePermission.permission_id)
            )
        )

    def delete(self, assignment: RolePermission) -> None:
        self.db.delete(assignment)
        self.db.flush()
