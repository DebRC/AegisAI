import hashlib
from datetime import datetime, timezone
import unittest

from app.core.exceptions import DocumentExtractionNotFoundError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import ProcessingJobStateError
from app.models import Document
from app.models import AuditEvent
from app.models import AuditEventType
from app.models import DocumentChunk
from app.models import DocumentExtraction
from app.models import DocumentStatus
from app.models import ProcessingJobStatus
from app.models import ProcessingOutboxEventStatus
from app.services.document_extraction_query_service import DocumentExtractionQueryService
from app.services.processing_job_service import ProcessingJobService
from tests.helpers import DatabaseTestCase


class DocumentExtractionQueryServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.document = Document(
            uploader_user_id=self.user.id,
            title="Security policy",
            original_filename="security-policy.txt",
            content_type="text/plain",
            size_bytes=22,
            sha256="a" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000008",
            status=DocumentStatus.READY,
        )
        self.session.add(self.document)
        self.session.commit()
        self.extraction = self._add_extraction(self.document)
        self.service = DocumentExtractionQueryService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_returns_metadata_and_a_bounded_ordered_chunk_page(self) -> None:
        extraction = self.service.get_extraction(self.document.id)
        page = self.service.list_chunks(
            document_id=self.document.id,
            offset=1,
            limit=1,
        )

        self.assertEqual(extraction.id, self.extraction.id)
        self.assertEqual(page.total, 2)
        self.assertEqual([chunk.ordinal for chunk in page.items], [1])
        self.assertEqual(page.items[0].content, "Access controls")

    def test_hides_deleted_documents_and_distinguishes_missing_output(self) -> None:
        self.document.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        with self.assertRaises(DocumentNotFoundError):
            self.service.get_extraction(self.document.id)

        new_document = Document(
            uploader_user_id=self.user.id,
            title="No output",
            original_filename="no-output.txt",
            content_type="text/plain",
            size_bytes=9,
            sha256="b" * 64,
            storage_key="documents/00000000-0000-0000-0000-000000000009",
            status=DocumentStatus.PENDING,
        )
        self.session.add(new_document)
        self.session.commit()
        with self.assertRaises(DocumentExtractionNotFoundError):
            self.service.get_extraction(new_document.id)

    def test_reprocess_queues_one_text_job_and_preserves_ready_state(self) -> None:
        job = self.service.request_reprocessing(
            self.document.id,
            actor_user_id=self.user.id,
        )

        self.assertEqual(job.job_type, ProcessingJobService.TEXT_EXTRACTION_JOB_TYPE)
        self.assertEqual(job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(job.outbox_events[0].status, ProcessingOutboxEventStatus.PENDING)
        self.assertEqual(self.document.status, DocumentStatus.READY)
        self.assertEqual(self.service.get_extraction(self.document.id).id, self.extraction.id)
        event = self.session.query(AuditEvent).one()
        self.assertEqual(event.event_type, AuditEventType.DOCUMENT_REPROCESS_QUEUED)
        self.assertEqual(event.actor_user_id, self.user.id)
        self.assertEqual(event.target_id, self.document.id)
        self.assertEqual(event.metadata_, {})

        with self.assertRaises(ProcessingJobStateError):
            self.service.request_reprocessing(self.document.id)

    def test_reprocess_requires_an_active_ready_document(self) -> None:
        self.document.status = DocumentStatus.FAILED
        self.session.commit()
        with self.assertRaises(ProcessingJobStateError):
            self.service.request_reprocessing(self.document.id)

        self.document.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        with self.assertRaises(DocumentNotFoundError):
            self.service.request_reprocessing(self.document.id)

    def _add_extraction(self, document: Document) -> DocumentExtraction:
        text = "Security policy\n\nAccess controls"
        extraction = DocumentExtraction(
            document_id=document.id,
            normalized_text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            character_count=len(text),
            extractor_version="phase8-v1",
            extracted_at=datetime.now(timezone.utc),
            chunks=[
                DocumentChunk(
                    ordinal=0,
                    content="Security policy",
                    content_sha256=hashlib.sha256(b"Security policy").hexdigest(),
                    start_offset=0,
                    end_offset=15,
                ),
                DocumentChunk(
                    ordinal=1,
                    content="Access controls",
                    content_sha256=hashlib.sha256(b"Access controls").hexdigest(),
                    start_offset=17,
                    end_offset=32,
                    source_locations=[{"kind": "paragraph", "index": 2}],
                ),
            ],
        )
        self.session.add(extraction)
        self.session.commit()
        return extraction
