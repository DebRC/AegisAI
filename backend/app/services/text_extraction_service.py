"""Worker-facing orchestration for durable Phase 8 text extraction."""

from tempfile import SpooledTemporaryFile

from sqlalchemy.orm import Session

from app.extraction.exceptions import ExtractedTextLimitExceededError
from app.extraction.exceptions import NoExtractableTextError
from app.extraction.exceptions import TextExtractionError
from app.extraction.processing import TextChunker
from app.extraction.processing import TextNormalizer
from app.extraction.registry import TextExtractorRegistry
from app.models.document import Document
from app.services.processing_job_service import ProcessingJobService
from app.storage.documents import DocumentStorage
from app.storage.documents import DocumentStorageError


class TextExtractionService:
    """Claim, transform, and persist one text-extraction job without Celery."""

    def __init__(
        self,
        db: Session,
        storage: DocumentStorage,
        extractors: TextExtractorRegistry,
        normalizer: TextNormalizer,
        chunker: TextChunker,
        maximum_characters: int,
    ):
        if (
            not isinstance(maximum_characters, int)
            or isinstance(maximum_characters, bool)
            or maximum_characters < 1
        ):
            raise ValueError("maximum_characters must be a positive integer")
        self.db = db
        self.storage = storage
        self.extractors = extractors
        self.normalizer = normalizer
        self.chunker = chunker
        self.maximum_characters = maximum_characters
        self.jobs = ProcessingJobService(db)

    def process(self, processing_job_id: int) -> str:
        """Run one idempotent extraction attempt and return its safe status."""
        claim = self.jobs.claim_text_extraction_job(job_id=processing_job_id)
        if not claim.claimed:
            return claim.job.status.value

        document = self.db.get(Document, claim.job.document_id)
        if document is None or document.deleted_at is not None:
            return self._cancel(processing_job_id)

        try:
            normalized_text, chunks = self._extract_and_chunk(document)
        except DocumentStorageError:
            return self._fail(
                processing_job_id,
                "The stored source document could not be read.",
            )
        except NoExtractableTextError:
            return self._fail(
                processing_job_id,
                "No extractable text was found in this document.",
            )
        except ExtractedTextLimitExceededError:
            return self._fail(
                processing_job_id,
                "Extracted text exceeds the processing limit.",
            )
        except TextExtractionError:
            return self._fail(
                processing_job_id,
                "Text could not be extracted from this document.",
            )
        except (OSError, ValueError):
            return self._fail(
                processing_job_id,
                "Text could not be extracted from this document.",
            )

        try:
            self.jobs.complete_text_extraction_job(
                job_id=processing_job_id,
                normalized_text=normalized_text,
                chunks=chunks,
            )
        except Exception:
            return self._fail(
                processing_job_id,
                "Extracted document content could not be saved.",
            )
        return "succeeded"

    def _extract_and_chunk(self, document: Document):
        # Keep small sources in memory, but spill larger allowed uploads to a
        # temporary file instead of requiring the worker to retain all bytes.
        with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as source:
            for chunk in self.storage.iter_chunks(document.storage_key):
                source.write(chunk)
            source.seek(0)
            extracted_text = self.extractors.extract(
                content_type=document.content_type,
                source=source,
            )
        normalized_text = self.normalizer.normalize(extracted_text)
        if len(normalized_text.text) > self.maximum_characters:
            raise ExtractedTextLimitExceededError()
        return normalized_text, self.chunker.chunk(normalized_text)

    def _fail(self, processing_job_id: int, safe_error: str) -> str:
        try:
            self.jobs.fail_job(job_id=processing_job_id, safe_error=safe_error)
        except Exception:
            return "cancelled"
        return "failed"

    def _cancel(self, processing_job_id: int) -> str:
        try:
            self.jobs.cancel_running_job(job_id=processing_job_id)
        except Exception:
            return "cancelled"
        return "cancelled"
