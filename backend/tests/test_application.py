import asyncio
from datetime import datetime
from datetime import timezone
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.api import auth as auth_api
from app.api import database as database_api
from app.api import documents as documents_api
from app.api import health as health_api
from app.api import protected as protected_api
from app.api import rbac as rbac_api
from app.api.dependencies import get_auth_service
from app.api.dependencies import get_document_service
from app.api.dependencies import get_document_extraction_query_service
from app.api.dependencies import get_rbac_service
from app.api.dependencies import get_sso_account_service
from app.core.exceptions import AuthenticationError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentExtractionNotFoundError
from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentValidationError
from app.core.exceptions import RoleAlreadyExistsError
from app.core.exceptions import RoleNotFoundError
from app.core.exceptions import SystemRoleModificationError
from app.core.exceptions import UserAlreadyExistsError
from app.db import database
from app.main import app
from app.models import DocumentStatus
from app.models import Role
from app.schemas.auth import RegisterRequest
from app.schemas.rbac import RoleCreateRequest
from app.schemas.document import DocumentRenameRequest
from app.security import dependencies
from app.security.constants import TokenType
from app.security.permissions import PermissionCode
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.document_extraction_query_service import DocumentExtractionQueryService
from app.services.rbac_service import RbacService
from app.services.sso_account_service import SsoAccountService
from app.storage.documents import DocumentStorageError


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
        self.assertIsInstance(
            get_document_service(session, Mock()),
            DocumentService,
        )
        self.assertIsInstance(
            get_document_extraction_query_service(session),
            DocumentExtractionQueryService,
        )

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
            return_value=SimpleNamespace(type=TokenType.ACCESS, sub=5),
        ), patch.object(
            dependencies,
            "UserRepository",
            return_value=SimpleNamespace(get_by_id=lambda _: active_user),
        ):
            self.assertIs(
                dependencies.get_current_user(
                    None,
                    Mock(),
                    SimpleNamespace(credentials="bearer-token"),
                ),
                active_user,
            )

        with self.assertRaises(HTTPException) as context:
            dependencies.get_current_user(None, Mock(), None)
        self.assertEqual(context.exception.status_code, 401)

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

    def test_document_routes_require_expected_permissions(self) -> None:
        expected_permissions = {
            ("/documents", "POST"): PermissionCode.DOCUMENTS_WRITE,
            ("/documents", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}", "PATCH"): PermissionCode.DOCUMENTS_WRITE,
            ("/documents/{document_id}", "DELETE"): PermissionCode.DOCUMENTS_WRITE,
            ("/documents/{document_id}/extraction", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}/extraction/chunks", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}/indexing-status", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}/reprocess", "POST"): PermissionCode.DOCUMENTS_WRITE,
            ("/documents/{document_id}/processing-jobs", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}/processing-jobs/{job_id}", "GET"): PermissionCode.DOCUMENTS_READ,
            ("/documents/{document_id}/processing-jobs/{job_id}/retry", "POST"): PermissionCode.DOCUMENTS_WRITE,
        }

        actual_permissions = {
            (route.path, method): self._route_permission(route)
            for route in documents_api.router.routes
            for method in route.methods
        }

        self.assertEqual(actual_permissions, expected_permissions)

    @staticmethod
    def _route_permission(route) -> PermissionCode:
        permissions = [
            cell.cell_contents
            for dependency in route.dependant.dependencies
            for cell in (getattr(dependency.call, "__closure__", None) or [])
            if isinstance(cell.cell_contents, PermissionCode)
        ]
        if len(permissions) != 1:
            raise AssertionError(f"Expected one permission dependency for {route.path}")
        return permissions[0]

    def test_openapi_exposes_password_and_pasteable_bearer_schemes(self) -> None:
        openapi = app.openapi()
        schemes = openapi["components"]["securitySchemes"]
        self.assertEqual(
            schemes["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"],
            "/auth/login",
        )
        self.assertEqual(schemes["AegisAI access token"]["type"], "http")
        self.assertEqual(schemes["AegisAI access token"]["scheme"], "bearer")

        security = openapi["paths"]["/auth/me"]["get"]["security"]
        self.assertIn({"OAuth2PasswordBearer": []}, security)
        self.assertIn({"AegisAI access token": []}, security)

        document_paths = openapi["paths"]
        self.assertEqual(document_paths["/documents"]["post"]["responses"]["201"]["description"], "Successful Response")
        self.assertIn(
            {"OAuth2PasswordBearer": []},
            document_paths["/documents"]["post"]["security"],
        )
        self.assertIn(
            {"AegisAI access token": []},
            document_paths["/documents/{document_id}"]["get"]["security"],
        )
        self.assertIn(
            {"OAuth2PasswordBearer": []},
            document_paths["/documents/{document_id}"]["patch"]["security"],
        )
        self.assertIn(
            {"AegisAI access token": []},
            document_paths["/documents/{document_id}/extraction"]["get"]["security"],
        )
        self.assertIn(
            "202",
            document_paths["/documents/{document_id}/reprocess"]["post"]["responses"],
        )

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

    def test_document_route_handlers_and_error_translation(self) -> None:
        service = Mock()
        user = SimpleNamespace(id=7)
        upload = SimpleNamespace(
            filename="security-policy.txt",
            content_type="text/plain",
            file=io.BytesIO(b"policy"),
        )
        now = datetime.now(timezone.utc)
        document = SimpleNamespace(
            id=3,
            uploader_user_id=user.id,
            title="Security policy",
            original_filename="security-policy.txt",
            content_type="text/plain",
            size_bytes=6,
            sha256="a" * 64,
            status=DocumentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        service.upload.return_value = document
        service.list_documents.return_value = SimpleNamespace(
            items=[document],
            offset=0,
            limit=25,
            total=1,
        )
        service.get_document.return_value = document
        service.rename_document.return_value = document

        self.assertIs(
            documents_api.upload_document(upload, user, service),
            document,
        )
        upload_arguments = service.upload.call_args.kwargs
        self.assertEqual(upload_arguments["uploader_user_id"], user.id)
        self.assertEqual(upload_arguments["original_filename"], "security-policy.txt")
        self.assertEqual(upload_arguments["content_type"], "text/plain")
        self.assertEqual(list(upload_arguments["chunks"]), [b"policy"])
        page = documents_api.list_documents(0, 25, service)
        self.assertEqual([item.id for item in page.items], [document.id])
        self.assertEqual(page.items[0].title, document.title)
        self.assertEqual(page.total, 1)
        self.assertIs(documents_api.get_document(3, service), document)
        self.assertIs(
            documents_api.rename_document(
                3,
                DocumentRenameRequest(title="Updated title"),
                service,
                user,
            ),
            document,
        )
        self.assertEqual(documents_api.delete_document(3, service, user).status_code, 204)

        service.upload.side_effect = DocumentValidationError()
        with self.assertRaises(HTTPException) as context:
            documents_api.upload_document(upload, user, service)
        self.assertEqual(context.exception.status_code, 422)

        service.get_document.side_effect = DocumentNotFoundError()
        with self.assertRaises(HTTPException) as context:
            documents_api.get_document(3, service)
        self.assertEqual(context.exception.status_code, 404)

        self.assertEqual(
            documents_api._document_error_to_http_exception(
                DocumentPersistenceError()
            ).status_code,
            503,
        )
        self.assertEqual(
            documents_api._document_error_to_http_exception(
                DocumentStorageError()
            ).status_code,
            503,
        )
        self.assertEqual(
            documents_api._document_error_to_http_exception(
                DocumentExtractionNotFoundError()
            ).status_code,
            404,
        )

    def test_document_extraction_route_handlers(self) -> None:
        service = Mock()
        now = datetime.now(timezone.utc)
        extraction = SimpleNamespace(
            id=8,
            document_id=3,
            character_count=31,
            extractor_version="phase8-v1",
            extracted_at=now,
            created_at=now,
            updated_at=now,
        )
        chunk = SimpleNamespace(
            id=11,
            ordinal=0,
            content="Security policy",
            start_offset=0,
            end_offset=15,
            source_locations=None,
            created_at=now,
            updated_at=now,
        )
        job = SimpleNamespace(id=9)
        service.get_extraction.return_value = extraction
        service.list_chunks.return_value = SimpleNamespace(
            items=[chunk], offset=0, limit=25, total=1
        )
        service.request_reprocessing.return_value = job

        self.assertIs(documents_api.get_document_extraction(3, service), extraction)
        page = documents_api.list_document_chunks(3, 0, 25, service)
        self.assertEqual([item.id for item in page.items], [chunk.id])
        self.assertEqual(page.total, 1)
        self.assertIs(documents_api.reprocess_document(3, service, Mock()), job)

        service.get_extraction.side_effect = DocumentExtractionNotFoundError()
        with self.assertRaises(HTTPException) as context:
            documents_api.get_document_extraction(3, service)
        self.assertEqual(context.exception.status_code, 404)
