from datetime import datetime, timezone
import unittest

from app.models import Document, ProcessingJobStatus, ProcessingOutboxEventStatus
from app.services.processing_job_dispatcher import ProcessingJobDispatcher
from app.services.processing_job_service import ProcessingJobService
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
        self.session.commit()
        dispatcher = ProcessingJobDispatcher(self.session, lambda job_id: f"task-{job_id}")
        summary = dispatcher.dispatch_pending(now=self.now)
        self.assertEqual((summary.published, summary.deferred), (1, 0))
        self.assertEqual(success_job.outbox_events[0].status, ProcessingOutboxEventStatus.PUBLISHED)

        failed_job = service.create_source_integrity_job(document_id=self.document.id, now=self.now)
        self.session.commit()
        failing_dispatcher = ProcessingJobDispatcher(self.session, lambda _: (_ for _ in ()).throw(RuntimeError()))
        summary = failing_dispatcher.dispatch_pending(now=self.now)
        self.assertEqual((summary.published, summary.deferred), (0, 1))
        event = failed_job.outbox_events[0]
        self.assertEqual(event.status, ProcessingOutboxEventStatus.PENDING)
        self.assertIsNotNone(event.last_error)
