import hashlib
from datetime import datetime
from datetime import timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID
from unittest.mock import patch

from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentValidationError
from app.models import Document
from app.models import AuditEvent
from app.models import AuditEventOutcome
from app.models import AuditEventType
from app.models import DocumentChunk
from app.models import DocumentExtraction
from app.models import DocumentStatus
from app.models import DocumentChunkEmbedding
from app.models import ProcessingJob
from app.models import VectorCleanupRequest
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.schemas.document import DocumentResponse
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

    def test_document_response_omits_internal_storage_key(self) -> None:
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

        response = DocumentResponse.model_validate(document)

        self.assertNotIn("storage_key", response.model_dump())


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
        self.assertEqual(repository.count_active(), 1)

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


class DocumentServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temporary_directory.name)
        self.storage = LocalDocumentStorage(self.root_path, maximum_bytes=1024)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()
        self.tear_down_database()

    def test_upload_stores_matching_metadata_and_original_bytes(self) -> None:
        document = DocumentService(self.session, self.storage).upload(
            uploader_user_id=self.user.id,
            original_filename="team-policy.md",
            content_type="text/markdown; charset=utf-8",
            chunks=[b"AegisAI policy"],
        )

        self.assertEqual(document.title, "team-policy")
        self.assertEqual(document.original_filename, "team-policy.md")
        self.assertEqual(document.content_type, "text/markdown")
        self.assertEqual(document.status, DocumentStatus.PENDING)
        self.assertEqual(document.size_bytes, len(b"AegisAI policy"))
        self.assertEqual(
            document.sha256,
            hashlib.sha256(b"AegisAI policy").hexdigest(),
        )
        self.assertEqual(
            (self.root_path / document.storage_key).read_bytes(),
            b"AegisAI policy",
        )

    def test_upload_records_uploader_provenance_without_resource_acl(self) -> None:
        uploader = self.create_user("uploader@example.com")
        service = DocumentService(self.session, self.storage)

        document = service.upload(
            uploader_user_id=uploader.id,
            original_filename="team-policy.txt",
            content_type="text/plain",
            chunks=[b"policy"],
        )

        self.assertEqual(document.uploader_user_id, uploader.id)
        self.assertEqual(document.uploader, uploader)
        self.assertEqual(DocumentResponse.model_validate(document).uploader_user_id, uploader.id)

    def test_upload_rejects_invalid_metadata_before_writing_bytes(self) -> None:
        service = DocumentService(self.session, self.storage)

        with self.assertRaises(DocumentValidationError):
            service.upload(
                uploader_user_id=self.user.id,
                original_filename="malware.exe",
                content_type="application/octet-stream",
                chunks=[b"not stored"],
            )

        self.assertEqual(list((self.root_path / "documents").iterdir()), [])
        self.assertEqual(self.session.query(Document).count(), 0)

    def test_upload_cleans_up_when_metadata_flush_fails(self) -> None:
        service = DocumentService(self.session, self.storage)

        with patch.object(
            service.documents,
            "create",
            side_effect=RuntimeError("database flush failed"),
        ):
            with self.assertRaises(DocumentPersistenceError):
                service.upload(
                    uploader_user_id=self.user.id,
                    original_filename="security-policy.txt",
                    content_type="text/plain",
                    chunks=[b"sensitive policy"],
                )

        self.assertEqual(self.session.query(Document).count(), 0)
        self.assertEqual(list((self.root_path / "documents").iterdir()), [])

    def test_upload_rolls_back_metadata_and_removes_bytes_when_commit_fails(self) -> None:
        service = DocumentService(self.session, self.storage)

        with patch.object(self.session, "commit", side_effect=RuntimeError("database down")):
            with self.assertRaises(DocumentPersistenceError):
                service.upload(
                    uploader_user_id=self.user.id,
                    original_filename="security-policy.txt",
                    content_type="text/plain",
                    chunks=[b"sensitive policy"],
                )

        self.assertEqual(self.session.query(Document).count(), 0)
        self.assertEqual(list((self.root_path / "documents").iterdir()), [])

    def test_list_and_get_return_only_active_document_metadata(self) -> None:
        service = DocumentService(self.session, self.storage)
        first = self._upload(service, "first.txt")
        second = self._upload(service, "second.txt")
        third = self._upload(service, "third.txt")

        first_page = service.list_documents(offset=0, limit=2)
        second_page = service.list_documents(offset=2, limit=2)

        self.assertEqual(first_page.items, [third, second])
        self.assertEqual(first_page.total, 3)
        self.assertEqual(second_page.items, [first])
        self.assertEqual(second_page.offset, 2)
        with self.assertRaises(DocumentNotFoundError):
            service.get_document(9999)

    def test_document_metadata_read_records_safe_best_effort_telemetry(self) -> None:
        service = DocumentService(self.session, self.storage)
        document = self._upload(service, "security-policy.txt")

        service.get_document(document.id, audit_actor_user_id=self.user.id)

        events = self.session.query(AuditEvent).order_by(AuditEvent.id).all()
        self.assertEqual(events[-1].event_type, AuditEventType.DOCUMENT_READ)
        self.assertEqual(events[-1].outcome, AuditEventOutcome.SUCCEEDED)
        self.assertEqual(events[-1].actor_user_id, self.user.id)
        self.assertEqual(events[-1].target_id, document.id)
        self.assertEqual(events[-1].metadata_, {})

    def test_rename_and_delete_update_visibility_and_storage(self) -> None:
        service = DocumentService(self.session, self.storage)
        document = self._upload(service, "security-policy.txt")
        stored_path = self.root_path / document.storage_key

        renamed = service.rename_document(
            document.id,
            " Updated policy ",
            actor_user_id=self.user.id,
        )
        service.delete_document(document.id, actor_user_id=self.user.id)

        self.assertEqual(renamed.title, "Updated policy")
        self.assertIsNotNone(document.deleted_at)
        self.assertFalse(stored_path.exists())
        self.assertEqual(service.list_documents(offset=0, limit=25).items, [])
        with self.assertRaises(DocumentNotFoundError):
            service.get_document(document.id)

        events = self.session.query(AuditEvent).order_by(AuditEvent.id).all()
        self.assertEqual(
            [event.event_type for event in events],
            [
                AuditEventType.DOCUMENT_UPLOADED,
                AuditEventType.DOCUMENT_RENAMED,
                AuditEventType.DOCUMENT_DELETED,
            ],
        )
        self.assertTrue(all(event.outcome == AuditEventOutcome.SUCCEEDED for event in events))
        self.assertTrue(all(event.actor_user_id == self.user.id for event in events))
        self.assertTrue(all(event.target_id == document.id for event in events))
        self.assertEqual(events[0].metadata_, {"content_type": "text/plain"})
        self.assertEqual(events[1].metadata_, {})
        self.assertEqual(events[2].metadata_, {})

    def test_delete_hides_metadata_when_best_effort_storage_cleanup_fails(self) -> None:
        service = DocumentService(self.session, self.storage)
        document = self._upload(service, "security-policy.txt")

        with patch.object(service.storage, "delete", side_effect=DocumentStorageError()):
            service.delete_document(document.id)

        self.assertIsNotNone(document.deleted_at)
        with self.assertRaises(DocumentNotFoundError):
            service.get_document(document.id)

    def test_delete_removes_extracted_output_with_document_metadata(self) -> None:
        service = DocumentService(self.session, self.storage)
        document = self._upload(service, "security-policy.txt")
        self.session.add(
            DocumentExtraction(
                document_id=document.id,
                normalized_text="Security policy",
                text_sha256="a" * 64,
                character_count=15,
                extractor_version="phase8-v1",
                extracted_at=datetime.now(timezone.utc),
                chunks=[
                    DocumentChunk(
                        ordinal=0,
                        content="Security policy",
                        content_sha256="a" * 64,
                        start_offset=0,
                        end_offset=15,
                    )
                ],
            )
        )
        self.session.commit()
        extraction = self.session.query(DocumentExtraction).one()
        self.session.add(
            DocumentChunkEmbedding(
                document_chunk_id=extraction.chunks[0].id,
                provider="openai",
                model="text-embedding-3-small",
                collection_name="retired_collection",
                point_id="10c4d748-1db2-477f-bf4c-47e72ef76e2c",
                vector_dimension=1536,
                content_sha256="a" * 64,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

        service.delete_document(document.id)

        self.assertEqual(self.session.query(DocumentExtraction).count(), 0)
        self.assertEqual(self.session.query(DocumentChunk).count(), 0)
        cleanup_job = self.session.query(ProcessingJob).filter_by(
            document_id=document.id,
            job_type="vector_cleanup",
        ).one()
        cleanup_request = self.session.query(VectorCleanupRequest).filter_by(
            processing_job_id=cleanup_job.id,
        ).one()
        self.assertEqual(cleanup_request.point_ids, ["10c4d748-1db2-477f-bf4c-47e72ef76e2c"])

    def test_rename_rejects_blank_title(self) -> None:
        service = DocumentService(self.session, self.storage)
        document = self._upload(service, "security-policy.txt")

        with self.assertRaises(DocumentValidationError):
            service.rename_document(document.id, "  ")

    def _upload(self, service: DocumentService, filename: str) -> Document:
        return service.upload(
            uploader_user_id=self.user.id,
            original_filename=filename,
            content_type="text/plain",
            chunks=[filename.encode()],
        )
