"""Construct the Qdrant client without leaking settings into services."""

from qdrant_client import QdrantClient

from app.core.config import Settings


def create_qdrant_client(configuration: Settings) -> QdrantClient:
    """Create one synchronous Qdrant client for a worker-scoped operation.

    The caller owns the returned client's lifecycle and must close it when the
    operation finishes. This function performs no network request: collection
    validation and vector operations belong to later Phase 9 checkpoints.
    """
    api_key = configuration.QDRANT_API_KEY
    return QdrantClient(
        url=configuration.QDRANT_URL,
        api_key=api_key.get_secret_value() if api_key is not None else None,
        timeout=configuration.QDRANT_TIMEOUT_SECONDS,
    )
