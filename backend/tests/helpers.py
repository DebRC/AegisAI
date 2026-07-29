from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.db.base import Base
from app.models import Permission
from app.models import User
from app.security.permissions import PermissionCode


class DatabaseTestCase:
    def set_up_database(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session: Session = sessionmaker(bind=self.engine)()

    def tear_down_database(self) -> None:
        self.session.close()
        self.engine.dispose()

    def create_user(
        self,
        email: str = "user@example.com",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email,
            full_name="Test User",
            password_hash="not-used-by-repository-tests",
            is_active=is_active,
        )
        self.session.add(user)
        self.session.commit()
        return user

    def seed_permissions(self) -> None:
        self.session.add_all(
            [
                Permission(code=code.value, description=code.value)
                for code in PermissionCode
            ]
        )
        self.session.commit()

    def permission_id(self, code: PermissionCode) -> int:
        return self.session.scalar(
            select(Permission.id).where(Permission.code == code.value)
        )
