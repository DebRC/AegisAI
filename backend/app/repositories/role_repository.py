from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, role: Role) -> Role:
        self.db.add(role)
        self.db.flush()
        self.db.refresh(role)
        return role

    def get_by_id(self, role_id: int, *, tenant_id: int | None = None) -> Role | None:
        statement = select(Role).where(Role.id == role_id)
        if tenant_id is not None:
            statement = statement.where(Role.tenant_id.in_((tenant_id, None)))
        return self.db.scalar(statement)

    def get_by_name(self, name: str, *, tenant_id: int | None = None) -> Role | None:
        statement = select(Role).where(Role.name == name)
        if tenant_id is not None:
            statement = statement.where(Role.tenant_id.in_((tenant_id, None)))
        return self.db.scalar(statement)

    def list(self, *, tenant_id: int | None = None) -> list[Role]:
        statement = select(Role)
        if tenant_id is not None:
            statement = statement.where(Role.tenant_id.in_((tenant_id, None)))
        return list(self.db.scalars(statement.order_by(Role.name)))

    def delete(self, role: Role) -> None:
        self.db.delete(role)
        self.db.flush()
