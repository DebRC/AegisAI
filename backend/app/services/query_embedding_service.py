"""Create one safe query vector for the Phase 10 retrieval pipeline."""

from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.embeddings.exceptions import EmbeddingProviderError
from app.schemas.retrieval import RetrievalSearchRequest


class QueryEmbeddingError(RuntimeError):
    """Safe, provider-neutral failure while embedding a search query."""


@dataclass(frozen=True)
class QueryEmbedding:
    """One validated vector plus the identity needed by the vector-store query."""

    vector: tuple[float, ...]
    provider: str
    model: str
    vector_dimension: int


EmbeddingProviderFactory = Callable[[], EmbeddingProvider]


class QueryEmbeddingService:
    """Adapt one validated retrieval request to the configured embedding provider."""

    def __init__(
        self,
        configuration: Settings,
        create_provider: EmbeddingProviderFactory,
    ) -> None:
        self.configuration = configuration
        self.create_provider = create_provider

    def embed_query(self, request: RetrievalSearchRequest) -> QueryEmbedding:
        """Embed exactly one query and verify the active embedding identity."""
        provider: EmbeddingProvider | None = None
        try:
            provider = self.create_provider()
            batch = provider.embed([request.query])
            if len(batch.vectors) != 1:
                raise QueryEmbeddingError("The query embedding provider returned an invalid result.")
            if (
                batch.provider != self.configuration.EMBEDDING_PROVIDER
                or batch.model != self.configuration.EMBEDDING_MODEL
            ):
                raise QueryEmbeddingError("The query embedding provider does not match the active configuration.")
            if batch.vector_dimension != self.configuration.EMBEDDING_VECTOR_DIMENSION:
                raise QueryEmbeddingError("The query embedding dimension does not match the active configuration.")
            return QueryEmbedding(
                vector=batch.vectors[0],
                provider=batch.provider,
                model=batch.model,
                vector_dimension=batch.vector_dimension,
            )
        except QueryEmbeddingError:
            raise
        except EmbeddingProviderConfigurationError as error:
            raise QueryEmbeddingError("Search embedding configuration is unavailable.") from error
        except (EmbeddingProviderError, ValueError) as error:
            raise QueryEmbeddingError("The search query could not be embedded.") from error
        finally:
            if provider is not None:
                try:
                    provider.close()
                except Exception:
                    # A client cleanup error must not replace the operation's
                    # safe result or expose provider internals to callers.
                    pass
