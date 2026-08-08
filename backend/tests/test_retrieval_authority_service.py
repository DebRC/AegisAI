from datetime import datetime, timezone
import hashlib
import unittest

from app.core.config import Settings
from app.integrations.vector_store.qdrant_store import QdrantSearchCandidate
from app.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentExtraction, DocumentStatus
from app.services.retrieval_authority_service import RetrievalAuthorityService
from tests.helpers import DatabaseTestCase


class RetrievalAuthorityServiceTests(DatabaseTestCase, unittest.TestCase):
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
        self.document, self.extraction, self.chunk, self.embedding = self._create_indexed_document()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_resolves_current_rows_and_preserves_qdrant_score(self) -> None:
        candidate = self._candidate()

        resolved = self._service().resolve(candidates=[candidate])

        self.assertEqual(len(resolved), 1)
        self.assertIs(resolved[0].document, self.document)
        self.assertIs(resolved[0].extraction, self.extraction)
        self.assertIs(resolved[0].chunk, self.chunk)
        self.assertIs(resolved[0].embedding, self.embedding)
        self.assertEqual(resolved[0].candidate.score, 0.87)

    def test_discards_stale_deleted_mismatched_and_payload_inconsistent_candidates(self) -> None:
        payload_mismatch = QdrantSearchCandidate(
            point_id=self.embedding.point_id,
            score=0.88,
            payload=self._candidate().payload | {"document_id": self.document.id + 100},
        )
        self.assertEqual(self._service().resolve(candidates=[payload_mismatch]), [])

        stale = QdrantSearchCandidate(
            point_id=self.embedding.point_id,
            score=0.87,
            payload=self._candidate().payload | {"chunk_id": self.chunk.id + 100},
        )
        wrong_identity = QdrantSearchCandidate(
            point_id=self.embedding.point_id,
            score=0.86,
            payload=self._candidate().payload | {"embedding_model": "old-model"},
        )
        self.embedding.content_sha256 = "f" * 64
        self.session.commit()
        self.assertEqual(self._service().resolve(candidates=[stale, wrong_identity]), [])

        self.embedding.content_sha256 = self.chunk.content_sha256
        self.document.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        self.assertEqual(self._service().resolve(candidates=[self._candidate()]), [])

    def test_applies_document_and_content_type_filters_against_postgres(self) -> None:
        candidate = self._candidate()

        self.assertEqual(
            len(self._service().resolve(candidates=[candidate], document_ids=[self.document.id])),
            1,
        )
        self.assertEqual(
            self._service().resolve(candidates=[candidate], document_ids=[999]),
            [],
        )
        self.assertEqual(
            self._service().resolve(candidates=[candidate], content_types=["application/pdf"]),
            [],
        )

    def _service(self) -> RetrievalAuthorityService:
        return RetrievalAuthorityService(self.session, Settings(**self._REQUIRED_SETTINGS))

    def _candidate(self) -> QdrantSearchCandidate:
        return QdrantSearchCandidate(
            point_id=self.embedding.point_id,
            score=0.87,
            payload={
                "document_id": self.document.id,
                "chunk_id": self.chunk.id,
                "document_extraction_id": self.extraction.id,
                "uploader_user_id": self.document.uploader_user_id,
                "content_type": self.document.content_type,
                "embedding_provider": self.embedding.provider,
                "embedding_model": self.embedding.model,
            },
        )

    def _create_indexed_document(self):
        document = Document(
            uploader_user_id=self.user.id,
            title="Policy",
            original_filename="policy.txt",
            content_type="text/plain",
            size_bytes=10,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000091",
            status=DocumentStatus.READY,
        )
        normalized_text = "Current policy"
        extraction = DocumentExtraction(
            normalized_text=normalized_text,
            text_sha256=hashlib.sha256(normalized_text.encode()).hexdigest(),
            character_count=len(normalized_text),
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content=normalized_text,
                    content_sha256=hashlib.sha256(normalized_text.encode()).hexdigest(),
                    start_offset=0,
                    end_offset=len(normalized_text),
                )
            ],
        )
        document.extraction = extraction
        self.session.add(document)
        self.session.commit()
        chunk = extraction.chunks[0]
        embedding = DocumentChunkEmbedding(
            document_chunk_id=chunk.id,
            provider="openai",
            model="text-embedding-3-small",
            collection_name="aegis_document_chunks_v1",
            point_id="d911e79c-97e2-4b68-8974-803034fc62ca",
            vector_dimension=1536,
            content_sha256=chunk.content_sha256,
            indexed_at=datetime.now(timezone.utc),
        )
        self.session.add(embedding)
        self.session.commit()
        return document, extraction, chunk, embedding
