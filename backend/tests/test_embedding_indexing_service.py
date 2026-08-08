from datetime import datetime, timezone
import unittest

from app.core.config import Settings
from app.embeddings.base import EmbeddingBatch
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.integrations.vector_store.qdrant_store import QdrantVectorPoint
from app.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentExtraction, DocumentStatus, ProcessingJobStatus
from app.services.embedding_indexing_service import EmbeddingIndexingService
from app.services.processing_job_service import ProcessingJobService
from tests.helpers import DatabaseTestCase


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.requests: list[list[str]] = []
        self.closed = False

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        self.requests.append(list(texts))
        return EmbeddingBatch(
            provider="openai",
            model="text-embedding-3-small",
            vectors=tuple((float(index + 1), 0.0, 1.0) for index in range(len(texts))),
        )

    def close(self) -> None:
        self.closed = True


class FakeVectorStore:
    def __init__(self) -> None:
        self.batches: list[list[QdrantVectorPoint]] = []
        self.closed = False

    def upsert_points(self, points: list[QdrantVectorPoint]) -> int:
        self.batches.append(points)
        return len(points)

    def close(self) -> None:
        self.closed = True


class EmbeddingIndexingServiceTests(DatabaseTestCase, unittest.TestCase):
    _REQUIRED_SETTINGS = {
        "APP_NAME": "AegisAI",
        "APP_VERSION": "test",
        "APP_ENV": "test",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_COLLECTION_NAME": "unit_test_vectors",
        "EMBEDDING_VECTOR_DIMENSION": 3,
        "EMBEDDING_BATCH_SIZE": 1,
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
            size_bytes=10,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000099",
            status=DocumentStatus.READY,
        )
        self.document.extraction = DocumentExtraction(
            normalized_text="First text\n\nSecond text",
            text_sha256="b" * 64,
            character_count=23,
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content="First text",
                    content_sha256="c" * 64,
                    start_offset=0,
                    end_offset=10,
                ),
                DocumentChunk(
                    ordinal=1,
                    content="Second text",
                    content_sha256="d" * 64,
                    start_offset=12,
                    end_offset=23,
                ),
            ],
        )
        self.session.add(self.document)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_indexes_batches_persists_traceability_and_is_idempotent(self) -> None:
        job = self._queued_job()
        provider = FakeEmbeddingProvider()
        vector_store = FakeVectorStore()

        service = self._service(lambda: provider, lambda: vector_store)

        self.assertEqual(service.process(job.id), "succeeded")
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(self.document.status, DocumentStatus.READY)
        self.assertEqual(provider.requests, [["First text"], ["Second text"]])
        self.assertTrue(provider.closed)
        self.assertTrue(vector_store.closed)
        self.assertEqual(len(vector_store.batches), 2)
        self.assertTrue(all(len(batch) == 1 for batch in vector_store.batches))

        embeddings = self.session.query(DocumentChunkEmbedding).order_by(DocumentChunkEmbedding.document_chunk_id).all()
        self.assertEqual(len(embeddings), 2)
        self.assertEqual({embedding.provider for embedding in embeddings}, {"openai"})
        self.assertEqual({embedding.model for embedding in embeddings}, {"text-embedding-3-small"})
        self.assertEqual({embedding.collection_name for embedding in embeddings}, {"unit_test_vectors"})
        self.assertEqual({embedding.vector_dimension for embedding in embeddings}, {3})
        self.assertEqual(
            {embedding.content_sha256 for embedding in embeddings},
            {"c" * 64, "d" * 64},
        )
        self.assertEqual(
            vector_store.batches[0][0].payload["document_extraction_id"],
            self.document.extraction.id,
        )

        self.assertEqual(service.process(job.id), "succeeded")
        self.assertEqual(len(vector_store.batches), 2)
        self.assertEqual(self.session.query(DocumentChunkEmbedding).count(), 2)

    def test_provider_configuration_failure_is_safe_and_keeps_text_ready(self) -> None:
        job = self._queued_job()
        vector_store = FakeVectorStore()

        service = self._service(
            lambda: (_ for _ in ()).throw(EmbeddingProviderConfigurationError("missing key")),
            lambda: vector_store,
        )

        self.assertEqual(service.process(job.id), "failed")
        self.assertEqual(job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(job.error_message, "Embedding provider configuration is unavailable.")
        self.assertEqual(self.document.status, DocumentStatus.READY)
        self.assertEqual(self.session.query(DocumentChunkEmbedding).count(), 0)
        self.assertFalse(vector_store.closed)

    def _queued_job(self):
        job = ProcessingJobService(self.session).create_embedding_indexing_job(
            document_id=self.document.id
        )
        self.session.commit()
        return job

    def _service(self, create_provider, create_vector_store) -> EmbeddingIndexingService:
        return EmbeddingIndexingService(
            self.session,
            Settings(**self._REQUIRED_SETTINGS),
            create_provider,
            create_vector_store,
        )
