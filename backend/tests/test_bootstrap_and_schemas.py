import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from pydantic import ValidationError

from app.models import Role
from app.schemas.auth import RegisterRequest
from app.schemas.rbac import RoleCreateRequest
from app.schemas.refresh import RefreshRequest
from app.schemas.token import TokenPayload
from app.security.constants import TokenType
from app.security.permissions import PermissionCode
from scripts import bootstrap_administrator
from tests.helpers import DatabaseTestCase


class BootstrapAdministratorTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user("admin@example.com")
        self.role = Role(
            name="administrator",
            description="System administrator",
            is_system=True,
        )
        self.session.add(self.role)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_assignment_is_idempotent_and_requires_existing_user_and_role(self) -> None:
        with patch.object(
            bootstrap_administrator,
            "SessionLocal",
            return_value=self.session,
        ):
            self.assertTrue(
                bootstrap_administrator.assign_administrator("admin@example.com")
            )
            self.assertFalse(
                bootstrap_administrator.assign_administrator("admin@example.com")
            )

            with self.assertRaisesRegex(ValueError, "No user exists"):
                bootstrap_administrator.assign_administrator("missing@example.com")

        self.session.delete(self.role)
        self.session.commit()
        with patch.object(
            bootstrap_administrator,
            "SessionLocal",
            return_value=self.session,
        ):
            with self.assertRaisesRegex(ValueError, "administrator role is missing"):
                bootstrap_administrator.assign_administrator("admin@example.com")

    def test_main_reports_success_existing_assignment_and_input_errors(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = SimpleNamespace(email="admin@example.com")

        with patch.object(
            bootstrap_administrator.argparse,
            "ArgumentParser",
            return_value=parser,
        ), patch.object(
            bootstrap_administrator,
            "assign_administrator",
            return_value=True,
        ), patch("builtins.print") as print_mock:
            bootstrap_administrator.main()
        print_mock.assert_called_once_with(
            "Administrator role assigned to admin@example.com."
        )

        with patch.object(
            bootstrap_administrator.argparse,
            "ArgumentParser",
            return_value=parser,
        ), patch.object(
            bootstrap_administrator,
            "assign_administrator",
            return_value=False,
        ), patch("builtins.print") as print_mock:
            bootstrap_administrator.main()
        print_mock.assert_called_once_with(
            "admin@example.com already has the administrator role."
        )

        with patch.object(
            bootstrap_administrator.argparse,
            "ArgumentParser",
            return_value=parser,
        ), patch.object(
            bootstrap_administrator,
            "assign_administrator",
            side_effect=ValueError("missing user"),
        ), self.assertRaises(SystemExit):
            parser.error.side_effect = SystemExit(2)
            bootstrap_administrator.main()
        parser.error.assert_called_with("missing user")


class SchemaTests(unittest.TestCase):
    def test_request_validation_and_whitespace_normalization(self) -> None:
        request = RoleCreateRequest(
            name="  reader  ",
            description="  Read-only access  ",
        )
        self.assertEqual(request.name, "reader")
        self.assertEqual(request.description, "Read-only access")

        with self.assertRaises(ValidationError):
            RegisterRequest(
                email="invalid-email",
                full_name="A",
                password="short",
            )

        with self.assertRaises(ValidationError):
            RefreshRequest(refresh_token="")

    def test_token_payload_parses_expected_types(self) -> None:
        payload = TokenPayload(
            sub=5,
            type=TokenType.ACCESS,
            exp="2030-01-01T00:00:00Z",
        )

        self.assertEqual(payload.sub, 5)
        self.assertEqual(payload.type, TokenType.ACCESS)
        self.assertIn(PermissionCode.ROLES_READ.value, PermissionCode.values())
