import unittest

from sqlalchemy.exc import IntegrityError

from app.models import Document
from app.models import DocumentAccessGrant
from app.models import DocumentAccessLevel
from tests.helpers import DatabaseTestCase


class DocumentAccessGrantModelTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.owner = self.create_user("owner@example.com")
        self.grantee = self.create_user("reader@example.com")
        self.document = Document(
            uploader_user_id=self.owner.id,
            title="Restricted policy",
            original_filename="restricted-policy.txt",
            content_type="text/plain",
            size_bytes=6,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000120",
        )
        self.session.add(self.document)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_persists_one_direct_grant_with_access_and_provenance(self) -> None:
        grant = DocumentAccessGrant(
            document_id=self.document.id,
            user_id=self.grantee.id,
            access_level=DocumentAccessLevel.READ,
            granted_by_user_id=self.owner.id,
        )
        self.session.add(grant)
        self.session.commit()

        self.assertEqual(grant.document, self.document)
        self.assertEqual(grant.grantee, self.grantee)
        self.assertEqual(grant.granted_by, self.owner)
        self.assertEqual(self.document.access_grants, [grant])
        self.assertEqual(self.grantee.document_access_grants, [grant])
        self.assertEqual(self.owner.granted_document_access_grants, [grant])

    def test_rejects_duplicate_grants_for_one_document_and_user(self) -> None:
        self.session.add(
            DocumentAccessGrant(
                document_id=self.document.id,
                user_id=self.grantee.id,
                access_level=DocumentAccessLevel.READ,
                granted_by_user_id=self.owner.id,
            )
        )
        self.session.commit()

        self.session.add(
            DocumentAccessGrant(
                document_id=self.document.id,
                user_id=self.grantee.id,
                access_level=DocumentAccessLevel.WRITE,
                granted_by_user_id=self.owner.id,
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.flush()
        self.session.rollback()
