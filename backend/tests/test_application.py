import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.api import auth as auth_api
from app.api import database as database_api
from app.api import health as health_api
from app.api import protected as protected_api
from app.api import rbac as rbac_api
from app.api.dependencies import get_auth_service
from app.api.dependencies import get_rbac_service
from app.api.dependencies import get_sso_account_service
from app.core.exceptions import AuthenticationError
from app.core.exceptions import RoleAlreadyExistsError
from app.core.exceptions import RoleNotFoundError
from app.core.exceptions import SystemRoleModificationError
from app.core.exceptions import UserAlreadyExistsError
from app.db import database
from app.main import app
from app.models import Role
from app.schemas.auth import RegisterRequest
from app.schemas.rbac import RoleCreateRequest
from app.security import dependencies
from app.security.constants import TokenType
from app.security.permissions import PermissionCode
from app.services.auth_service import AuthService
from app.services.rbac_service import RbacService
from app.services.sso_account_service import SsoAccountService


class ApplicationTests(unittest.TestCase):
    def test_database_session_dependency_closes_session(self) -> None:
        session = Mock()

        with patch.object(database, "SessionLocal", return_value=session):
            dependency = database.get_db()
            self.assertIs(next(dependency), session)
            with self.assertRaises(StopIteration):
                next(dependency)

        session.close.assert_called_once()

    def test_service_dependencies_construct_expected_services(self) -> None:
        session = Mock()

        self.assertIsInstance(get_auth_service(session), AuthService)
        self.assertIsInstance(get_rbac_service(session), RbacService)
        self.assertIsInstance(get_sso_account_service(session), SsoAccountService)

    def test_current_user_and_permission_dependencies(self) -> None:
        active_user = SimpleNamespace(id=5, is_active=True)

        with patch.object(
            dependencies,
            "decode_token",
            return_value=SimpleNamespace(type=TokenType.ACCESS, sub=5),
        ), patch.object(
            dependencies,
            "UserRepository",
            return_value=SimpleNamespace(get_by_id=lambda _: active_user),
        ):
            self.assertIs(dependencies.get_current_user("token", Mock()), active_user)

        with patch.object(
            dependencies,
            "decode_token",
            side_effect=AuthenticationError(),
        ):
            with self.assertRaises(HTTPException) as context:
                dependencies.get_current_user("token", Mock())
        self.assertEqual(context.exception.status_code, 401)

        with patch.object(
            dependencies,
            "decode_token",
            return_value=SimpleNamespace(type=TokenType.REFRESH, sub=5),
        ):
            with self.assertRaises(HTTPException) as context:
                dependencies.get_current_user("token", Mock())
        self.assertEqual(context.exception.detail, "Invalid token type")

        allowed_database = Mock()
        allowed_database.scalar.return_value = 1
        guard = dependencies.require_permission(PermissionCode.ROLES_READ)
        self.assertIs(guard(active_user, allowed_database), active_user)

    def test_basic_routes_and_lifespan(self) -> None:
        self.assertEqual(health_api.health(), {"status": "healthy"})
        user = SimpleNamespace(id=5)
        self.assertEqual(protected_api.protected(user)["user"], user)
        self.assertEqual(root_response := app.routes[-1].endpoint()["service"], app.title)

        asyncio.run(self._exercise_lifespan())

    async def _exercise_lifespan(self) -> None:
        async with app.router.lifespan_context(app):
            pass

    def test_database_health_executes_query_and_closes_session(self) -> None:
        session = Mock()

        with patch.object(database_api, "SessionLocal", return_value=session):
            self.assertEqual(database_api.database_health(), {"database": "connected"})

        session.execute.assert_called_once()
        session.close.assert_called_once()

    def test_auth_route_handlers_translate_errors_and_return_results(self) -> None:
        request = RegisterRequest(
            email="person@example.com",
            full_name="Test Person",
            password="strong-password",
        )
        service = Mock()
        service.register.return_value = "registered"
        self.assertEqual(auth_api.register(request, service), "registered")

        service.register.side_effect = UserAlreadyExistsError()
        with self.assertRaises(HTTPException) as context:
            auth_api.register(request, service)
        self.assertEqual(context.exception.status_code, 409)

        form_data = SimpleNamespace(username="person@example.com", password="password")
        service.login.return_value = "logged-in"
        self.assertEqual(auth_api.login(form_data, service), "logged-in")
        service.login.side_effect = AuthenticationError()
        with self.assertRaises(HTTPException) as context:
            auth_api.login(form_data, service)
        self.assertEqual(context.exception.status_code, 401)

        self.assertEqual(auth_api.me("user"), "user")
        self.assertEqual(auth_api.logout(SimpleNamespace(refresh_token="token"), service), {"message": "Logged out"})
        service.refresh.return_value = "refreshed"
        self.assertEqual(auth_api.refresh(SimpleNamespace(refresh_token="token"), service), "refreshed")

    def test_rbac_route_handlers_and_error_translation(self) -> None:
        service = Mock()
        role = Role(name="reader", description=None)
        service.list_permissions.return_value = ["permission"]
        service.list_roles.return_value = [role]
        service.create_role.return_value = role
        service.list_role_permissions.return_value = ["role-permission"]
        service.grant_permission.return_value = "role-permission"
        service.list_user_roles.return_value = ["user-role"]
        service.assign_role.return_value = "user-role"

        self.assertEqual(rbac_api.list_permissions(service), ["permission"])
        self.assertEqual(rbac_api.list_roles(service), [role])
        self.assertIs(
            rbac_api.create_role(RoleCreateRequest(name="reader"), service),
            role,
        )
        self.assertEqual(rbac_api.delete_role(1, service).status_code, 204)
        self.assertEqual(rbac_api.list_role_permissions(1, service), ["role-permission"])
        self.assertEqual(rbac_api.grant_role_permission(1, 2, service), "role-permission")
        self.assertEqual(rbac_api.revoke_role_permission(1, 2, service).status_code, 204)
        self.assertEqual(rbac_api.list_user_roles(1, service), ["user-role"])
        self.assertEqual(rbac_api.assign_user_role(1, 2, service), "user-role")
        self.assertEqual(rbac_api.remove_user_role(1, 2, service).status_code, 204)

        self.assertEqual(
            rbac_api._service_error_to_http_exception(RoleNotFoundError()).status_code,
            404,
        )
        self.assertEqual(
            rbac_api._service_error_to_http_exception(RoleAlreadyExistsError()).status_code,
            409,
        )
        self.assertEqual(
            rbac_api._service_error_to_http_exception(
                SystemRoleModificationError()
            ).status_code,
            400,
        )
