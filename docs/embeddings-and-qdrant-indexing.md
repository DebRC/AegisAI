# Embeddings and Qdrant indexing design

## Purpose

Phase 9 makes the deterministic chunks produced by Phase 8 semantically
searchable. A background worker will turn each current chunk into an embedding
vector and index that vector in Qdrant. Phase 10 will use those vectors for
retrieval; Phase 9 does not expose a search API or generate LLM answers.

PostgreSQL remains AegisAI's system of record. Qdrant is a derived search
index: it may be recreated from the database and must never be the only copy of
document text, ownership, or processing state.

## Completion criteria

Phase 9 is complete when all of the following are true:

- Every current extracted chunk can have one traceable embedding for the active
  provider and model.
- A successful text-extraction job atomically queues a durable
  `embedding_indexing` job through the existing outbox.
- Workers batch embedding requests, validate returned vector dimensions, and
  upsert deterministic Qdrant points safely.
- PostgreSQL records the provider, model, collection, point identifier,
  chunk-content checksum, and successful indexing time for every current
  vector.
- A duplicate delivery or retry cannot create duplicate logical vectors.
- Reprocessing and document deletion remove superseded vectors without
  exposing broker, provider, or storage details through the API.
- Unit tests, Docker verification, and focused operating documentation cover
  the failure and recovery paths.

## Scope and boundaries

| Included in Phase 9 | Deliberately deferred |
| --- | --- |
| Provider abstraction, one configured embedding provider, batch generation, Qdrant collection management, vector persistence, lifecycle jobs, cleanup, and indexing status | Similarity-search endpoints, ranking, metadata-filter query language, LLM prompts, chat streaming, citations, tenant filtering, and permission-aware search results |

Phase 9 is not allowed to change the Phase 8 extraction/chunking algorithm
silently. Chunks remain deterministic, ordered, and traceable by their existing
database IDs, checksums, and normalized-text offsets.

## Data ownership and index shape

One `DocumentChunkEmbedding` record will represent one current embedding of one
chunk for one configured provider/model/collection combination. It will record:

| Field | Reason |
| --- | --- |
| Chunk ID and document-extraction ID | Connect the vector to its authoritative text and extraction version. |
| Provider identifier and model identifier | Identify exactly how the vector was created. |
| Collection name and deterministic Qdrant point ID | Allow repair, deletion, and migration without searching by free-form text. |
| Vector dimension | Detect a provider or collection configuration mismatch safely. |
| Chunk content checksum | Detect stale vectors after a chunk changes. |
| Indexed timestamp and lifecycle timestamps | Make operational status and recovery auditable. |

The Qdrant point payload contains only identifiers and safe filter fields needed
by a later retrieval stage: `document_id`, `chunk_id`, `document_extraction_id`,
`uploader_user_id`, `content_type`, and the embedding provider/model identity.
Chunk text, original filenames, storage keys, JWTs, provider credentials, and
raw error details are not copied into Qdrant payloads. Phase 10 will retrieve
matching point IDs and load authoritative text and current-document state from
PostgreSQL.

## Provider and collection contract

The application depends on an `EmbeddingProvider` interface rather than a
vendor SDK in worker or service code. Its contract is:

```text
embed(texts) -> ordered vectors + provider identifier + model identifier
```

The provider returns exactly one finite, numeric vector per input text and
preserves input order. The OpenAI adapter sends the configured model, requested
dimension, and float encoding to the Embeddings API; it then reorders results by
the provider's returned input index. It rejects empty responses, non-finite
values, count mismatches, model mismatches, and dimension mismatches before an
embedding record can be written or a job marked successful.

The first implementation uses OpenAI `text-embedding-3-small` at its documented
default of 1,536 dimensions. Its API key stays in environment configuration and
is never stored in PostgreSQL or sent to the browser. Test doubles will
implement the same interface, so tests do not require a network call or paid
credentials. The provider boundary remains replaceable for a later deployment
choice.

Qdrant collections have an immutable vector dimension and distance metric. The
active collection therefore has these rules:

- it uses cosine distance for semantic similarity;
- its configured dimension must exactly equal every vector returned by the
  configured provider;
- an existing collection with incompatible distance, dimension, or vector
  schema causes a safe indexing failure rather than mutation; and
- changing provider/model/dimension requires a new collection and a deliberate
  reindex, not an in-place rewrite of existing points.

The vector-store boundary creates the collection only when it is absent, with
the configured dimension and cosine distance. It then reads its configuration
back before any point write. A pre-existing collection with named vectors, a
different dimension, or a different distance metric is rejected; AegisAI never
deletes or recreates it automatically. The boundary also creates Qdrant payload
indexes for the allow-listed filter fields before ingesting points.

Its typed point input makes the payload contract explicit. Every point contains
only the seven fields below, and no caller can attach arbitrary payload data:

```text
document_id, chunk_id, document_extraction_id, uploader_user_id,
content_type, embedding_provider, embedding_model
```

The boundary accepts caller-supplied UUID point IDs, validates finite vectors
against the configured dimension, waits for Qdrant upsert/delete completion,
and exposes only safe operation errors. The Phase 9.6 worker supplies the
deterministic IDs and invokes these operations.

The provider name, model, collection name, dimension, request timeout, and
batch limits are validated environment settings. `QDRANT_API_KEY` remains empty
for the local Docker Qdrant service. `OPENAI_API_KEY` must be set in the local
uncommitted `backend/.env` before an indexing worker can generate real vectors;
without it, the durable job fails safely and remains retryable. No secret is
introduced by version control.

## Identity and idempotency

The service derives a stable Qdrant point UUID from the embedding identity
(chunk ID, provider, model, and collection) and uses Qdrant upsert semantics.
Repeating the same job therefore writes the same logical point rather than
accumulating another one.

The content checksum is part of the validity check, not the point identity. If
reprocessing replaces an extraction or a document is deleted, the pipeline
captures old point IDs in durable collection-scoped cleanup requests before
chunk rows cascade-delete. A cleanup worker deletes those IDs using their
original collection name and records a retryable job result. Reprocessing is
blocked while indexing or cleanup is non-terminal, avoiding replacement races.
New chunks receive new point IDs; a vector is usable only when its document,
extraction/chunk, embedding record, and checksum all remain current.

## Processing lifecycle

`Document.status` continues to mean that source text and chunks are available.
It does not become an overloaded vector-index health flag. The new job type
tracks indexing separately:

```text
text_extraction succeeds
  │
  ├── persist extraction and chunks
  ├── mark document READY
  └── create embedding_indexing job + outbox event in the same transaction
          │
          ├── queued / running: document remains READY; vectors may be incomplete
          ├── succeeded: all current chunks have valid Qdrant points
          ├── failed: document remains READY; safe job error is visible and retryable
          └── cancelled: document was deleted or its work became superseded

replacement or deletion
  └── create vector_cleanup job(s) + point-ID request(s) in the same transaction
          ├── succeeded: obsolete points are removed
          └── failed: safe error is retryable; no document status is changed
```

This separation means a document is never reported as text-extraction failed
merely because an external embedding provider is temporarily unavailable. The
existing processing-job API will expose the safe job state; Phase 9 does not add
a vector-search endpoint.

## Failure, retry, and cleanup policy

Embedding providers and Qdrant are external systems, so a PostgreSQL commit and
a vector upsert cannot form one shared database transaction. The implementation
uses this recovery sequence:

1. Claim one durable indexing job through the existing PostgreSQL job rules.
2. Read only the current extraction and chunks; cancel if the document was
   deleted or superseded.
3. Generate and validate batches of vectors.
4. Upsert deterministic points to Qdrant.
5. Persist matching embedding records and complete the job only after every
   current chunk is represented.

If a call fails before completion, the job records a bounded, user-safe error
and can be retried. A retry repeats deterministic upserts and converges on the
same points. If Qdrant succeeds but the following PostgreSQL commit fails, the
next retry upserts the same points and repairs the database record. Superseded
and deleted document vectors are removed through durable, retryable cleanup
work; API deletion never relies solely on a best-effort network call.

Safe stored/API errors use messages such as `Embeddings could not be generated
for this document.` or `Document vectors could not be indexed.` Provider HTTP
bodies, credentials, stack traces, and Qdrant internals remain in worker logs.

## Authorization and future retrieval

Phase 9 retains the established global `documents:read` and `documents:write`
policies for safe document and job-status APIs. The index payload carries
provenance fields needed for later filtering, but payload fields are not an
authorization boundary. Phase 12 will enforce permission-aware retrieval before
any user can receive semantic search results or citations.

## Delivery checkpoints

- [x] 9.1 Embedding and indexing contract
- [x] 9.2 Qdrant configuration and runtime client
- [x] 9.3 Embedding persistence and migration
- [x] 9.4 Embedding-provider abstraction
- [x] 9.5 Qdrant collection and vector operations
- [x] 9.6 Background indexing pipeline
- [x] 9.7 Reprocessing, idempotency, and cleanup
- [ ] 9.8 Status visibility and authorization
- [ ] 9.9 Tests, Docker verification, and documentation
