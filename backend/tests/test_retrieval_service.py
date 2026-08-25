from types import SimpleNamespace
import unittest

from app.integrations.vector_store.qdrant_store import QdrantSearchCandidate
from app.schemas.retrieval import RetrievalSearchRequest
from app.services.query_embedding_service import QueryEmbedding
from app.services.retrieval_authority_service import AuthoritativeRetrievalCandidate
from app.services.retrieval_service import RetrievalService


class FakeQueryEmbeddingService:
    def __init__(self) -> None:
        self.requests: list[RetrievalSearchRequest] = []

    def embed_query(self, request: RetrievalSearchRequest) -> QueryEmbedding:
        self.requests.append(request)
        return QueryEmbedding(
            vector=(0.1, 0.2, 0.3),
            provider="openai",
            model="text-embedding-3-small",
            vector_dimension=3,
        )


class FakeVectorStore:
    def __init__(self, candidates: list[QdrantSearchCandidate]) -> None:
        self.candidates = candidates
        self.search_calls: list[dict[str, object]] = []
        self.closed = False

    def search(self, **kwargs: object) -> list[QdrantSearchCandidate]:
        self.search_calls.append(kwargs)
        return self.candidates

    def close(self) -> None:
        self.closed = True


class FakeAuthorityService:
    def __init__(self, resolved: list[AuthoritativeRetrievalCandidate]) -> None:
        self.resolved = resolved
        self.calls: list[dict[str, object]] = []

    def resolve(self, **kwargs: object) -> list[AuthoritativeRetrievalCandidate]:
        self.calls.append(kwargs)
        return self.resolved


class FakeAuditEvents:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_best_effort(self, **kwargs: object) -> None:
        self.events.append(kwargs)


class RetrievalServiceTests(unittest.TestCase):
    def test_search_overfetches_verifies_ranks_and_bounds_results(self) -> None:
        request = RetrievalSearchRequest(
            query="refresh tokens",
            limit=2,
            document_ids=[12, 18],
            content_types=["text/markdown"],
        )
        candidates = [self._candidate("a", 0.7), self._candidate("b", 0.9), self._candidate("c", 0.9)]
        store = FakeVectorStore(candidates)
        authority = FakeAuthorityService(
            [
                self._authoritative(candidates[0], document_id=18, chunk_id=3, ordinal=0),
                self._authoritative(candidates[1], document_id=12, chunk_id=2, ordinal=1),
                self._authoritative(candidates[2], document_id=12, chunk_id=1, ordinal=0),
            ]
        )
        embeddings = FakeQueryEmbeddingService()
        service = RetrievalService(embeddings, authority, lambda: store)

        response = service.search(request, user_id=7)

        self.assertEqual([item.chunk_id for item in response.items], [1, 2])
        self.assertEqual([item.score for item in response.items], [0.9, 0.9])
        self.assertEqual(response.limit, 2)
        self.assertEqual(embeddings.requests, [request])
        self.assertTrue(store.closed)
        self.assertEqual(store.search_calls[0]["limit"], 6)
        self.assertEqual(store.search_calls[0]["document_ids"], [12, 18])
        self.assertEqual(authority.calls[0]["user_id"], 7)
        self.assertEqual(authority.calls[0]["content_types"], ["text/markdown"])

    def test_search_maps_verified_source_fields_and_does_not_expose_embedding_data(self) -> None:
        candidate = self._candidate("a", 0.8)
        store = FakeVectorStore([candidate])
        authority = FakeAuthorityService([self._authoritative(candidate, document_id=12, chunk_id=4, ordinal=2)])
        service = RetrievalService(FakeQueryEmbeddingService(), authority, lambda: store)

        result = service.search(
            RetrievalSearchRequest(query="policy"),
            user_id=7,
        ).items[0]

        self.assertEqual(result.document_id, 12)
        self.assertEqual(result.document_title, "Policy")
        self.assertEqual(result.chunk_id, 4)
        self.assertEqual(result.content, "Current policy text")
        self.assertEqual(result.source_locations, [{"kind": "line", "start": 1, "end": 3}])
        self.assertFalse(hasattr(result, "point_id"))
        self.assertFalse(hasattr(result, "vector"))

    def test_vector_store_is_closed_when_search_fails(self) -> None:
        class FailingStore(FakeVectorStore):
            def search(self, **kwargs: object) -> list[QdrantSearchCandidate]:
                raise RuntimeError("provider internals")

        store = FailingStore([])
        service = RetrievalService(FakeQueryEmbeddingService(), FakeAuthorityService([]), lambda: store)

        with self.assertRaisesRegex(RuntimeError, "provider internals"):
            service.search(RetrievalSearchRequest(query="policy"), user_id=7)
        self.assertTrue(store.closed)

    def test_records_only_safe_search_telemetry(self) -> None:
        candidate = self._candidate("a", 0.8)
        audit_events = FakeAuditEvents()
        service = RetrievalService(
            FakeQueryEmbeddingService(),
            FakeAuthorityService([self._authoritative(candidate, document_id=12, chunk_id=4, ordinal=2)]),
            lambda: FakeVectorStore([candidate]),
            audit_events,
        )

        service.search(RetrievalSearchRequest(query="confidential query"), user_id=7)

        self.assertEqual(len(audit_events.events), 1)
        event = audit_events.events[0]
        self.assertEqual(event["actor_user_id"], 7)
        self.assertEqual(event["metadata"], {"result_count": 1})
        self.assertNotIn("query", event)

    @staticmethod
    def _candidate(suffix: str, score: float) -> QdrantSearchCandidate:
        return QdrantSearchCandidate(
            point_id=f"{suffix}911e79c-97e2-4b68-8974-803034fc62ca",
            score=score,
            payload={},
        )

    @staticmethod
    def _authoritative(
        candidate: QdrantSearchCandidate,
        *,
        document_id: int,
        chunk_id: int,
        ordinal: int,
    ) -> AuthoritativeRetrievalCandidate:
        document = SimpleNamespace(
            id=document_id,
            title="Policy",
            content_type="text/markdown",
        )
        extraction = SimpleNamespace(id=22)
        chunk = SimpleNamespace(
            id=chunk_id,
            ordinal=ordinal,
            content="Current policy text",
            source_locations=[{"kind": "line", "start": 1, "end": 3}],
        )
        embedding = SimpleNamespace(
            provider="openai",
            model="text-embedding-3-small",
        )
        return AuthoritativeRetrievalCandidate(
            candidate=candidate,
            document=document,
            extraction=extraction,
            chunk=chunk,
            embedding=embedding,
        )
