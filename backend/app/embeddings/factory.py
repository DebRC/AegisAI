"""Create configured embedding providers without leaking provider choice to workers."""

import httpx

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.openai import OpenAIEmbeddingProvider


def create_embedding_provider(
    configuration: Settings,
    http_client: httpx.Client | None = None,
) -> EmbeddingProvider:
    """Create the selected provider; later implementations extend this boundary."""
    if configuration.EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbeddingProvider(configuration, http_client=http_client)
    raise ValueError("Unsupported embedding provider")
