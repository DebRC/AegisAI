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
    # Docker Compose exposes an empty ``QDRANT_API_KEY=`` as a real empty
    # string. Qdrant's local unauthenticated service expects no key at all.
    secret = api_key.get_secret_value().strip() if api_key is not None else ""
    return QdrantClient(
        url=configuration.QDRANT_URL,
        api_key=secret or None,
        timeout=configuration.QDRANT_TIMEOUT_SECONDS,
    )
