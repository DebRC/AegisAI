from types import SimpleNamespace
import unittest

from app.embeddings.base import EmbeddingBatch
from app.embeddings.exceptions import EmbeddingProviderConfigurationError
from app.embeddings.exceptions import EmbeddingProviderError
from app.schemas.retrieval import RetrievalSearchRequest
from app.services.query_embedding_service import QueryEmbeddingError
from app.services.query_embedding_service import QueryEmbeddingService


class FakeProvider:
    def __init__(self, batch: EmbeddingBatch | Exception):
        self.batch = batch
        self.inputs: list[list[str]] = []
        self.closed = False

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        self.inputs.append(texts)
        if isinstance(self.batch, Exception):
            raise self.batch
        return self.batch

    def close(self) -> None:
        self.closed = True


class QueryEmbeddingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configuration = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_VECTOR_DIMENSION=3,
        )
        self.request = RetrievalSearchRequest(query="  refresh tokens  ")

    def test_embeds_one_normalized_query_and_returns_active_identity(self) -> None:
        provider = FakeProvider(
            EmbeddingBatch(
                provider="openai",
                model="text-embedding-3-small",
                vectors=((0.1, 0.2, 0.3),),
            )
        )
        service = QueryEmbeddingService(self.configuration, lambda: provider)

        result = service.embed_query(self.request)

        self.assertEqual(provider.inputs, [["refresh tokens"]])
        self.assertEqual(result.vector, (0.1, 0.2, 0.3))
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "text-embedding-3-small")
        self.assertEqual(result.vector_dimension, 3)
        self.assertTrue(provider.closed)

    def test_rejects_provider_model_dimension_and_count_mismatches(self) -> None:
        batches = (
            EmbeddingBatch(provider="other", model="text-embedding-3-small", vectors=((1, 2, 3),)),
            EmbeddingBatch(provider="openai", model="other-model", vectors=((1, 2, 3),)),
            EmbeddingBatch(provider="openai", model="text-embedding-3-small", vectors=((1, 2),)),
            EmbeddingBatch(
                provider="openai",
                model="text-embedding-3-small",
                vectors=((1, 2, 3), (4, 5, 6)),
            ),
        )

        for batch in batches:
            provider = FakeProvider(batch)
            service = QueryEmbeddingService(self.configuration, lambda provider=provider: provider)
            with self.subTest(batch=batch), self.assertRaises(QueryEmbeddingError):
                service.embed_query(self.request)
            self.assertTrue(provider.closed)

    def test_translates_provider_failures_to_safe_errors_and_closes_client(self) -> None:
        failures = (
            EmbeddingProviderConfigurationError("secret details"),
            EmbeddingProviderError("provider response details"),
        )

        for failure in failures:
            provider = FakeProvider(failure)
            service = QueryEmbeddingService(self.configuration, lambda provider=provider: provider)
            with self.subTest(failure=type(failure)), self.assertRaises(QueryEmbeddingError) as context:
                service.embed_query(self.request)
            self.assertNotIn("details", str(context.exception))
            self.assertTrue(provider.closed)
