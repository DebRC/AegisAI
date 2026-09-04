from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.user_role import UserRole
from app.models.tenant import TenantMembership


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def get_by_email(self, email: str):
        stmt = select(User).where(User.email == email)
        return self.db.scalar(stmt)

    def get_by_id(self, user_id: int):
        stmt = select(User).where(User.id == user_id)
        return self.db.scalar(stmt)

    def update(self):
        self.db.flush()

    def list_for_administration(
        self,
        *,
        email_query: str | None,
        is_active: bool | None,
        offset: int,
        limit: int,
        tenant_id: int | None = None,
    ) -> list[User]:
        statement = self._administration_statement(
            email_query=email_query,
            is_active=is_active,
            tenant_id=tenant_id,
        ).options(selectinload(User.role_assignments).selectinload(UserRole.role))
        if tenant_id is not None:
            statement = statement.options(
                selectinload(User.role_assignments.and_(UserRole.tenant_id == tenant_id)).selectinload(UserRole.role)
            )
        statement = statement.order_by(User.created_at.desc(), User.id.desc())
        return list(self.db.scalars(statement.offset(offset).limit(limit)))

    def count_for_administration(
        self,
        *,
        email_query: str | None,
        is_active: bool | None,
        tenant_id: int | None = None,
    ) -> int:
        statement = self._administration_statement(
            email_query=email_query,
            is_active=is_active,
            tenant_id=tenant_id,
        )
        return self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0

    def get_for_administration(self, user_id: int, *, tenant_id: int | None = None) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.role_assignments).selectinload(UserRole.role))
        )
        if tenant_id is not None:
            statement = (
                statement.join(TenantMembership)
                .where(TenantMembership.tenant_id == tenant_id)
                .options(selectinload(User.role_assignments.and_(UserRole.tenant_id == tenant_id)).selectinload(UserRole.role))
            )
        return self.db.scalar(statement)

    @staticmethod
    def _administration_statement(*, email_query: str | None, is_active: bool | None, tenant_id: int | None):
        statement = select(User)
        if tenant_id is not None:
            statement = statement.join(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
            )
        if email_query is not None:
            statement = statement.where(User.email.ilike(f"%{email_query}%"))
        if is_active is not None:
            statement = statement.where(
                TenantMembership.is_active == is_active if tenant_id is not None else User.is_active == is_active
            )
        return statement
