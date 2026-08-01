from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.models import Document, DocumentStatus, ProcessingJobStatus, ProcessingOutboxEventStatus
from app.services.processing_job_dispatcher import ProcessingJobDispatcher
from app.services.processing_job_service import ProcessingJobService
from app.workers.tasks import _publish_processing_job
from tests.helpers import DatabaseTestCase


class ProcessingJobTests(DatabaseTestCase, unittest.TestCase):
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
            storage_key="documents/00000000-0000-0000-0000-000000000001",
        )
        self.session.add(self.document)
        self.session.commit()
        self.now = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_create_claim_duplicate_delivery_and_complete(self) -> None:
        service = ProcessingJobService(self.session)
        job = service.create_source_integrity_job(document_id=self.document.id, now=self.now)
        self.session.commit()
        self.assertEqual(job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(job.outbox_events[0].status, ProcessingOutboxEventStatus.PENDING)

        self.assertTrue(service.claim_job(job_id=job.id, now=self.now).claimed)
        self.assertFalse(service.claim_job(job_id=job.id, now=self.now).claimed)
        completed = service.complete_job(job_id=job.id, now=self.now)
        self.assertEqual(completed.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(completed.attempt_count, 1)

    def test_source_success_atomically_queues_text_extraction(self) -> None:
        service = ProcessingJobService(self.session)
        source_job = service.create_source_integrity_job(
            document_id=self.document.id,
            now=self.now,
        )
        self.session.commit()
        self.assertTrue(
            service.claim_job(
                job_id=source_job.id,
                now=self.now,
                expected_job_type=ProcessingJobService.SOURCE_INTEGRITY_JOB_TYPE,
            ).claimed
        )

        extraction_job = service.complete_source_integrity_job(
            job_id=source_job.id,
            now=self.now,
        )

        self.assertEqual(source_job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(extraction_job.job_type, ProcessingJobService.TEXT_EXTRACTION_JOB_TYPE)
        self.assertEqual(extraction_job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(extraction_job.outbox_events[0].status, ProcessingOutboxEventStatus.PENDING)
        self.assertEqual(extraction_job.document_id, self.document.id)

    def test_embedding_failure_and_retry_keep_extracted_document_ready(self) -> None:
        self.document.status = DocumentStatus.READY
        self.session.commit()
        service = ProcessingJobService(self.session)
        job = service.create_embedding_indexing_job(document_id=self.document.id, now=self.now)
        self.session.commit()
        self.assertTrue(
            service.claim_embedding_indexing_job(job_id=job.id, now=self.now).claimed
        )

        failed = service.fail_embedding_indexing_job(
            job_id=job.id,
            safe_error="Document vectors could not be indexed.",
            now=self.now,
        )
        self.assertEqual(failed.status, ProcessingJobStatus.FAILED)
        self.assertEqual(failed.document.status.value, "ready")

        retried = service.retry_failed_job(document_id=self.document.id, job_id=job.id, now=self.now)
        self.assertEqual(retried.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(retried.document.status.value, "ready")

    @patch("app.workers.tasks.run_embedding_indexing.delay")
    def test_embedding_indexing_jobs_are_routed_to_the_dedicated_worker_task(self, delay) -> None:
        delay.return_value.id = "embedding-task-1"

        task_id = _publish_processing_job(
            ProcessingJobService.EMBEDDING_INDEXING_JOB_TYPE,
            processing_job_id=42,
        )

        self.assertEqual(task_id, "embedding-task-1")
        delay.assert_called_once_with(42)

    def test_failure_retry_and_cancellation(self) -> None:
        service = ProcessingJobService(self.session)
        job = service.create_source_integrity_job(document_id=self.document.id, now=self.now)
        self.session.commit()
        service.claim_job(job_id=job.id, now=self.now)
        failed = service.fail_job(job_id=job.id, safe_error="Source is unavailable.", now=self.now)
        self.assertEqual(failed.status, ProcessingJobStatus.FAILED)
        self.assertEqual(failed.document.status.value, "failed")

        retried = service.retry_failed_job(document_id=self.document.id, job_id=job.id, now=self.now)
        self.assertEqual(retried.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(len(retried.outbox_events), 2)
        service.cancel_document_jobs(document_id=self.document.id, now=self.now)
        self.session.commit()
        self.assertEqual(retried.status, ProcessingJobStatus.CANCELLED)
        self.assertTrue(all(event.status == ProcessingOutboxEventStatus.CANCELLED for event in retried.outbox_events))

    def test_dispatcher_marks_success_and_reschedules_broker_failure(self) -> None:
        service = ProcessingJobService(self.session)
        success_job = service.create_source_integrity_job(document_id=self.document.id, now=self.now)
        extraction_job = service.create_text_extraction_job(
            document_id=self.document.id,
            now=self.now,
        )
        self.session.commit()
        dispatched: list[tuple[str, int]] = []
        dispatcher = ProcessingJobDispatcher(
            self.session,
            lambda job_type, job_id: dispatched.append((job_type, job_id)) or f"task-{job_id}",
        )
        summary = dispatcher.dispatch_pending(now=self.now)
        self.assertEqual((summary.published, summary.deferred), (2, 0))
        self.assertEqual(success_job.outbox_events[0].status, ProcessingOutboxEventStatus.PUBLISHED)
        self.assertEqual(extraction_job.outbox_events[0].status, ProcessingOutboxEventStatus.PUBLISHED)
        self.assertEqual(
            dispatched,
            [
                (ProcessingJobService.SOURCE_INTEGRITY_JOB_TYPE, success_job.id),
                (ProcessingJobService.TEXT_EXTRACTION_JOB_TYPE, extraction_job.id),
            ],
        )

        failed_job = service.create_source_integrity_job(document_id=self.document.id, now=self.now)
        self.session.commit()
        failing_dispatcher = ProcessingJobDispatcher(
            self.session,
            lambda _job_type, _job_id: (_ for _ in ()).throw(RuntimeError()),
        )
        summary = failing_dispatcher.dispatch_pending(now=self.now)
        self.assertEqual((summary.published, summary.deferred), (0, 1))
        event = failed_job.outbox_events[0]
        self.assertEqual(event.status, ProcessingOutboxEventStatus.PENDING)
        self.assertIsNotNone(event.last_error)
