"""Persistence operations for derived document-chunk embedding pointers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

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
