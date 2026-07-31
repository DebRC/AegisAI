import unittest

from app.models import Document
from app.models import DocumentStatus
from tests.helpers import DatabaseTestCase


class DocumentModelTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_document_persists_metadata_with_pending_default_status(self) -> None:
        document = Document(
            uploader_user_id=self.user.id,
            title="Security policy",
            original_filename="security-policy.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000001",
        )
        self.session.add(document)
        self.session.commit()

        self.assertEqual(document.status, DocumentStatus.PENDING)
        self.assertEqual(document.uploader.id, self.user.id)
        self.assertEqual(self.user.uploaded_documents, [document])
        self.assertIsNone(document.deleted_at)
        self.assertIsNone(document.processing_error)
