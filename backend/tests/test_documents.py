import hashlib
from datetime import datetime
from datetime import timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from app.models import Document
from app.models import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.storage.documents import EmptyDocumentError
from app.storage.documents import DocumentStorageError
from app.storage.documents import LocalDocumentStorage
from app.storage.documents import StorageLimitExceededError
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


class DocumentRepositoryTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_repository_creates_lists_and_excludes_deleted_documents(self) -> None:
        repository = DocumentRepository(self.session)
        active = repository.create(self._document("active"))
        deleted = repository.create(self._document("deleted"))
        deleted.deleted_at = datetime.now(timezone.utc)
        repository.update()
        self.session.commit()

        self.assertEqual(repository.get_by_id(deleted.id), deleted)
        self.assertIsNone(repository.get_active_by_id(deleted.id))
        self.assertEqual(repository.get_active_by_id(active.id), active)
        self.assertEqual(repository.list_active(offset=0, limit=10), [active])

    def _document(self, suffix: str) -> Document:
        return Document(
            uploader_user_id=self.user.id,
            title=f"Document {suffix}",
            original_filename=f"document-{suffix}.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256="a" * 64,
            storage_key=f"documents/00000000-0000-0000-0000-0000000000{len(suffix):02d}",
        )


class LocalDocumentStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_store_streams_content_with_server_generated_key_and_digest(self) -> None:
        storage = LocalDocumentStorage(self.root_path, maximum_bytes=1024)

        stored = storage.store([b"Aegis", b"AI"])

        self.assertEqual(stored.size_bytes, 7)
        self.assertEqual(stored.sha256, hashlib.sha256(b"AegisAI").hexdigest())
        self.assertTrue(stored.storage_key.startswith("documents/"))
        UUID(stored.storage_key.removeprefix("documents/"))
        self.assertEqual(
            (self.root_path / stored.storage_key).read_bytes(),
            b"AegisAI",
        )
        self.assertEqual(list((self.root_path / "documents").glob(".upload-*")), [])

    def test_store_rejects_empty_and_oversized_content_without_leaving_files(self) -> None:
        storage = LocalDocumentStorage(self.root_path, maximum_bytes=3)

        with self.assertRaises(EmptyDocumentError):
            storage.store([])
        with self.assertRaises(StorageLimitExceededError):
            storage.store([b"four"])

        self.assertEqual(list((self.root_path / "documents").iterdir()), [])

    def test_store_removes_temporary_file_when_content_stream_fails(self) -> None:
        storage = LocalDocumentStorage(self.root_path, maximum_bytes=1024)

        def failing_chunks():
            yield b"first chunk"
            raise RuntimeError("stream disconnected")

        with self.assertRaises(DocumentStorageError):
            storage.store(failing_chunks())

        self.assertEqual(list((self.root_path / "documents").iterdir()), [])

    def test_delete_is_idempotent_and_rejects_untrusted_storage_keys(self) -> None:
        storage = LocalDocumentStorage(self.root_path, maximum_bytes=1024)
        stored = storage.store([b"document"])

        storage.delete(stored.storage_key)
        storage.delete(stored.storage_key)

        self.assertFalse((self.root_path / stored.storage_key).exists())
        with self.assertRaises(ValueError):
            storage.delete("../../outside-the-storage-root")
