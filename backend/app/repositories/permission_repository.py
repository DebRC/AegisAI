from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission


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
