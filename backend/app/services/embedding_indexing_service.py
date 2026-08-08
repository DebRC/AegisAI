"""Worker-facing orchestration for durable Phase 9 embedding indexing."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.embeddings.exceptions import EmbeddingProviderError
from app.embeddings.exceptions import EmbeddingProviderResponseError
from app.integrations.vector_store.exceptions import VectorStoreConfigurationError
from app.integrations.vector_store.exceptions import VectorStoreOperationError
from app.integrations.vector_store.qdrant_store import QdrantVectorPoint
from app.integrations.vector_store.qdrant_store import QdrantVectorStore
from app.models.document import Document
from app.models.document_extraction import DocumentChunk
from app.models.document_extraction import DocumentChunkEmbedding
from app.repositories.document_extraction_repository import DocumentExtractionRepository
from app.services.processing_job_service import ProcessingJobService


EmbeddingProviderFactory = Callable[[], EmbeddingProvider]
VectorStoreFactory = Callable[[], QdrantVectorStore]


@dataclass(frozen=True)
class _IndexedChunk:
    chunk: DocumentChunk
    point_id: str
    provider: str
    model: str
    vector_dimension: int


class EmbeddingIndexingService:
    """Claim, vectorize, index, and persist one document's current chunks."""

    def __init__(
        self,
        db: Session,
        configuration: Settings,
        create_provider: EmbeddingProviderFactory,
        create_vector_store: VectorStoreFactory,
    ) -> None:
        self.db = db
        self.configuration = configuration
        self.create_provider = create_provider
        self.create_vector_store = create_vector_store
        self.jobs = ProcessingJobService(db)
        self.extractions = DocumentExtractionRepository(db)

    def process(self, processing_job_id: int) -> str:
        """Run one idempotent indexing attempt and return only a safe status."""
        claim = self.jobs.claim_embedding_indexing_job(job_id=processing_job_id)
        if not claim.claimed:
            return claim.job.status.value

        document = self.db.get(Document, claim.job.document_id)
        if document is None or document.deleted_at is not None:
            return self._cancel(processing_job_id)
        extraction = self.extractions.get_by_document_id(document.id)
        if extraction is None or not extraction.chunks:
            return self._fail(processing_job_id, "Current extracted text is unavailable for indexing.")

        provider: EmbeddingProvider | None = None
        vector_store: QdrantVectorStore | None = None
        try:
            provider = self.create_provider()
            vector_store = self.create_vector_store()
            indexed_chunks = self._index_chunks(
                document=document,
                chunks=list(extraction.chunks),
                provider=provider,
                vector_store=vector_store,
            )
            self.jobs.complete_embedding_indexing_job(
                job_id=processing_job_id,
                document_extraction_id=extraction.id,
                embeddings=[
                    DocumentChunkEmbedding(
                        document_chunk_id=indexed.chunk.id,
                        provider=indexed.provider,
                        model=indexed.model,
                        collection_name=self.configuration.QDRANT_COLLECTION_NAME,
                        point_id=indexed.point_id,
                        vector_dimension=indexed.vector_dimension,
                        content_sha256=indexed.chunk.content_sha256,
                        indexed_at=self._now(),
                    )
                    for indexed in indexed_chunks
                ],
            )
        except EmbeddingProviderConfigurationError:
            return self._fail(processing_job_id, "Embedding provider configuration is unavailable.")
        except (EmbeddingProviderError, EmbeddingProviderResponseError):
            return self._fail(processing_job_id, "Embeddings could not be generated for this document.")
        except VectorStoreConfigurationError:
            return self._fail(processing_job_id, "Document-vector storage configuration is invalid.")
        except VectorStoreOperationError:
            return self._fail(processing_job_id, "Document vectors could not be indexed.")
        except Exception:
            return self._fail(processing_job_id, "Document embedding records could not be saved.")
        finally:
            if provider is not None:
                provider.close()
            if vector_store is not None:
                vector_store.close()
        return "succeeded"

    def _index_chunks(
        self,
        *,
        document: Document,
        chunks: list[DocumentChunk],
        provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
    ) -> list[_IndexedChunk]:
        indexed_chunks: list[_IndexedChunk] = []
        for batch in self._batches(chunks):
            embedding_batch = provider.embed([chunk.content for chunk in batch])
            if len(embedding_batch.vectors) != len(batch):
                raise EmbeddingProviderResponseError("Embedding response did not match the input batch")
            if (
                embedding_batch.provider != self.configuration.EMBEDDING_PROVIDER
                or embedding_batch.model != self.configuration.EMBEDDING_MODEL
            ):
                raise EmbeddingProviderResponseError("Embedding response did not match the active provider")
            if embedding_batch.vector_dimension != self.configuration.EMBEDDING_VECTOR_DIMENSION:
                raise EmbeddingProviderResponseError("Embedding response had an unexpected dimension")

            points: list[QdrantVectorPoint] = []
            for chunk, vector in zip(batch, embedding_batch.vectors, strict=True):
                point_id = self._point_id(
                    chunk_id=chunk.id,
                    provider=embedding_batch.provider,
                    model=embedding_batch.model,
                )
                points.append(
                    QdrantVectorPoint(
                        point_id=point_id,
                        vector=vector,
                        document_id=document.id,
                        chunk_id=chunk.id,
                        document_extraction_id=chunk.document_extraction_id,
                        uploader_user_id=document.uploader_user_id,
                        content_type=document.content_type,
                        embedding_provider=embedding_batch.provider,
                        embedding_model=embedding_batch.model,
                    )
                )
                indexed_chunks.append(
                    _IndexedChunk(
                        chunk=chunk,
                        point_id=point_id,
                        provider=embedding_batch.provider,
                        model=embedding_batch.model,
                        vector_dimension=embedding_batch.vector_dimension,
                    )
                )
            vector_store.upsert_points(points)
        return indexed_chunks

    def _batches(self, chunks: list[DocumentChunk]) -> list[list[DocumentChunk]]:
        return [
            chunks[index : index + self.configuration.EMBEDDING_BATCH_SIZE]
            for index in range(0, len(chunks), self.configuration.EMBEDDING_BATCH_SIZE)
        ]

    def _point_id(self, *, chunk_id: int, provider: str, model: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"aegisai:embedding:{self.configuration.QDRANT_COLLECTION_NAME}:{provider}:{model}:chunk:{chunk_id}",
            )
        )

    def _fail(self, processing_job_id: int, safe_error: str) -> str:
        try:
            self.jobs.fail_embedding_indexing_job(
                job_id=processing_job_id,
                safe_error=safe_error,
            )
        except Exception:
            return "cancelled"
        return "failed"

    def _cancel(self, processing_job_id: int) -> str:
        try:
            self.jobs.cancel_running_job(job_id=processing_job_id)
        except Exception:
            return "cancelled"
        return "cancelled"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
