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
from app.api import audit_events as audit_events_api
from app.api import chat as chat_api
from app.api import database as database_api
from app.api import document_access as document_access_api
from app.api import document_access_grants as document_access_grants_api
from app.api import documents as documents_api
from app.api import health as health_api
from app.api import protected as protected_api
from app.api import rbac as rbac_api
from app.api import retrieval as retrieval_api
from app.api.dependencies import get_auth_service
from app.api.dependencies import get_audit_query_service
from app.api.dependencies import get_document_access_policy_service
from app.api.dependencies import get_document_access_grant_service
from app.api.dependencies import get_document_service
from app.api.dependencies import get_document_extraction_query_service
from app.api.dependencies import get_rbac_service
from app.api.dependencies import get_retrieval_authority_service
from app.api.dependencies import get_retrieval_service
from app.api.dependencies import get_query_embedding_service
from app.api.dependencies import get_rag_chat_service
from app.api.dependencies import get_sso_account_service
from app.core.exceptions import AuthenticationError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentAccessOwnerGrantError
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
from app.schemas.audit import AuditEventListResponse
from app.schemas.rbac import RoleCreateRequest
from app.schemas.document import DocumentRenameRequest
from app.security import dependencies
from app.security.constants import TokenType
from app.security.permissions import PermissionCode
from app.services.auth_service import AuthService
from app.services.audit_query_service import AuditQueryService
from app.services.document_service import DocumentService
from app.services.document_access_policy_service import DocumentAccessPolicyService
from app.services.document_access_grant_service import DocumentAccessGrantService
from app.services.document_extraction_query_service import DocumentExtractionQueryService
from app.services.rbac_service import RbacService
from app.services.query_embedding_service import QueryEmbeddingError
from app.services.query_embedding_service import QueryEmbeddingService
from app.services.rag_chat_service import RagChatService
from app.services.retrieval_authority_service import RetrievalAuthorityService
from app.services.retrieval_service import RetrievalService
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
        self.assertIsInstance(get_audit_query_service(session), AuditQueryService)
        self.assertIsInstance(get_rbac_service(session), RbacService)
        self.assertIsInstance(get_sso_account_service(session), SsoAccountService)
        self.assertIsInstance(
            get_document_service(session, Mock()),
            DocumentService,
        )
        self.assertIsInstance(
            get_document_access_policy_service(session),
            DocumentAccessPolicyService,
        )
        self.assertIsInstance(
            get_document_access_grant_service(session),
            DocumentAccessGrantService,
        )
        self.assertIsInstance(
            get_document_extraction_query_service(session),
            DocumentExtractionQueryService,
        )
        self.assertIsInstance(get_query_embedding_service(), QueryEmbeddingService)
        self.assertIsInstance(get_retrieval_authority_service(session), RetrievalAuthorityService)
        self.assertIsInstance(
            get_retrieval_service(Mock(), Mock()),
            RetrievalService,
        )
        with patch("app.api.dependencies.create_chat_model_provider", return_value=Mock()):
            self.assertIsInstance(get_rag_chat_service(Mock()), RagChatService)

    def test_chat_route_requires_read_permission_and_returns_a_non_buffered_sse_response(self) -> None:
        route = next(route for route in chat_api.router.routes if route.path == "/chat/stream")
        self.assertEqual(self._route_permission(route), PermissionCode.DOCUMENTS_READ)

        from app.schemas.chat import ChatStreamRequest
        from app.services.rag_chat_service import ChatAnswerFragment
        from app.services.rag_chat_service import ChatCompletion

        service = Mock()
        service.stream.return_value = iter((ChatAnswerFragment("No context."), ChatCompletion(False, ())))
        response = chat_api.stream(ChatStreamRequest(question="Question"), SimpleNamespace(id=7), service)

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")
        self.assertEqual(response.headers["x-accel-buffering"], "no")

    def test_chat_event_stream_serializes_events_and_closes_the_service(self) -> None:
        from app.schemas.chat import ChatStreamRequest
        from app.services.rag_chat_service import ChatAnswerFragment
        from app.services.rag_chat_service import ChatCompletion

        service = Mock()
        service.stream.return_value = iter((ChatAnswerFragment("No context."), ChatCompletion(False, ())))

        request = ChatStreamRequest(question="Question")
        messages = list(chat_api.chat_event_stream(service, request, user_id=7))

        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[0].startswith("event: answer_delta\n"))
        self.assertTrue(messages[1].startswith("event: done\n"))
        service.stream.assert_called_once_with(request, user_id=7)
        service.close.assert_called_once_with()

    def test_retrieval_route_requires_read_permission_and_translates_failures(self) -> None:
        route = next(route for route in retrieval_api.router.routes if route.path == "/retrieval/search")
        self.assertEqual(self._route_permission(route), PermissionCode.DOCUMENTS_READ)

        from app.schemas.retrieval import RetrievalSearchRequest
        from app.schemas.retrieval import RetrievalSearchResponse

        request = RetrievalSearchRequest(query="policy")
        service = Mock()
        service.search.return_value = RetrievalSearchResponse(items=[], limit=10)
        self.assertEqual(
            retrieval_api.search(request, SimpleNamespace(id=7), service).items,
            [],
        )
        service.search.assert_called_once_with(request, user_id=7)

        service.search.side_effect = QueryEmbeddingError("provider details")
        with self.assertRaises(HTTPException) as context:
            retrieval_api.search(request, SimpleNamespace(id=7), service)
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(context.exception.detail, "Semantic retrieval is temporarily unavailable")

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

    def test_audit_event_route_requires_audit_read_and_returns_a_safe_page(self) -> None:
        route = next(route for route in audit_events_api.router.routes if route.path == "/audit-events")
        self.assertEqual(self._route_permission(route), PermissionCode.AUDIT_READ)
        service = Mock()
        event = SimpleNamespace(
            id=1,
            actor_user_id=7,
            event_type="document.read",
            outcome="succeeded",
            occurred_at=datetime.now(timezone.utc),
            target_type="document",
            target_id=3,
            metadata_={},
        )
        service.list_events.return_value = SimpleNamespace(items=[event], offset=0, limit=25, total=1)

        response = audit_events_api.list_audit_events(
            offset=0,
            limit=25,
            actor_user_id=None,
            target_id=None,
            service=service,
        )

        self.assertIsInstance(response, AuditEventListResponse)
        self.assertEqual(response.total, 1)
        service.list_events.assert_called_once_with(
            offset=0,
            limit=25,
            actor_user_id=None,
            event_type=None,
            outcome=None,
            target_type=None,
            target_id=None,
            occurred_after=None,
            occurred_before=None,
        )

    def test_document_access_dependency_hides_denied_resources(self) -> None:
        user = SimpleNamespace(id=7)
        policy = Mock()

        policy.can_read.return_value = True
        self.assertIs(document_access_api.require_document_read_access(3, user, policy), user)
        policy.can_read.assert_called_once_with(user_id=user.id, document_id=3)

        policy.can_write.return_value = False
        with self.assertRaises(HTTPException) as context:
            document_access_api.require_document_write_access(3, user, policy)
        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Document not found")

    def test_document_access_grant_routes_require_write_and_translate_errors(self) -> None:
        from app.schemas.document import DocumentAccessGrantRequest
        from app.models.document_access_grant import DocumentAccessLevel

        for path in (
            "/documents/{document_id}/access",
            "/documents/{document_id}/access/{user_id}",
        ):
            routes = [route for route in document_access_grants_api.router.routes if route.path == path]
            self.assertTrue(routes)
            self.assertTrue(all(self._route_permission(route) == PermissionCode.DOCUMENTS_WRITE for route in routes))

        service = Mock()
        user = SimpleNamespace(id=7)
        grant = SimpleNamespace(
            document_id=3,
            user_id=8,
            access_level=DocumentAccessLevel.READ,
            granted_by_user_id=7,
        )
        service.list_grants.return_value = [grant]
        service.upsert_grant.return_value = grant

        self.assertEqual(
            document_access_grants_api.list_document_access_grants(3, user, service),
            [grant],
        )
        request = DocumentAccessGrantRequest(access_level=DocumentAccessLevel.READ)
        self.assertEqual(
            document_access_grants_api.upsert_document_access_grant(3, 8, request, user, service),
            grant,
        )
        service.upsert_grant.assert_called_once_with(
            actor_user_id=7,
            document_id=3,
            grantee_user_id=8,
            access_level=DocumentAccessLevel.READ,
        )
        self.assertEqual(
            document_access_grants_api.revoke_document_access_grant(3, 8, user, service).status_code,
            204,
        )
        service.revoke_grant.assert_called_once_with(
            actor_user_id=7,
            document_id=3,
            grantee_user_id=8,
        )

        service.upsert_grant.side_effect = DocumentAccessOwnerGrantError()
        with self.assertRaises(HTTPException) as context:
            document_access_grants_api.upsert_document_access_grant(3, 7, request, user, service)
        self.assertEqual(context.exception.status_code, 422)

    @staticmethod
    def _route_permission(route) -> PermissionCode:
        def permissions_for(dependency) -> set[PermissionCode]:
            found = {
                cell.cell_contents
                for cell in (getattr(dependency.call, "__closure__", None) or [])
                if isinstance(cell.cell_contents, PermissionCode)
            }
            for nested_dependency in dependency.dependencies:
                found.update(permissions_for(nested_dependency))
            return found

        permissions = set()
        for dependency in route.dependant.dependencies:
            permissions.update(permissions_for(dependency))
        if len(permissions) != 1:
            raise AssertionError(f"Expected one permission dependency for {route.path}")
        return permissions.pop()

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
        self.assertIn(
            {"AegisAI access token": []},
            document_paths["/retrieval/search"]["post"]["security"],
        )
        self.assertIn(
            {"OAuth2PasswordBearer": []},
            document_paths["/chat/stream"]["post"]["security"],
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
            rbac_api.create_role(RoleCreateRequest(name="reader"), service, current_user=SimpleNamespace(id=7)),
            role,
        )
        self.assertEqual(rbac_api.delete_role(1, service, current_user=SimpleNamespace(id=7)).status_code, 204)
        self.assertEqual(rbac_api.list_role_permissions(1, service), ["role-permission"])
        self.assertEqual(rbac_api.grant_role_permission(1, 2, service, current_user=SimpleNamespace(id=7)), "role-permission")
        self.assertEqual(rbac_api.revoke_role_permission(1, 2, service, current_user=SimpleNamespace(id=7)).status_code, 204)
        self.assertEqual(rbac_api.list_user_roles(1, service), ["user-role"])
        self.assertEqual(rbac_api.assign_user_role(1, 2, service, current_user=SimpleNamespace(id=7)), "user-role")
        self.assertEqual(rbac_api.remove_user_role(1, 2, service, current_user=SimpleNamespace(id=7)).status_code, 204)

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
        policy = Mock()
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
        policy.list_readable_documents.return_value = SimpleNamespace(
            items=[document],
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
        page = documents_api.list_documents(0, 25, user, policy)
        self.assertEqual([item.id for item in page.items], [document.id])
        self.assertEqual(page.items[0].title, document.title)
        self.assertEqual(page.offset, 0)
        self.assertEqual(page.limit, 25)
        self.assertEqual(page.total, 1)
        policy.list_readable_documents.assert_called_once_with(
            user_id=user.id,
            offset=0,
            limit=25,
        )
        self.assertIs(documents_api.get_document(3, service, user), document)
        service.get_document.assert_called_once_with(3, audit_actor_user_id=user.id)
        self.assertIs(
            documents_api.rename_document(
                3,
                DocumentRenameRequest(title="Updated title"),
                service,
                user,
            ),
            document,
        )
        service.rename_document.assert_called_once_with(
            3,
            "Updated title",
            actor_user_id=user.id,
        )
        self.assertEqual(documents_api.delete_document(3, service, user).status_code, 204)
        service.delete_document.assert_called_once_with(3, actor_user_id=user.id)

        service.upload.side_effect = DocumentValidationError()
        with self.assertRaises(HTTPException) as context:
            documents_api.upload_document(upload, user, service)
        self.assertEqual(context.exception.status_code, 422)

        service.get_document.side_effect = DocumentNotFoundError()
        with self.assertRaises(HTTPException) as context:
            documents_api.get_document(3, service, user)
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
        user = SimpleNamespace(id=7)
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

        self.assertIs(documents_api.get_document_extraction(3, service, user), extraction)
        page = documents_api.list_document_chunks(3, 0, 25, service, user)
        self.assertEqual([item.id for item in page.items], [chunk.id])
        self.assertEqual(page.total, 1)
        self.assertIs(documents_api.reprocess_document(3, service, user), job)

        service.get_extraction.side_effect = DocumentExtractionNotFoundError()
        with self.assertRaises(HTTPException) as context:
            documents_api.get_document_extraction(3, service, user)
        self.assertEqual(context.exception.status_code, 404)
