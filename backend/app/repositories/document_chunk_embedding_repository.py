"""Persistence operations for derived document-chunk embedding pointers."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document import DocumentStatus
from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentExtraction
from app.models.document_extraction import DocumentChunkEmbedding


class DocumentChunkEmbeddingRepository:
    """Store one current Qdrant-point pointer per embedding identity."""

    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, embeddings: list[DocumentChunkEmbedding]) -> None:
        """Persist idempotent records after their deterministic Qdrant upserts."""
        for embedding in embeddings:
            existing = self.db.scalar(
                select(DocumentChunkEmbedding).where(
                    DocumentChunkEmbedding.document_chunk_id == embedding.document_chunk_id,
                    DocumentChunkEmbedding.provider == embedding.provider,
                    DocumentChunkEmbedding.model == embedding.model,
                    DocumentChunkEmbedding.collection_name == embedding.collection_name,
                )
            )
            if existing is None:
                self.db.add(embedding)
                continue
            existing.point_id = embedding.point_id
            existing.vector_dimension = embedding.vector_dimension
            existing.content_sha256 = embedding.content_sha256
            existing.indexed_at = embedding.indexed_at
        self.db.flush()

    def list_by_document_id(self, document_id: int) -> list[DocumentChunkEmbedding]:
        """Return current derived pointers before a document extraction is replaced."""
        from app.models.document_extraction import DocumentChunk
        from app.models.document_extraction import DocumentExtraction

        return list(
            self.db.scalars(
                select(DocumentChunkEmbedding)
                .join(DocumentChunk)
                .join(DocumentExtraction)
                .where(DocumentExtraction.document_id == document_id)
            )
        )

    def count_current_chunks_by_document_id(
        self,
        *,
        document_id: int,
        provider: str,
        model: str,
        collection_name: str,
    ) -> int:
        """Count current chunks indexed by the active provider/model/collection."""
        from app.models.document_extraction import DocumentChunk
        from app.models.document_extraction import DocumentExtraction

        return self.db.scalar(
            select(func.count(func.distinct(DocumentChunkEmbedding.document_chunk_id)))
            .join(DocumentChunk)
            .join(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == document_id,
                DocumentChunkEmbedding.provider == provider,
                DocumentChunkEmbedding.model == model,
                DocumentChunkEmbedding.collection_name == collection_name,
            )
        ) or 0

    def resolve_current_by_point_ids(
        self,
        *,
        point_ids: list[str],
        provider: str,
        model: str,
        collection_name: str,
        vector_dimension: int,
        document_ids: list[int] | None = None,
        content_types: list[str] | None = None,
    ) -> dict[str, tuple[Document, DocumentExtraction, DocumentChunk, DocumentChunkEmbedding]]:
        """Resolve only current, active PostgreSQL rows for Qdrant point IDs."""
        if not point_ids:
            return {}

        conditions = [
            DocumentChunkEmbedding.point_id.in_(point_ids),
            DocumentChunkEmbedding.provider == provider,
            DocumentChunkEmbedding.model == model,
            DocumentChunkEmbedding.collection_name == collection_name,
            DocumentChunkEmbedding.vector_dimension == vector_dimension,
            DocumentChunkEmbedding.content_sha256 == DocumentChunk.content_sha256,
            Document.deleted_at.is_(None),
            Document.status == DocumentStatus.READY,
        ]
        if document_ids is not None:
            conditions.append(Document.id.in_(document_ids))
        if content_types is not None:
            conditions.append(Document.content_type.in_(content_types))

        rows = self.db.execute(
            select(Document, DocumentExtraction, DocumentChunk, DocumentChunkEmbedding)
            .join(DocumentExtraction, DocumentExtraction.document_id == Document.id)
            .join(DocumentChunk, DocumentChunk.document_extraction_id == DocumentExtraction.id)
            .join(DocumentChunkEmbedding, DocumentChunkEmbedding.document_chunk_id == DocumentChunk.id)
            .where(*conditions)
        ).all()
        return {embedding.point_id: (document, extraction, chunk, embedding) for document, extraction, chunk, embedding in rows}
