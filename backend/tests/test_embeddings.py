import json
import unittest

import httpx

from app.core.config import Settings
from app.embeddings.base import EmbeddingBatch
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.embeddings.exceptions import EmbeddingProviderError
from app.embeddings.exceptions import EmbeddingProviderResponseError
from app.embeddings.factory import create_embedding_provider
from app.embeddings.openai import OpenAIEmbeddingProvider


class EmbeddingBatchTests(unittest.TestCase):
    def test_normalizes_finite_vectors_and_exposes_the_common_dimension(self) -> None:
        batch = EmbeddingBatch(
            provider="test",
            model="test-v1",
            vectors=((1, 2.5), (3.0, 4)),
        )

        self.assertEqual(batch.vectors, ((1.0, 2.5), (3.0, 4.0)))
        self.assertEqual(batch.vector_dimension, 2)

    def test_rejects_empty_inconsistent_or_non_finite_values(self) -> None:
        invalid_values = (
            {"provider": "", "model": "test", "vectors": ((1.0,),)},
            {"provider": "test", "model": "", "vectors": ((1.0,),)},
            {"provider": "test", "model": "test", "vectors": ()},
            {"provider": "test", "model": "test", "vectors": ((1.0,), (2.0, 3.0))},
            {"provider": "test", "model": "test", "vectors": ((float("nan"),),)},
            {"provider": "test", "model": "test", "vectors": ((True,),)},
        )

        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    EmbeddingBatch(**values)


class OpenAIEmbeddingProviderTests(unittest.TestCase):
    _REQUIRED_SETTINGS = {
        "APP_NAME": "AegisAI",
        "APP_VERSION": "test",
        "APP_ENV": "test",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "QDRANT_URL": "http://qdrant:6333",
        "JWT_SECRET_KEY": "test-secret",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
    }

    def test_sends_a_bounded_ordered_float_request_and_reorders_indexed_response(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["url"] = str(request.url)
            observed["authorization"] = request.headers["Authorization"]
            observed["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-small",
                    "data": [
                        {"index": 1, "embedding": [3.0, 4.0]},
                        {"index": 0, "embedding": [1.0, 2.0]},
                    ],
                },
            )

        provider = OpenAIEmbeddingProvider(
            self._configuration(EMBEDDING_VECTOR_DIMENSION=2, EMBEDDING_BATCH_SIZE=2),
            httpx.Client(base_url="https://api.openai.com/v1/", transport=httpx.MockTransport(handler)),
        )

        result = provider.embed(["first", "second"])

        self.assertEqual(observed["url"], "https://api.openai.com/v1/embeddings")
        self.assertEqual(observed["authorization"], "Bearer test-openai-key")
        self.assertEqual(
            observed["payload"],
            {
                "input": ["first", "second"],
                "model": "text-embedding-3-small",
                "dimensions": 2,
                "encoding_format": "float",
            },
        )
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.vectors, ((1.0, 2.0), (3.0, 4.0)))

    def test_rejects_missing_key_invalid_input_provider_errors_and_invalid_responses(self) -> None:
        with self.assertRaises(EmbeddingProviderConfigurationError):
            OpenAIEmbeddingProvider(self._configuration(OPENAI_API_KEY=""))

        provider = self._provider_with_response(
            200,
            {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [1.0, 2.0]}]},
        )
        for invalid_input in ([], [""], ["one", "two", "three"]):
            with self.subTest(invalid_input=invalid_input):
                with self.assertRaises(EmbeddingProviderError):
                    provider.embed(invalid_input)

        with self.assertRaises(EmbeddingProviderError):
            self._provider_with_response(429, {"error": {"message": "ignored"}}).embed(["text"])

        invalid_responses = (
            {"model": "other", "data": [{"index": 0, "embedding": [1.0, 2.0]}]},
            {"model": "text-embedding-3-small", "data": [{"index": 1, "embedding": [1.0, 2.0]}]},
            {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [1.0]}]},
            {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [True, 2.0]}]},
        )
        for payload in invalid_responses:
            with self.subTest(payload=payload):
                with self.assertRaises(EmbeddingProviderResponseError):
                    self._provider_with_response(200, payload).embed(["text"])

    def test_factory_returns_the_configured_provider(self) -> None:
        provider = create_embedding_provider(
            self._configuration(),
            http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
        )

        self.assertIsInstance(provider, OpenAIEmbeddingProvider)

    def _configuration(self, **overrides: object) -> Settings:
        return Settings(
            **(
                self._REQUIRED_SETTINGS
                | {
                    "OPENAI_API_KEY": "test-openai-key",
                    **overrides,
                }
            )
        )

    def _provider_with_response(self, status_code: int, payload: dict[str, object]) -> OpenAIEmbeddingProvider:
        return OpenAIEmbeddingProvider(
            self._configuration(EMBEDDING_VECTOR_DIMENSION=2, EMBEDDING_BATCH_SIZE=2),
            httpx.Client(
                base_url="https://api.openai.com/v1/",
                transport=httpx.MockTransport(lambda _: httpx.Response(status_code, json=payload)),
            ),
        )
