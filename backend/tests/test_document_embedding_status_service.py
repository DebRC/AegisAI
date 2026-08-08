from datetime import datetime, timezone
import unittest

from app.core.exceptions import DocumentNotFoundError
from app.core.config import Settings
from app.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentExtraction, DocumentStatus
from app.services.document_embedding_status_service import DocumentEmbeddingStatusService
from app.services.processing_job_service import ProcessingJobService
from tests.helpers import DatabaseTestCase


class DocumentEmbeddingStatusServiceTests(DatabaseTestCase, unittest.TestCase):
    _REQUIRED_SETTINGS = {
        "APP_NAME": "AegisAI",
        "APP_VERSION": "test",
        "APP_ENV": "test",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "QDRANT_URL": "http://qdrant:6333",
        "JWT_SECRET_KEY": "test-secret",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
    }

    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.document = Document(
            uploader_user_id=self.user.id,
            title="Policy",
            original_filename="policy.txt",
            content_type="text/plain",
            size_bytes=6,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000071",
            status=DocumentStatus.READY,
        )
        self.session.add(self.document)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_reports_not_started_for_a_document_without_extracted_chunks(self) -> None:
        status = self._service().get_status(self.document.id)

        self.assertEqual(status.total_chunks, 0)
        self.assertEqual(status.indexed_chunks, 0)
        self.assertEqual(status.indexing_status, "not_started")
        self.assertEqual(status.indexing_attempt_count, 0)
        self.assertIsNone(status.indexing_error)
        self.assertEqual(status.cleanup_pending_count, 0)

    def test_reports_safe_failed_progress_and_pending_cleanup_from_authoritative_rows(self) -> None:
        self.document.extraction = DocumentExtraction(
            normalized_text="Policy",
            text_sha256="b" * 64,
            character_count=6,
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content="Policy",
                    content_sha256="c" * 64,
                    start_offset=0,
                    end_offset=6,
                ),
                DocumentChunk(
                    ordinal=1,
                    content="Second",
                    content_sha256="d" * 64,
                    start_offset=7,
                    end_offset=13,
                ),
            ],
        )
        self.session.commit()
        self.session.add(
            DocumentChunkEmbedding(
                document_chunk_id=self.document.extraction.chunks[0].id,
                provider="openai",
                model="text-embedding-3-small",
                collection_name="aegis_document_chunks_v1",
                point_id="de97bf07-e934-4573-baaa-3688e8cf845b",
                vector_dimension=1536,
                content_sha256="c" * 64,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        jobs = ProcessingJobService(self.session)
        indexing_job = jobs.create_embedding_indexing_job(document_id=self.document.id)
        self.session.commit()
        jobs.claim_embedding_indexing_job(job_id=indexing_job.id)
        jobs.fail_embedding_indexing_job(
            job_id=indexing_job.id,
            safe_error="Document vectors could not be indexed.",
        )
        jobs.queue_vector_cleanup_for_document(document_id=self.document.id)
        self.session.commit()

        status = self._service().get_status(self.document.id)

        self.assertEqual(status.total_chunks, 2)
        self.assertEqual(status.indexed_chunks, 1)
        self.assertEqual(status.indexing_status, "failed")
        self.assertEqual(status.indexing_attempt_count, 1)
        self.assertEqual(status.indexing_error, "Document vectors could not be indexed.")
        self.assertEqual(status.cleanup_pending_count, 1)

    def test_hides_deleted_or_missing_documents(self) -> None:
        self.document.deleted_at = datetime.now(timezone.utc)
        self.session.commit()

        with self.assertRaises(DocumentNotFoundError):
            self._service().get_status(self.document.id)

    def _service(self) -> DocumentEmbeddingStatusService:
        return DocumentEmbeddingStatusService(
            self.session,
            Settings(**self._REQUIRED_SETTINGS),
        )
