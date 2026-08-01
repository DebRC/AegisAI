from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentExtraction


class DocumentExtractionRepository:
    """Persistence boundary for one document's current extraction result."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_document_id(self, document_id: int) -> DocumentExtraction | None:
        return self.db.scalar(
            select(DocumentExtraction).where(DocumentExtraction.document_id == document_id)
        )

    def replace(self, extraction: DocumentExtraction) -> DocumentExtraction:
        """Replace old output in the caller's transaction, never append it."""
        existing = self.get_by_document_id(extraction.document_id)
        if existing is not None:
            self.db.delete(existing)
            self.db.flush()
        self.db.add(extraction)
        self.db.flush()
        self.db.refresh(extraction)
        return extraction

    def delete_by_document_id(self, document_id: int) -> bool:
        extraction = self.get_by_document_id(document_id)
        if extraction is None:
            return False
        self.db.delete(extraction)
        self.db.flush()
        return True

    def list_chunks_by_document_id(
        self,
        *,
        document_id: int,
        offset: int,
        limit: int,
    ) -> list[DocumentChunk]:
        return list(
            self.db.scalars(
                select(DocumentChunk)
                .join(DocumentExtraction)
                .where(DocumentExtraction.document_id == document_id)
                .order_by(DocumentChunk.ordinal)
                .offset(offset)
                .limit(limit)
            )
        )

    def count_chunks_by_document_id(self, document_id: int) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(DocumentExtraction)
            .where(DocumentExtraction.document_id == document_id)
        ) or 0
