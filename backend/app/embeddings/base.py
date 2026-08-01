"""Provider-neutral embedding values and protocol."""

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


@dataclass(frozen=True)
class EmbeddingBatch:
    """Ordered, validated vectors returned for one ordered text request."""

    provider: str
    model: str
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("Embedding provider must be a non-empty string")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Embedding model must be a non-empty string")
        if not self.vectors:
            raise ValueError("Embedding batches must contain at least one vector")

        dimension: int | None = None
        normalized_vectors: list[tuple[float, ...]] = []
        for vector in self.vectors:
            if not vector:
                raise ValueError("Embedding vectors must not be empty")
            normalized: list[float] = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Embedding vector values must be finite numbers")
                normalized.append(float(value))
            if dimension is None:
                dimension = len(normalized)
            elif len(normalized) != dimension:
                raise ValueError("Embedding vectors in one batch must share a dimension")
            normalized_vectors.append(tuple(normalized))
        object.__setattr__(self, "vectors", tuple(normalized_vectors))

    @property
    def vector_dimension(self) -> int:
        """Return the common dimension after construction-time validation."""
        return len(self.vectors[0])


class EmbeddingProvider(Protocol):
    """Generate one ordered vector for each supplied non-empty text value."""

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Return vectors in the exact order of ``texts``."""

    def close(self) -> None:
        """Release provider-owned resources when a worker operation ends."""
