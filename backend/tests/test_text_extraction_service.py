from datetime import datetime, timezone
import unittest

from app.extraction.base import ExtractedText, ExtractedTextBlock, SourceLocation
from app.extraction.exceptions import NoExtractableTextError
from app.extraction.processing import TextChunker, TextNormalizer
from app.extraction.registry import TextExtractorRegistry
from app.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentExtraction, DocumentStatus, ProcessingJob, ProcessingJobStatus, VectorCleanupRequest
from app.services.processing_job_service import ProcessingJobService
from app.services.text_extraction_service import TextExtractionService
from tests.helpers import DatabaseTestCase


class MemoryStorage:
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    def iter_chunks(self, storage_key: str):
        return iter(self.chunks)


class StaticExtractor:
    def __init__(self, result: ExtractedText | Exception):
        self.result = result

    def extract(self, source) -> ExtractedText:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TextExtractionServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.document = Document(
            uploader_user_id=self.user.id,
            title="Security policy",
            original_filename="security-policy.txt",
            content_type="text/plain",
            size_bytes=16,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000010",
        )
        self.session.add(self.document)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_process_persists_chunks_and_advances_to_ready(self) -> None:
        job = self._queued_text_job()
        service = self._service(
            ExtractedText(
                blocks=(
                    ExtractedTextBlock("First paragraph.", SourceLocation("page", 1)),
                    ExtractedTextBlock("Second paragraph.", SourceLocation("page", 2)),
                )
            )
        )

        status = service.process(job.id)

        self.assertEqual(status, "succeeded")
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(self.document.status, DocumentStatus.READY)
        extraction = self.session.query(DocumentExtraction).one()
        self.assertEqual(extraction.document_id, self.document.id)
        self.assertEqual(extraction.normalized_text, "First paragraph.\n\nSecond paragraph.")
        self.assertEqual(extraction.chunks[0].source_locations, [{"kind": "page", "index": 1}])
        self.assertTrue(all(chunk.content_sha256 for chunk in extraction.chunks))
        embedding_job = self.session.query(ProcessingJob).filter_by(
            document_id=self.document.id,
            job_type=ProcessingJobService.EMBEDDING_INDEXING_JOB_TYPE,
        ).one()
        self.assertEqual(embedding_job.status, ProcessingJobStatus.QUEUED)

    def test_process_fails_safely_without_persisting_partial_output(self) -> None:
        job = self._queued_text_job()
        service = self._service(NoExtractableTextError())

        status = service.process(job.id)

        self.assertEqual(status, "failed")
        self.assertEqual(job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(self.document.status, DocumentStatus.FAILED)
        self.assertEqual(self.document.processing_error, "No extractable text was found in this document.")
        self.assertEqual(self.session.query(DocumentExtraction).count(), 0)

    def test_process_replaces_existing_output_in_one_current_extraction(self) -> None:
        old_extraction = DocumentExtraction(
            document_id=self.document.id,
            normalized_text="Old text",
            text_sha256="b" * 64,
            character_count=8,
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content="Old text",
                    content_sha256="b" * 64,
                    start_offset=0,
                    end_offset=8,
                )
            ],
        )
        self.session.add(old_extraction)
        self.document.status = DocumentStatus.READY
        self.session.commit()
        self.session.add(
            DocumentChunkEmbedding(
                document_chunk_id=old_extraction.chunks[0].id,
                provider="openai",
                model="text-embedding-3-small",
                collection_name="retired_collection",
                point_id="cc38c86d-a5b7-4c25-98cf-759291d7fbc9",
                vector_dimension=1536,
                content_sha256="b" * 64,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()
        job = self._queued_text_job()
        service = self._service(ExtractedText(blocks=(ExtractedTextBlock("New policy text"),)))

        self.assertEqual(service.process(job.id), "succeeded")
        self.assertEqual(self.session.query(DocumentExtraction).count(), 1)
        self.assertEqual(self.session.query(DocumentExtraction).one().normalized_text, "New policy text")
        self.assertEqual(self.document.status, DocumentStatus.READY)
        cleanup_request = self.session.query(VectorCleanupRequest).one()
        self.assertEqual(cleanup_request.collection_name, "retired_collection")
        self.assertEqual(cleanup_request.point_ids, ["cc38c86d-a5b7-4c25-98cf-759291d7fbc9"])

    def test_deleted_document_is_cancelled_without_reading_source(self) -> None:
        job = self._queued_text_job()
        self.document.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        service = self._service(ExtractedText(blocks=(ExtractedTextBlock("unused"),)))

        self.assertEqual(service.process(job.id), "cancelled")
        self.assertEqual(job.status, ProcessingJobStatus.CANCELLED)
        self.assertEqual(self.document.status, DocumentStatus.PENDING)

    def _queued_text_job(self):
        job = ProcessingJobService(self.session).create_text_extraction_job(
            document_id=self.document.id
        )
        self.session.commit()
        return job

    def _service(self, result: ExtractedText | Exception) -> TextExtractionService:
        return TextExtractionService(
            self.session,
            MemoryStorage([b"source bytes"]),
            TextExtractorRegistry(
                100,
                plain_text_extractor=StaticExtractor(result),
            ),
            TextNormalizer(),
            TextChunker(target_characters=20, overlap_characters=4),
            maximum_characters=100,
        )
