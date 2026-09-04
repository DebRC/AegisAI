from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_role import UserRole


class UserRoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, assignment: UserRole) -> UserRole:
        self.db.add(assignment)
        self.db.flush()
        self.db.refresh(assignment)
        return assignment

    def get_by_user_and_role(
        self,
        user_id: int,
        role_id: int,
        tenant_id: int | None = None,
    ) -> UserRole | None:
        statement = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        if tenant_id is not None:
            statement = statement.where(UserRole.tenant_id.in_((tenant_id, None)))
        return self.db.scalar(statement)

    def list_by_user_id(self, user_id: int, *, tenant_id: int | None = None) -> list[UserRole]:
        statement = select(UserRole).where(UserRole.user_id == user_id)
        if tenant_id is not None:
            statement = statement.where(UserRole.tenant_id.in_((tenant_id, None)))
        return list(self.db.scalars(statement.order_by(UserRole.role_id)))

    def delete(self, assignment: UserRole) -> None:
        self.db.delete(assignment)
        self.db.flush()
