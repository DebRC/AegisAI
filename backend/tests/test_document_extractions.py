import hashlib
from datetime import datetime, timezone
import unittest

from sqlalchemy.exc import IntegrityError

from app.models import Document
from app.models import DocumentChunk
from app.models import DocumentChunkEmbedding
from app.models import DocumentExtraction
from tests.helpers import DatabaseTestCase


class DocumentExtractionModelTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.document = self._document("8")
        self.session.add(self.document)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_persists_one_traceable_extraction_with_ordered_chunks(self) -> None:
        normalized_text = "Security policy\n\nAccess controls"
        extraction = DocumentExtraction(
            document_id=self.document.id,
            normalized_text=normalized_text,
            text_sha256=hashlib.sha256(normalized_text.encode()).hexdigest(),
            character_count=len(normalized_text),
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=1,
                    content="Access controls",
                    content_sha256=hashlib.sha256(b"Access controls").hexdigest(),
                    start_offset=17,
                    end_offset=32,
                    source_locations=[{"kind": "page", "index": 2}],
                ),
                DocumentChunk(
                    ordinal=0,
                    content="Security policy",
                    content_sha256=hashlib.sha256(b"Security policy").hexdigest(),
                    start_offset=0,
                    end_offset=15,
                    source_locations=[{"kind": "page", "index": 1}],
                ),
            ],
        )
        self.session.add(extraction)
        self.session.commit()

        self.session.refresh(self.document)

        self.assertEqual(self.document.extraction, extraction)
        self.assertEqual(extraction.character_count, len(normalized_text))
        self.assertEqual([chunk.ordinal for chunk in extraction.chunks], [0, 1])
        self.assertEqual(extraction.chunks[0].source_locations, [{"kind": "page", "index": 1}])

    def test_enforces_one_current_extraction_and_valid_chunk_ranges(self) -> None:
        self.session.add(self._extraction(self.document))
        self.session.commit()

        self.session.add(self._extraction(self.document))
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        second_document = self._document("9")
        self.session.add(second_document)
        self.session.commit()
        invalid_extraction = self._extraction(second_document)
        invalid_extraction.chunks[0].ordinal = -1
        invalid_extraction.chunks[0].end_offset = 0
        self.session.add(invalid_extraction)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_deleting_an_extraction_deletes_its_chunks(self) -> None:
        extraction = self._extraction(self.document)
        self.session.add(extraction)
        self.session.commit()

        self.session.add(
            DocumentChunkEmbedding(
                document_chunk_id=extraction.chunks[0].id,
                provider="openai",
                model="text-embedding-3-small",
                collection_name="aegis_document_chunks_v1",
                point_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                vector_dimension=1536,
                content_sha256=extraction.chunks[0].content_sha256,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

        self.session.delete(extraction)
        self.session.commit()

        self.assertEqual(self.session.query(DocumentChunk).count(), 0)
        self.assertEqual(self.session.query(DocumentChunkEmbedding).count(), 0)
        self.session.refresh(self.document)
        self.assertIsNone(self.document.extraction)

    def test_persists_one_traceable_embedding_per_chunk_and_index_identity(self) -> None:
        extraction = self._extraction(self.document)
        self.session.add(extraction)
        self.session.commit()
        chunk = extraction.chunks[0]
        embedding = DocumentChunkEmbedding(
            document_chunk_id=chunk.id,
            provider="openai",
            model="text-embedding-3-small",
            collection_name="aegis_document_chunks_v1",
            point_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            vector_dimension=1536,
            content_sha256=chunk.content_sha256,
            indexed_at=datetime.now(timezone.utc),
        )
        self.session.add(embedding)
        self.session.commit()

        self.session.refresh(chunk)

        self.assertEqual(chunk.embeddings, [embedding])
        self.assertEqual(embedding.chunk, chunk)
        self.assertEqual(embedding.content_sha256, chunk.content_sha256)

        self.session.add(
            DocumentChunkEmbedding(
                document_chunk_id=chunk.id,
                provider="openai",
                model="text-embedding-3-small",
                collection_name="aegis_document_chunks_v1",
                point_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                vector_dimension=1536,
                content_sha256=chunk.content_sha256,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        invalid = DocumentChunkEmbedding(
            document_chunk_id=chunk.id,
            provider="openai",
            model="text-embedding-3-small",
            collection_name="aegis_document_chunks_v1",
            point_id="too-short",
            vector_dimension=0,
            content_sha256=chunk.content_sha256,
            indexed_at=datetime.now(timezone.utc),
        )
        self.session.add(invalid)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def _document(self, suffix: str) -> Document:
        return Document(
            uploader_user_id=self.user.id,
            title=f"Security policy {suffix}",
            original_filename=f"security-policy-{suffix}.txt",
            content_type="text/plain",
            size_bytes=10,
            sha256="a" * 64,
            storage_key=f"documents/00000000-0000-0000-0000-00000000000{suffix}",
        )

    @staticmethod
    def _extraction(document: Document) -> DocumentExtraction:
        return DocumentExtraction(
            document_id=document.id,
            normalized_text="Valid text",
            text_sha256="b" * 64,
            character_count=10,
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content="Valid text",
                    content_sha256="b" * 64,
                    start_offset=0,
                    end_offset=10,
                )
            ],
        )
