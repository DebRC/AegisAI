from datetime import datetime, timezone
import unittest

from app.models import Document, DocumentChunk, DocumentChunkEmbedding, DocumentExtraction, ProcessingJobStatus, VectorCleanupRequest
from app.services.processing_job_service import ProcessingJobService
from app.services.vector_cleanup_service import VectorCleanupService
from tests.helpers import DatabaseTestCase


class FakeVectorStore:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.deleted_point_ids: list[str] = []
        self.closed = False

    def delete_points(self, point_ids: list[str]) -> int:
        if self.should_fail:
            raise RuntimeError("transport details must not escape")
        self.deleted_point_ids.extend(point_ids)
        return len(point_ids)

    def close(self) -> None:
        self.closed = True


class VectorCleanupServiceTests(DatabaseTestCase, unittest.TestCase):
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
            storage_key="documents/00000000-0000-0000-0000-000000000044",
        )
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
                )
            ],
        )
        self.session.add(self.document)
        self.session.commit()
        self.embedding = DocumentChunkEmbedding(
            document_chunk_id=self.document.extraction.chunks[0].id,
            provider="openai",
            model="text-embedding-3-small",
            collection_name="retired_collection",
            point_id="22fcad55-cf0b-429a-85f4-78f09f605dc4",
            vector_dimension=1536,
            content_sha256="c" * 64,
            indexed_at=datetime.now(timezone.utc),
        )
        self.session.add(self.embedding)
        self.session.commit()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_deletes_stale_points_and_marks_the_request_complete(self) -> None:
        job = self._queue_cleanup_job()
        vector_store = FakeVectorStore()
        requested_collections: list[str] = []
        service = VectorCleanupService(
            self.session,
            lambda collection: requested_collections.append(collection) or vector_store,
        )

        self.assertEqual(service.process(job.id), "succeeded")
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(requested_collections, ["retired_collection"])
        self.assertEqual(vector_store.deleted_point_ids, [self.embedding.point_id])
        self.assertTrue(vector_store.closed)
        request = self.session.query(VectorCleanupRequest).one()
        self.assertIsNotNone(request.completed_at)

        self.assertEqual(service.process(job.id), "succeeded")
        self.assertEqual(vector_store.deleted_point_ids, [self.embedding.point_id])

    def test_cleanup_failure_is_safe_and_retryable_without_changing_document_state(self) -> None:
        job = self._queue_cleanup_job()
        vector_store = FakeVectorStore(should_fail=True)
        service = VectorCleanupService(self.session, lambda _collection: vector_store)

        self.assertEqual(service.process(job.id), "failed")
        self.assertEqual(job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(job.error_message, "Document vectors could not be removed.")
        self.assertTrue(vector_store.closed)

        retried = ProcessingJobService(self.session).retry_failed_job(
            document_id=self.document.id,
            job_id=job.id,
        )
        self.assertEqual(retried.status, ProcessingJobStatus.QUEUED)

    def _queue_cleanup_job(self):
        jobs = ProcessingJobService(self.session).queue_vector_cleanup_for_document(
            document_id=self.document.id
        )
        self.session.commit()
        self.assertEqual(len(jobs), 1)
        return jobs[0]
