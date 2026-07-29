import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.exceptions import RoleAlreadyExistsError
from app.core.exceptions import SystemRoleModificationError
from app.db.base import Base
from app.models import Permission
from app.models import Role
from app.models import User
from app.repositories.permission_repository import PermissionRepository
from app.security import dependencies
from app.security.constants import TokenType
from app.security.permissions import PermissionCode
from app.services.rbac_service import RbacService


class RbacServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session: Session = sessionmaker(bind=self.engine)()
        self.service = RbacService(self.session)

        self.user = User(
            email="operator@example.com",
            full_name="Operator",
            password_hash="not-used-by-rbac-tests",
        )
        self.session.add(self.user)
        self.session.add_all(
            [
                Permission(code=code.value, description=code.value)
                for code in PermissionCode
            ]
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _permission_id(self, code: PermissionCode) -> int:
        return self.session.scalar(
            select(Permission.id).where(Permission.code == code.value)
        )

    def test_role_assignment_grants_and_revokes_permission(self) -> None:
        role = self.service.create_role("analyst", "Read documents")
        permission_id = self._permission_id(PermissionCode.DOCUMENTS_READ)
        permissions = PermissionRepository(self.session)

        self.assertFalse(
            permissions.user_has_permission(
                self.user.id,
                PermissionCode.DOCUMENTS_READ.value,
            )
        )

        self.service.assign_role(self.user.id, role.id)
        self.assertFalse(
            permissions.user_has_permission(
                self.user.id,
                PermissionCode.DOCUMENTS_READ.value,
            )
        )

        self.service.grant_permission(role.id, permission_id)
        self.assertTrue(
            permissions.user_has_permission(
                self.user.id,
                PermissionCode.DOCUMENTS_READ.value,
            )
        )

        self.service.revoke_permission(role.id, permission_id)
        self.assertFalse(
            permissions.user_has_permission(
                self.user.id,
                PermissionCode.DOCUMENTS_READ.value,
            )
        )

    def test_duplicate_role_name_is_rejected(self) -> None:
        self.service.create_role("analyst", "Read documents")

        with self.assertRaises(RoleAlreadyExistsError):
            self.service.create_role("analyst", "Duplicate")

    def test_system_role_cannot_be_deleted(self) -> None:
        system_role = Role(
            name="administrator",
            description="Protected role",
            is_system=True,
        )
        self.session.add(system_role)
        self.session.commit()

        with self.assertRaises(SystemRoleModificationError):
            self.service.delete_role(system_role.id)

    def test_inactive_user_is_rejected_before_permission_check(self) -> None:
        self.user.is_active = False
        self.session.commit()

        with patch.object(
            dependencies,
            "decode_token",
            return_value=SimpleNamespace(
                type=TokenType.ACCESS,
                sub=self.user.id,
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                dependencies.get_current_user("access-token", self.session)

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Inactive user")

    def test_missing_permission_is_forbidden(self) -> None:
        guard = dependencies.require_permission(PermissionCode.ROLES_READ)

        with self.assertRaises(HTTPException) as context:
            guard(self.user, self.session)

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.detail, "Insufficient permissions")
