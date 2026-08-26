import unittest

from app.models import Permission, Role, RolePermission, UserRole
from app.services.admin_rbac_service import AdminRbacService
from tests.helpers import DatabaseTestCase


class AdminRbacServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.role = Role(name="analyst", description="Analyst")
        self.permission = Permission(code="documents:read", description="Read documents")
        self.session.add_all([self.role, self.permission])
        self.session.flush()
        self.session.add_all([
            RolePermission(role_id=self.role.id, permission_id=self.permission.id),
            UserRole(user_id=self.user.id, role_id=self.role.id),
        ])
        self.session.commit()
        self.service = AdminRbacService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_lists_role_and_permission_assignment_summaries(self) -> None:
        roles = self.service.list_roles()
        permissions = self.service.list_permissions()

        self.assertEqual(roles[0].permission_codes, ["documents:read"])
        self.assertEqual(roles[0].user_count, 1)
        self.assertEqual(permissions[0].permission.code, "documents:read")
        self.assertEqual(permissions[0].role_count, 1)
