import unittest
from datetime import datetime
from datetime import timezone

from app.models import Document
from app.models import DocumentAccessGrant
from app.models import DocumentAccessLevel
from app.models import Permission
from app.models import Role
from app.models import RolePermission
from app.models import UserRole
from app.repositories.document_access_grant_repository import DocumentAccessGrantRepository
from app.security.permissions import PermissionCode
from app.services.document_access_policy_service import DocumentAccessPolicyService
from tests.helpers import DatabaseTestCase


class DocumentAccessPolicyServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.owner = self.create_user("owner@example.com")
        self.reader = self.create_user("reader@example.com")
        self.writer = self.create_user("writer@example.com")
        self.viewer = self.create_user("viewer@example.com")
        self.administrator = self.create_user("administrator@example.com")
        self.inactive = self.create_user("inactive@example.com", is_active=False)
        self.owned_document = self._document("owned")
        self.shared_document = self._document("shared")
        self.deleted_document = self._document("deleted")
        self.deleted_document.deleted_at = datetime.now(timezone.utc)
        self.session.add_all(
            [
                DocumentAccessGrant(
                    document_id=self.shared_document.id,
                    user_id=self.reader.id,
                    access_level=DocumentAccessLevel.READ,
                    granted_by_user_id=self.owner.id,
                ),
                DocumentAccessGrant(
                    document_id=self.shared_document.id,
                    user_id=self.writer.id,
                    access_level=DocumentAccessLevel.WRITE,
                    granted_by_user_id=self.owner.id,
                ),
            ]
        )
        self._grant_administrator_override()
        self.session.commit()
        self.service = DocumentAccessPolicyService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_owner_and_direct_grants_have_only_their_expected_access(self) -> None:
        self.assertTrue(self.service.can_read(user_id=self.owner.id, document_id=self.owned_document.id))
        self.assertTrue(self.service.can_write(user_id=self.owner.id, document_id=self.owned_document.id))
        self.assertTrue(self.service.can_read(user_id=self.reader.id, document_id=self.shared_document.id))
        self.assertFalse(self.service.can_write(user_id=self.reader.id, document_id=self.shared_document.id))
        self.assertTrue(self.service.can_read(user_id=self.writer.id, document_id=self.shared_document.id))
        self.assertTrue(self.service.can_write(user_id=self.writer.id, document_id=self.shared_document.id))
        self.assertFalse(self.service.can_read(user_id=self.reader.id, document_id=self.owned_document.id))

    def test_administrator_override_and_deleted_or_inactive_users_are_handled_safely(self) -> None:
        self.assertTrue(self.service.can_read(user_id=self.administrator.id, document_id=self.owned_document.id))
        self.assertTrue(self.service.can_write(user_id=self.administrator.id, document_id=self.owned_document.id))
        self.assertFalse(self.service.can_read(user_id=self.administrator.id, document_id=self.deleted_document.id))
        self.assertFalse(self.service.can_read(user_id=self.inactive.id, document_id=self.shared_document.id))
        self.assertFalse(self.service.can_read(user_id=0, document_id=self.shared_document.id))

    def test_filters_only_active_documents_the_user_can_read_or_write(self) -> None:
        document_ids = [
            self.owned_document.id,
            self.shared_document.id,
            self.deleted_document.id,
            99999,
        ]

        self.assertEqual(
            self.service.readable_document_ids(
                user_id=self.reader.id,
                document_ids=document_ids,
            ),
            {self.shared_document.id},
        )
        self.assertEqual(
            self.service.writable_document_ids(
                user_id=self.writer.id,
                document_ids=document_ids,
            ),
            {self.shared_document.id},
        )
        self.assertEqual(
            self.service.readable_document_ids(
                user_id=self.administrator.id,
                document_ids=document_ids,
            ),
            {self.owned_document.id, self.shared_document.id},
        )

    def test_grant_repository_reads_lists_updates_and_deletes_without_committing(self) -> None:
        repository = DocumentAccessGrantRepository(self.session)
        grant = repository.get_by_document_and_user(
            document_id=self.shared_document.id,
            user_id=self.reader.id,
        )
        self.assertEqual(
            [item.user_id for item in repository.list_by_document_id(self.shared_document.id)],
            [self.reader.id, self.writer.id],
        )

        grant.access_level = DocumentAccessLevel.WRITE
        repository.update()
        self.session.commit()
        self.assertEqual(grant.access_level, DocumentAccessLevel.WRITE)

        created = repository.create(
            DocumentAccessGrant(
                document_id=self.shared_document.id,
                user_id=self.viewer.id,
                access_level=DocumentAccessLevel.READ,
                granted_by_user_id=self.owner.id,
            )
        )
        self.assertEqual(
            repository.get_by_document_and_user(
                document_id=self.shared_document.id,
                user_id=self.viewer.id,
            ),
            created,
        )

        repository.delete(created)
        self.session.commit()
        self.assertIsNone(repository.get_by_document_and_user(
            document_id=self.shared_document.id,
            user_id=self.viewer.id,
        ))

    def _document(self, suffix: str) -> Document:
        document = Document(
            uploader_user_id=self.owner.id,
            title=f"{suffix.title()} document",
            original_filename=f"{suffix}.txt",
            content_type="text/plain",
            size_bytes=5,
            sha256=(suffix[0] * 64),
            storage_key=f"documents/00000000-0000-0000-0000-000000000{len(suffix):03d}",
        )
        self.session.add(document)
        self.session.flush()
        return document

    def _grant_administrator_override(self) -> None:
        permission = Permission(
            code=PermissionCode.DOCUMENTS_MANAGE.value,
            description="Manage documents",
        )
        role = Role(name="document-administrator", description=None)
        self.session.add_all([permission, role])
        self.session.flush()
        self.session.add_all(
            [
                RolePermission(role_id=role.id, permission_id=permission.id),
                UserRole(user_id=self.administrator.id, role_id=role.id),
            ]
        )
