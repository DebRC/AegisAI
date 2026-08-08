# Retrieval and metadata filtering design

## Purpose

Phase 10 turns Phase 9's derived vectors into grounded semantic-search
results. Qdrant finds candidate vector IDs and similarity scores; PostgreSQL
will remain authoritative for document state, chunk text, extraction identity,
and vector validity. Phase 10 does not generate an LLM answer or provide chat.

## 10.1 Retrieval contract and search policy

The future read-only search endpoint is `POST /retrieval/search`. Its route is
deliberately deferred to checkpoint 10.7, when a real retrieval service can
enforce the contract below. Registering an endpoint that cannot retrieve would
mislead clients and create an unsupported public API.

`RetrievalSearchRequest` accepts only:

| Field | Rule |
| --- | --- |
| `query` | Required, whitespace-normalized text of at most 10,000 characters. |
| `limit` | Optional, defaults to 10, and is bounded from 1 through 20. |
| `document_ids` | Optional allow-list of at most 100 unique positive document IDs. |
| `content_types` | Optional allow-list from the four supported ingestion MIME types; duplicates are rejected. |

Clients cannot send a Qdrant collection name, point ID, score threshold,
provider/model override, arbitrary Qdrant filter expression, or any other
vendor-specific control. The active configured embedding identity is the only
one used for search.

Each future `RetrievalSearchResult` contains only the current document/chunk
identity, document title and content type, chunk text and source locations, and
a finite similarity score. A score is a ranking value, not a confidence claim.
Results are ordered highest score first and use deterministic tie-breaking in
the retrieval service. Empty matches return an empty `items` list, while invalid
input is rejected by request validation.

The eventual endpoint requires the existing global `documents:read` permission.
That is not document-level authorization: Phase 12 will add permission-aware
and tenant-aware retrieval before semantic results can be exposed under a
resource-specific policy.

## 10.2 Query-embedding boundary

`QueryEmbeddingService` adapts one validated `RetrievalSearchRequest` to the
existing `EmbeddingProvider` protocol. It calls `embed` with exactly one
normalized query string, verifies that exactly one vector was returned, and
requires the provider, model, and vector dimension to match the active settings.
The returned `QueryEmbedding` carries only the finite vector and that validated
identity; query vectors are not persisted.

Provider configuration, transport, response, and validation failures become a
single safe `QueryEmbeddingError` boundary. Provider details and credentials do
not cross into an API response, and the provider client is closed after every
attempt, including failures. The service is injected with a provider factory so
unit tests and future provider implementations do not require a network call.

## Delivery checkpoints

- [x] 10.1 Retrieval contract and search policy
- [x] 10.2 Query-embedding boundary
- [ ] 10.3 Qdrant similarity-search boundary
- [ ] 10.4 Metadata filters
- [ ] 10.5 PostgreSQL authority checks
- [ ] 10.6 Retrieval service and ranking
- [ ] 10.7 Retrieval API and current RBAC
- [ ] 10.8 Tests, Docker verification, and documentation
