"""Replaceable clients for derived vector-search infrastructure."""

from app.integrations.vector_store.qdrant_client import create_qdrant_client

__all__ = ["create_qdrant_client"]
