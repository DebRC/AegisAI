"""OpenAI implementation of the provider-neutral embedding contract."""

from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import Settings
from app.embeddings.base import EmbeddingBatch
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.embeddings.exceptions import EmbeddingProviderError
from app.embeddings.exceptions import EmbeddingProviderResponseError


class OpenAIEmbeddingProvider:
    """Generate ordered float embeddings through OpenAI's Embeddings API."""

    provider_name = "openai"

    def __init__(self, configuration: Settings, http_client: httpx.Client | None = None):
        api_key = configuration.OPENAI_API_KEY
        secret = api_key.get_secret_value().strip() if api_key is not None else ""
        if not secret:
            raise EmbeddingProviderConfigurationError(
                "OPENAI_API_KEY must be configured before embeddings can be generated"
            )
        self.model = configuration.EMBEDDING_MODEL
        self.vector_dimension = configuration.EMBEDDING_VECTOR_DIMENSION
        self.batch_size = configuration.EMBEDDING_BATCH_SIZE
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=f"{configuration.OPENAI_BASE_URL}/",
            timeout=configuration.EMBEDDING_REQUEST_TIMEOUT_SECONDS,
        )
        self._headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        }

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Request and validate one vector per text without exposing provider details."""
        inputs = self._validated_inputs(texts)
        try:
            response = self._client.post(
                "embeddings",
                headers=self._headers,
                json={
                    "input": inputs,
                    "model": self.model,
                    "dimensions": self.vector_dimension,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EmbeddingProviderError("OpenAI embeddings request failed") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise EmbeddingProviderResponseError("OpenAI embeddings response was invalid") from error
        batch = self._parse_response(payload, input_count=len(inputs))
        if batch.vector_dimension != self.vector_dimension:
            raise EmbeddingProviderResponseError("OpenAI embeddings response had an unexpected dimension")
        return batch

    def close(self) -> None:
        """Close only the client that this provider constructed itself."""
        if self._owns_client:
            self._client.close()

    def _validated_inputs(self, texts: Sequence[str]) -> list[str]:
        if isinstance(texts, (str, bytes)) or not texts or len(texts) > self.batch_size:
            raise EmbeddingProviderError("Embedding input batch is invalid")
        inputs = list(texts)
        if any(not isinstance(text, str) or not text.strip() for text in inputs):
            raise EmbeddingProviderError("Embedding input batch is invalid")
        return inputs

    def _parse_response(self, payload: Any, *, input_count: int) -> EmbeddingBatch:
        if not isinstance(payload, dict) or payload.get("model") != self.model:
            raise EmbeddingProviderResponseError("OpenAI embeddings response did not match the configured model")
        entries = payload.get("data")
        if not isinstance(entries, list) or len(entries) != input_count:
            raise EmbeddingProviderResponseError("OpenAI embeddings response did not match the input batch")

        vectors: list[tuple[float, ...] | None] = [None] * input_count
        for entry in entries:
            if not isinstance(entry, dict):
                raise EmbeddingProviderResponseError("OpenAI embeddings response was invalid")
            index = entry.get("index")
            vector = entry.get("embedding")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < input_count:
                raise EmbeddingProviderResponseError("OpenAI embeddings response contained an invalid index")
            if vectors[index] is not None or not isinstance(vector, list):
                raise EmbeddingProviderResponseError("OpenAI embeddings response was invalid")
            vectors[index] = tuple(vector)
        if any(vector is None for vector in vectors):
            raise EmbeddingProviderResponseError("OpenAI embeddings response did not include every input")
        try:
            return EmbeddingBatch(
                provider=self.provider_name,
                model=self.model,
                vectors=tuple(vector for vector in vectors if vector is not None),
            )
        except ValueError as error:
            raise EmbeddingProviderResponseError("OpenAI embeddings response contained an invalid vector") from error
