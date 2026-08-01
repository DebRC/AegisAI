"""Validated, payload-safe Qdrant collection and point operations."""

from dataclasses import dataclass
import math
from typing import Sequence
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.core.config import Settings
from app.integrations.vector_store.exceptions import VectorStoreConfigurationError
from app.integrations.vector_store.exceptions import VectorStoreOperationError


_PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("document_id", models.PayloadSchemaType.INTEGER),
    ("chunk_id", models.PayloadSchemaType.INTEGER),
    ("document_extraction_id", models.PayloadSchemaType.INTEGER),
    ("uploader_user_id", models.PayloadSchemaType.INTEGER),
    ("content_type", models.PayloadSchemaType.KEYWORD),
    ("embedding_provider", models.PayloadSchemaType.KEYWORD),
    ("embedding_model", models.PayloadSchemaType.KEYWORD),
)


@dataclass(frozen=True)
class QdrantVectorPoint:
    """One validated derived point with the only payload fields AegisAI permits."""

    point_id: str
    vector: tuple[float, ...]
    document_id: int
    chunk_id: int
    document_extraction_id: int
    uploader_user_id: int
    content_type: str
    embedding_provider: str
    embedding_model: str

    def __post_init__(self) -> None:
        try:
            normalized_point_id = str(UUID(self.point_id))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Qdrant point_id must be a UUID") from error

        if not self.vector:
            raise ValueError("Qdrant vectors must not be empty")
        normalized_vector: list[float] = []
        for value in self.vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Qdrant vector values must be finite numbers")
            normalized_vector.append(float(value))

        for field_name in (
            "document_id",
            "chunk_id",
            "document_extraction_id",
            "uploader_user_id",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")

        for field_name in ("content_type", "embedding_provider", "embedding_model"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        object.__setattr__(self, "point_id", normalized_point_id)
        object.__setattr__(self, "vector", tuple(normalized_vector))

    @property
    def payload(self) -> dict[str, int | str]:
        """Return the explicit allow-list of safe retrieval metadata."""
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "document_extraction_id": self.document_extraction_id,
            "uploader_user_id": self.uploader_user_id,
            "content_type": self.content_type,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
        }


class QdrantVectorStore:
    """Own the compatible collection contract and idempotent point operations."""

    def __init__(self, client: QdrantClient, configuration: Settings) -> None:
        self._client = client
        self._collection_name = configuration.QDRANT_COLLECTION_NAME
        self._vector_dimension = configuration.EMBEDDING_VECTOR_DIMENSION

    def ensure_collection(self) -> None:
        """Create and validate the active collection without mutating mismatches."""
        try:
            exists = self._client.collection_exists(self._collection_name)
        except Exception as error:
            raise VectorStoreOperationError("Document-vector storage is unavailable.") from error

        if not exists:
            self._create_collection_if_absent()

        try:
            collection = self._client.get_collection(self._collection_name)
        except Exception as error:
            raise VectorStoreOperationError("Document-vector storage is unavailable.") from error

        self._validate_collection(collection.config.params.vectors)
        self._ensure_payload_indexes()

    def upsert_points(self, points: Sequence[QdrantVectorPoint]) -> int:
        """Upsert validated vectors under deterministic caller-provided UUIDs."""
        if not points:
            return 0

        for point in points:
            if len(point.vector) != self._vector_dimension:
                raise VectorStoreConfigurationError(
                    "An embedding vector does not match the configured collection dimension."
                )

        self.ensure_collection()
        try:
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    models.PointStruct(id=point.point_id, vector=list(point.vector), payload=point.payload)
                    for point in points
                ],
                wait=True,
            )
        except Exception as error:
            raise VectorStoreOperationError("Document vectors could not be indexed.") from error
        return len(points)

    def delete_points(self, point_ids: Sequence[str]) -> int:
        """Delete known derived vectors without creating an otherwise unused collection."""
        if not point_ids:
            return 0

        normalized_point_ids = [self._normalize_point_id(point_id) for point_id in point_ids]
        try:
            if not self._client.collection_exists(self._collection_name):
                return 0
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(points=normalized_point_ids),
                wait=True,
            )
        except Exception as error:
            raise VectorStoreOperationError("Document vectors could not be removed.") from error
        return len(normalized_point_ids)

    def _create_collection_if_absent(self) -> None:
        try:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=self._vector_dimension,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as error:
            # Another worker may have created the same collection after the
            # initial existence check. Validate that winner rather than ever
            # deleting or replacing it.
            try:
                exists_now = self._client.collection_exists(self._collection_name)
            except Exception:
                exists_now = False
            if not exists_now:
                raise VectorStoreOperationError("Document-vector storage is unavailable.") from error

    def _validate_collection(self, vectors: object) -> None:
        if not isinstance(vectors, models.VectorParams):
            raise VectorStoreConfigurationError(
                "The configured Qdrant collection has an incompatible vector schema."
            )
        if vectors.size != self._vector_dimension or vectors.distance != models.Distance.COSINE:
            raise VectorStoreConfigurationError(
                "The configured Qdrant collection does not match the active embedding configuration."
            )

    def _ensure_payload_indexes(self) -> None:
        for field_name, field_schema in _PAYLOAD_INDEXES:
            try:
                self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
            except Exception as error:
                raise VectorStoreOperationError("Document-vector storage is unavailable.") from error

    @staticmethod
    def _normalize_point_id(point_id: str) -> str:
        try:
            return str(UUID(point_id))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Qdrant point_id must be a UUID") from error
