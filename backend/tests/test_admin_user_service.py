from datetime import datetime, timedelta, timezone
import unittest

from app.core.exceptions import AdministratorSelfDeactivationError
from app.models import AuditEvent
from app.models import AuditEventType
from app.models import RefreshToken
from app.models import Role
from app.models import UserRole
from app.services.admin_user_service import AdminUserService
from tests.helpers import DatabaseTestCase


class AdminUserServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.admin = self.create_user("admin@example.com")
        self.user = self.create_user("target@example.com")
        self.role = Role(name="analyst", description="Analyst")
        self.session.add(self.role)
        self.session.flush()
        self.session.add(UserRole(user_id=self.user.id, role_id=self.role.id))
        self.token = RefreshToken(
            token="token-value",
            user_id=self.user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        self.session.add(self.token)
        self.session.commit()
        self.service = AdminUserService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_lists_and_gets_safe_user_records_with_roles(self) -> None:
        page = self.service.list_users(offset=0, limit=25, email_query="target")

        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].id, self.user.id)
        self.assertEqual([assignment.role.name for assignment in page.items[0].role_assignments], ["analyst"])
        self.assertEqual(self.service.get_user(self.user.id).email, "target@example.com")

    def test_deactivation_revokes_refresh_tokens_and_records_audit_event(self) -> None:
        user = self.service.set_active(
            actor_user_id=self.admin.id,
            user_id=self.user.id,
            is_active=False,
        )

        self.assertFalse(user.is_active)
        self.assertIsNotNone(self.token.revoked_at)
        event = self.session.query(AuditEvent).one()
        self.assertEqual(event.event_type, AuditEventType.ADMIN_USER_DEACTIVATED)
        self.assertEqual(event.actor_user_id, self.admin.id)
        self.assertEqual(event.target_id, self.user.id)

    def test_prevents_self_deactivation(self) -> None:
        with self.assertRaises(AdministratorSelfDeactivationError):
            self.service.set_active(
                actor_user_id=self.admin.id,
                user_id=self.admin.id,
                is_active=False,
            )
