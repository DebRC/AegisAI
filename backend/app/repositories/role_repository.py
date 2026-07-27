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

    def get_by_id(self, role_id: int) -> Role | None:
        return self.db.scalar(
            select(Role).where(Role.id == role_id)
        )

    def get_by_name(self, name: str) -> Role | None:
        return self.db.scalar(
            select(Role).where(Role.name == name)
        )

    def list(self) -> list[Role]:
        return list(
            self.db.scalars(
                select(Role).order_by(Role.name)
            )
        )

    def delete(self, role: Role) -> None:
        self.db.delete(role)
        self.db.flush()
