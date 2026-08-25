from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentExtractionNotFoundError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentValidationError
from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentExtraction
from app.repositories.document_extraction_repository import DocumentExtractionRepository
from app.repositories.document_repository import DocumentRepository
from app.services.processing_job_service import ProcessingJobService


@dataclass(frozen=True)
class DocumentChunkPage:
    """A bounded, ordered page of an extraction's chunks."""

    items: list[DocumentChunk]
    offset: int
    limit: int
    total: int


class DocumentExtractionQueryService:
    """Read durable extraction output and request safe replacement processing."""

    def __init__(self, db: Session):
        self.documents = DocumentRepository(db)
        self.extractions = DocumentExtractionRepository(db)
        self.processing_jobs = ProcessingJobService(db)

    def get_extraction(self, document_id: int) -> DocumentExtraction:
        self._get_active_document_id(document_id)
        extraction = self.extractions.get_by_document_id(document_id)
        if extraction is None:
            raise DocumentExtractionNotFoundError()
        return extraction

    def list_chunks(
        self,
        *,
        document_id: int,
        offset: int,
        limit: int,
    ) -> DocumentChunkPage:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise DocumentValidationError()
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise DocumentValidationError()
        self.get_extraction(document_id)
        return DocumentChunkPage(
            items=self.extractions.list_chunks_by_document_id(
                document_id=document_id,
                offset=offset,
                limit=limit,
            ),
            offset=offset,
            limit=limit,
            total=self.extractions.count_chunks_by_document_id(document_id),
        )

    def request_reprocessing(self, document_id: int, *, actor_user_id: int | None = None):
        self._get_active_document_id(document_id)
        return self.processing_jobs.request_text_reprocessing(
            document_id=document_id,
            actor_user_id=actor_user_id,
        )

    def _get_active_document_id(self, document_id: int) -> int:
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document.id
