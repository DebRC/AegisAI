"""Validated, payload-safe Qdrant collection and point operations."""

from dataclasses import dataclass
import math
from typing import Mapping, Sequence
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.core.config import Settings
from app.integrations.vector_store.exceptions import VectorStoreConfigurationError
from app.integrations.vector_store.exceptions import VectorStoreOperationError
from app.schemas.retrieval import SUPPORTED_RETRIEVAL_CONTENT_TYPES


_PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("tenant_id", models.PayloadSchemaType.INTEGER),
    ("document_id", models.PayloadSchemaType.INTEGER),
    ("chunk_id", models.PayloadSchemaType.INTEGER),
    ("document_extraction_id", models.PayloadSchemaType.INTEGER),
    ("uploader_user_id", models.PayloadSchemaType.INTEGER),
    ("content_type", models.PayloadSchemaType.KEYWORD),
    ("embedding_provider", models.PayloadSchemaType.KEYWORD),
    ("embedding_model", models.PayloadSchemaType.KEYWORD),
)
_PAYLOAD_FIELDS: tuple[str, ...] = tuple(field_name for field_name, _ in _PAYLOAD_INDEXES)
_MAX_SEARCH_LIMIT = 100


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
    tenant_id: int = 0

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

        if not isinstance(self.tenant_id, int) or self.tenant_id < 0:
            raise ValueError("tenant_id must be a non-negative integer")

        for field_name in ("content_type", "embedding_provider", "embedding_model"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        object.__setattr__(self, "point_id", normalized_point_id)
        object.__setattr__(self, "vector", tuple(normalized_vector))

    @property
    def payload(self) -> dict[str, int | str]:
        """Return the explicit allow-list of safe retrieval metadata."""
        payload: dict[str, int | str] = {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "document_extraction_id": self.document_extraction_id,
            "uploader_user_id": self.uploader_user_id,
            "content_type": self.content_type,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
        }
        if self.tenant_id:
            payload["tenant_id"] = self.tenant_id
        return payload


@dataclass(frozen=True)
class QdrantSearchCandidate:
    """A scored point with only the allow-listed retrieval payload."""

    point_id: str
    score: float
    payload: Mapping[str, int | str]

    def __post_init__(self) -> None:
        try:
            normalized_point_id = str(UUID(self.point_id))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Qdrant search point_id must be a UUID") from error
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
            raise ValueError("Qdrant search scores must be finite numbers")
        normalized_payload = {
            field_name: self.payload[field_name]
            for field_name in _PAYLOAD_FIELDS
            if field_name in self.payload
        }
        object.__setattr__(self, "point_id", normalized_point_id)
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(self, "payload", normalized_payload)


class QdrantVectorStore:
    """Own the compatible collection contract and idempotent point operations."""

    def __init__(
        self,
        client: QdrantClient,
        configuration: Settings,
        *,
        collection_name: str | None = None,
    ) -> None:
        self._client = client
        self._configuration = configuration
        self._collection_name = collection_name or configuration.QDRANT_COLLECTION_NAME
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

    def search(
        self,
        *,
        vector: Sequence[float],
        provider: str,
        model: str,
        limit: int,
        document_ids: Sequence[int] | None = None,
        content_types: Sequence[str] | None = None,
        tenant_id: int | None = None,
    ) -> list[QdrantSearchCandidate]:
        """Return filtered active-identity candidates without creating a collection."""
        if provider != self._configuration_provider or model != self._configuration_model:
            raise VectorStoreConfigurationError(
                "The search embedding identity does not match the active configuration."
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_SEARCH_LIMIT:
            raise ValueError(f"Qdrant search limit must be between 1 and {_MAX_SEARCH_LIMIT}")
        normalized_document_ids = self._normalize_document_filter(document_ids)
        normalized_content_types = self._normalize_content_type_filter(content_types)
        if tenant_id is not None and (isinstance(tenant_id, bool) or not isinstance(tenant_id, int) or tenant_id < 1):
            raise ValueError("tenant_id must be a positive integer")

        normalized_vector = self._normalize_search_vector(vector)
        must_conditions = [
            models.FieldCondition(
                key="embedding_provider",
                match=models.MatchValue(value=provider),
            ),
            models.FieldCondition(
                key="embedding_model",
                match=models.MatchValue(value=model),
            ),
        ]
        if tenant_id is not None:
            must_conditions.append(
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))
            )
        if normalized_document_ids is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=normalized_document_ids),
                )
            )
        if normalized_content_types is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="content_type",
                    match=models.MatchAny(any=normalized_content_types),
                )
            )
        query_filter = models.Filter(must=must_conditions)
        try:
            if not self._client.collection_exists(self._collection_name):
                return []
            collection = self._client.get_collection(self._collection_name)
            self._validate_collection(collection.config.params.vectors)
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=normalized_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=list(_PAYLOAD_FIELDS),
                with_vectors=False,
            )
            return [
                QdrantSearchCandidate(
                    point_id=str(point.id),
                    score=point.score,
                    payload=point.payload or {},
                )
                for point in response.points
            ]
        except VectorStoreConfigurationError:
            raise
        except ValueError as error:
            raise VectorStoreOperationError("Document-vector search returned invalid data.") from error
        except Exception as error:
            raise VectorStoreOperationError("Document-vector storage is unavailable.") from error

    def close(self) -> None:
        """Release the worker-scoped client created for this store."""
        self._client.close()

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

    @property
    def _configuration_provider(self) -> str:
        return self._configuration.EMBEDDING_PROVIDER

    @property
    def _configuration_model(self) -> str:
        return self._configuration.EMBEDDING_MODEL

    def _normalize_search_vector(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self._vector_dimension:
            raise VectorStoreConfigurationError(
                "The search vector does not match the active embedding dimension."
            )
        normalized: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Qdrant search vectors must contain finite numbers")
            normalized.append(float(value))
        return normalized

    @staticmethod
    def _normalize_document_filter(document_ids: Sequence[int] | None) -> list[int] | None:
        if document_ids is None:
            return None
        normalized = list(document_ids)
        if not normalized or any(
            isinstance(document_id, bool) or not isinstance(document_id, int) or document_id < 1
            for document_id in normalized
        ) or len(set(normalized)) != len(normalized):
            raise ValueError("Qdrant document filters must contain unique positive integers")
        return normalized

    @staticmethod
    def _normalize_content_type_filter(content_types: Sequence[str] | None) -> list[str] | None:
        if content_types is None:
            return None
        normalized = list(content_types)
        if not normalized or any(
            not isinstance(content_type, str) or content_type not in SUPPORTED_RETRIEVAL_CONTENT_TYPES
            for content_type in normalized
        ) or len(set(normalized)) != len(normalized):
            raise ValueError("Qdrant content-type filters contain an unsupported or duplicate value")
        return normalized

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
