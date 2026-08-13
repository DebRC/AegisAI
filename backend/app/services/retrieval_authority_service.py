"""Validate Qdrant candidates against PostgreSQL's authoritative state."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.vector_store.qdrant_store import QdrantSearchCandidate
from app.models.document import Document
from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentChunkEmbedding
from app.models.document_extraction import DocumentExtraction
from app.repositories.document_chunk_embedding_repository import DocumentChunkEmbeddingRepository


@dataclass(frozen=True)
class AuthoritativeRetrievalCandidate:
    """A Qdrant score paired with current, relationally verified source rows."""

    candidate: QdrantSearchCandidate
    document: Document
    extraction: DocumentExtraction
    chunk: DocumentChunk
    embedding: DocumentChunkEmbedding


class RetrievalAuthorityService:
    """Discard stale, deleted, mismatched, or payload-inconsistent candidates."""

    def __init__(self, db: Session, configuration: Settings):
        self.configuration = configuration
        self.embeddings = DocumentChunkEmbeddingRepository(db)

    def resolve(
        self,
        *,
        candidates: list[QdrantSearchCandidate],
        document_ids: list[int] | None = None,
        content_types: list[str] | None = None,
    ) -> list[AuthoritativeRetrievalCandidate]:
        """Return candidates whose Qdrant identity and PostgreSQL state agree."""
        records = self.embeddings.resolve_current_by_point_ids(
            point_ids=[candidate.point_id for candidate in candidates],
            provider=self.configuration.EMBEDDING_PROVIDER,
            model=self.configuration.EMBEDDING_MODEL,
            collection_name=self.configuration.QDRANT_COLLECTION_NAME,
            vector_dimension=self.configuration.EMBEDDING_VECTOR_DIMENSION,
            document_ids=document_ids,
            content_types=content_types,
        )
        resolved: list[AuthoritativeRetrievalCandidate] = []
        for candidate in candidates:
            record = records.get(candidate.point_id)
            if record is None:
                continue
            document, extraction, chunk, embedding = record
            expected_payload = {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "document_extraction_id": extraction.id,
                "uploader_user_id": document.uploader_user_id,
                "content_type": document.content_type,
                "embedding_provider": embedding.provider,
                "embedding_model": embedding.model,
            }
            if any(candidate.payload.get(field) != value for field, value in expected_payload.items()):
                continue
            resolved.append(
                AuthoritativeRetrievalCandidate(
                    candidate=candidate,
                    document=document,
                    extraction=extraction,
                    chunk=chunk,
                    embedding=embedding,
                )
            )
        return resolved
