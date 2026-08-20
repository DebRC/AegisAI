import unittest

from app.core.exceptions import DocumentAccessGranteeInactiveError
from app.core.exceptions import DocumentAccessGrantNotFoundError
from app.core.exceptions import DocumentAccessOwnerGrantError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import UserNotFoundError
from app.models import Document
from app.models import DocumentAccessLevel
from app.models import Permission
from app.models import Role
from app.models import RolePermission
from app.models import UserRole
from app.security.permissions import PermissionCode
from app.services.document_access_grant_service import DocumentAccessGrantService
from tests.helpers import DatabaseTestCase


class DocumentAccessGrantServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.owner = self.create_user("owner@example.com")
        self.writer = self.create_user("writer@example.com")
        self.reader = self.create_user("reader@example.com")
        self.inactive = self.create_user("inactive@example.com", is_active=False)
        self.document = self._document()
        self.service = DocumentAccessGrantService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_owner_can_create_update_list_and_revoke_a_grant(self) -> None:
        created = self.service.upsert_grant(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
            grantee_user_id=self.reader.id,
            access_level=DocumentAccessLevel.READ,
        )
        self.assertEqual(created.access_level, DocumentAccessLevel.READ)
        self.assertEqual(created.granted_by_user_id, self.owner.id)
        self.assertEqual(self.service.list_grants(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
        ), [created])

        updated = self.service.upsert_grant(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
            grantee_user_id=self.reader.id,
            access_level=DocumentAccessLevel.WRITE,
        )
        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.access_level, DocumentAccessLevel.WRITE)

        self.service.revoke_grant(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
            grantee_user_id=self.reader.id,
        )
        self.assertEqual(self.service.list_grants(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
        ), [])

    def test_writer_can_manage_grants_and_administrator_can_override(self) -> None:
        self.service.upsert_grant(
            actor_user_id=self.owner.id,
            document_id=self.document.id,
            grantee_user_id=self.writer.id,
            access_level=DocumentAccessLevel.WRITE,
        )
        created = self.service.upsert_grant(
            actor_user_id=self.writer.id,
            document_id=self.document.id,
            grantee_user_id=self.reader.id,
            access_level=DocumentAccessLevel.READ,
        )
        self.assertEqual(created.granted_by_user_id, self.writer.id)

        administrator = self.create_user("administrator@example.com")
        self._grant_manage_override(administrator.id)
        updated = self.service.upsert_grant(
            actor_user_id=administrator.id,
            document_id=self.document.id,
            grantee_user_id=self.reader.id,
            access_level=DocumentAccessLevel.WRITE,
        )
        self.assertEqual(updated.granted_by_user_id, administrator.id)
        self.assertEqual(updated.access_level, DocumentAccessLevel.WRITE)

    def test_rejects_unknown_inactive_owner_and_unmanageable_grant_operations(self) -> None:
        with self.assertRaises(UserNotFoundError):
            self.service.upsert_grant(
                actor_user_id=self.owner.id,
                document_id=self.document.id,
                grantee_user_id=999,
                access_level=DocumentAccessLevel.READ,
            )
        with self.assertRaises(DocumentAccessGranteeInactiveError):
            self.service.upsert_grant(
                actor_user_id=self.owner.id,
                document_id=self.document.id,
                grantee_user_id=self.inactive.id,
                access_level=DocumentAccessLevel.READ,
            )
        with self.assertRaises(DocumentAccessOwnerGrantError):
            self.service.upsert_grant(
                actor_user_id=self.owner.id,
                document_id=self.document.id,
                grantee_user_id=self.owner.id,
                access_level=DocumentAccessLevel.READ,
            )
        with self.assertRaises(DocumentNotFoundError):
            self.service.list_grants(actor_user_id=self.reader.id, document_id=self.document.id)
        with self.assertRaises(DocumentAccessGrantNotFoundError):
            self.service.revoke_grant(
                actor_user_id=self.owner.id,
                document_id=self.document.id,
                grantee_user_id=self.reader.id,
            )

    def _document(self) -> Document:
        document = Document(
            uploader_user_id=self.owner.id,
            title="Security policy",
            original_filename="policy.txt",
            content_type="text/plain",
            size_bytes=6,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000012",
        )
        self.session.add(document)
        self.session.commit()
        return document

    def _grant_manage_override(self, user_id: int) -> None:
        permission = Permission(
            code=PermissionCode.DOCUMENTS_MANAGE.value,
            description="Manage every document",
        )
        role = Role(name="administrator", description="Administrator", is_system=True)
        self.session.add_all([permission, role])
        self.session.flush()
        self.session.add_all([
            RolePermission(role_id=role.id, permission_id=permission.id),
            UserRole(user_id=user_id, role_id=role.id),
        ])
        self.session.commit()
