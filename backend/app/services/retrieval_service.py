"""Orchestrate query embedding, vector candidates, authority checks, and ranking."""

from collections.abc import Callable

from app.integrations.vector_store.qdrant_store import QdrantSearchCandidate
from app.integrations.vector_store.qdrant_store import QdrantVectorStore
from app.schemas.retrieval import RetrievalSearchRequest
from app.schemas.retrieval import RetrievalSearchResponse
from app.schemas.retrieval import RetrievalSearchResult
from app.services.query_embedding_service import QueryEmbeddingService
from app.services.retrieval_authority_service import AuthoritativeRetrievalCandidate
from app.services.retrieval_authority_service import RetrievalAuthorityService
from app.services.audit_event_service import AuditEventService
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType


_MAX_CANDIDATE_LIMIT = 100
VectorStoreFactory = Callable[[], QdrantVectorStore]


class RetrievalService:
    """Build bounded retrieval results from verified current source records."""

    def __init__(
        self,
        query_embeddings: QueryEmbeddingService,
        authority: RetrievalAuthorityService,
        create_vector_store: VectorStoreFactory,
        audit_events: AuditEventService | None = None,
    ) -> None:
        self.query_embeddings = query_embeddings
        self.authority = authority
        self.create_vector_store = create_vector_store
        self.audit_events = audit_events

    def search(
        self,
        request: RetrievalSearchRequest,
        *,
        user_id: int,
    ) -> RetrievalSearchResponse:
        """Search with bounded over-fetching, authority validation, and stable ranking."""
        try:
            query_embedding = self.query_embeddings.embed_query(request)
            vector_store = self.create_vector_store()
            try:
                candidates = vector_store.search(
                    vector=query_embedding.vector,
                    provider=query_embedding.provider,
                    model=query_embedding.model,
                    limit=min(_MAX_CANDIDATE_LIMIT, max(request.limit * 3, request.limit)),
                    document_ids=request.document_ids,
                    content_types=request.content_types,
                )
            finally:
                try:
                    vector_store.close()
                except Exception:
                    # Client cleanup must not replace a successful or safe search
                    # result with an infrastructure-specific exception.
                    pass

            authoritative = self.authority.resolve(
                candidates=candidates,
                user_id=user_id,
                document_ids=request.document_ids,
                content_types=request.content_types,
            )
            ranked = sorted(authoritative, key=self._ranking_key)
            response = RetrievalSearchResponse(
                items=[self._to_result(item) for item in ranked[: request.limit]],
                limit=request.limit,
            )
        except Exception:
            self._record_search(user_id=user_id, outcome=AuditEventOutcome.FAILED)
            raise
        self._record_search(
            user_id=user_id,
            outcome=AuditEventOutcome.SUCCEEDED,
            result_count=len(response.items),
        )
        return response

    def _record_search(
        self,
        *,
        user_id: int,
        outcome: AuditEventOutcome,
        result_count: int | None = None,
    ) -> None:
        if self.audit_events is None:
            return
        metadata = {"result_count": result_count} if result_count is not None else None
        self.audit_events.record_best_effort(
            event_type=AuditEventType.RETRIEVAL_SEARCH,
            outcome=outcome,
            actor_user_id=user_id,
            metadata=metadata,
        )

    @staticmethod
    def _ranking_key(item: AuthoritativeRetrievalCandidate) -> tuple[float, int, int, int, str]:
        """Rank by score, then stable relational identity and point UUID."""
        return (
            -item.candidate.score,
            item.document.id,
            item.chunk.ordinal,
            item.chunk.id,
            item.candidate.point_id,
        )

    @staticmethod
    def _to_result(item: AuthoritativeRetrievalCandidate) -> RetrievalSearchResult:
        return RetrievalSearchResult(
            document_id=item.document.id,
            document_title=item.document.title,
            content_type=item.document.content_type,
            chunk_id=item.chunk.id,
            chunk_ordinal=item.chunk.ordinal,
            content=item.chunk.content,
            source_locations=item.chunk.source_locations,
            score=item.candidate.score,
        )
