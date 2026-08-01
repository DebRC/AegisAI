# Text extraction and chunking design

## Purpose

Phase 8 turns a validated, stored source document into durable extracted text
and ordered chunks that later phases can embed, retrieve, and cite. It extends
the Phase 7 background-processing foundation; it does not generate embeddings,
write vectors to Qdrant, rank results, or answer chat questions.

This document is the contract for the Phase 8 model, migration, extractors,
worker tasks, services, APIs, tests, and documentation. It is intentionally
defined before parser code so every supported format has the same lifecycle and
failure guarantees.

## Completion criteria

Phase 8 is complete when all of the following are true:

- A source-integrity success queues one durable text-extraction job.
- A worker extracts supported source files without executing their content or
  making network requests.
- Cleaned text and its ordered chunks are stored transactionally and remain
  traceable to their source document and locations within extracted text.
- A successful run changes the document from `PENDING` to `READY`; no partial
  output remains visible after a failed run.
- A duplicate delivery is harmless, and an authorized retry/reprocess safely
  replaces an earlier extraction result rather than appending duplicates.
- Document readers can inspect safe extraction and chunk information under the
  existing `documents:read` policy.
- Unit tests and the Docker build cover extraction, chunking, lifecycle,
  cleanup, authorization, and migrations.

## Scope and format policy

Phase 8 processes the same upload allowlist introduced in Phase 6. An accepted
upload is not automatically an extractable document: the worker applies the
rules below after source-integrity validation.

| Format | Phase 8 extraction policy | Explicit exclusion |
| --- | --- | --- |
| Plain text (`.txt`, `text/plain`) | Decode UTF-8, allowing a UTF-8 byte-order mark. | Other encodings are not guessed or silently converted. |
| Markdown (`.md`, `.markdown`, `text/markdown`) | Decode as UTF-8 and retain readable Markdown text. | Markdown rendering, external includes, and remote content are not fetched. |
| PDF (`.pdf`, `application/pdf`) | Extract embedded, selectable text with page-location metadata when available. | OCR, password handling, JavaScript, embedded-file execution, and form processing are out of scope. |
| Word (`.docx`) | Extract readable document paragraphs and preserve their source order. | Legacy `.doc`, macros, embedded-object execution, tracked-change semantics, and layout-perfect rendering are out of scope. |

An encrypted, malformed, unreadable, unsupported-encoding, or textless source
fails safely. A scanned PDF with no embedded text therefore fails rather than
claiming that OCR occurred. Future OCR or additional formats must be introduced
as explicit pipeline stages, not hidden fallback behaviour.

## Security and resource limits

Extractors treat every source as untrusted data:

- They never execute macros, JavaScript, embedded content, or shell commands.
- They make no external network requests and do not resolve remote references.
- They run only in the existing Celery worker, subject to its configured hard
  and soft time limits.
- They read the original only through the document-storage abstraction after
  the Phase 7 integrity check.
- They enforce a bounded extracted-text size before persistence, protecting the
  worker and PostgreSQL from expansion-heavy files such as decompression bombs.

Checkpoint 8.2 will add explicit settings for the maximum extracted text and
the chunk target/overlap. The initial implementation will use a 5,000,000
character extracted-text limit, a 1,200-character target chunk size, and a
200-character overlap. These values are model-neutral defaults, not a promise
about any embedding model's token limit; Phase 9 will validate the selected
embedding model's actual token constraints.

## Processing lifecycle

`Document.status` expresses readiness of the document's content, while a
`ProcessingJob` records execution of a single pipeline stage. They must not be
treated as interchangeable.

```text
upload
  │
  ▼
PENDING + source_integrity job
  │
  ├── source integrity fails ──► FAILED
  │
  └── source integrity succeeds
          │
          ▼
     PENDING + text_extraction job
          │
          ├── worker claims job ──► PROCESSING
          │                            │
          │                            ├── extraction fails ──► FAILED
          │                            │
          │                            └── text and chunks commit ──► READY
          │
          └── document deleted ──► cancelled job; no output is retained
```

The successful Phase 7 job remains part of the document's immutable processing
history. Phase 8 creates a separate `text_extraction` job rather than changing
its meaning. A source-integrity success and creation of the extraction job will
be committed together, then dispatched through the same PostgreSQL outbox.

While the extraction job is merely queued, the document stays `PENDING`. Its
worker changes the document to `PROCESSING` only after atomically claiming the
job. It clears `processing_error` when work starts; on success it sets `READY`;
on failure it sets `FAILED` with a safe bounded message. A deleted document is
never extracted, even if an older broker message is delivered late.

## Extraction result and traceability contract

Phase 8 will persist one current extraction result per active document and its
ordered chunks. The migration in checkpoint 8.3 will represent the following
logical fields:

| Record | Required information | Purpose |
| --- | --- | --- |
| Extraction result | document ID, normalized full text, text checksum, character count, extractor version, timestamps | Identifies exactly what was produced from the source. |
| Chunk | extraction-result ID, zero-based ordinal, content, content checksum, start/end character offsets, source-location metadata | Lets later retrieval and citations point back to a stable section. |

Character offsets always refer to the normalized extracted text, not byte
offsets in the original file. This remains meaningful after a PDF parser has
removed layout information or line endings have been normalized. Source-location
metadata is additive: PDF chunks can record page ranges when available; plain
text and DOCX chunks may have only normalized-text offsets.

The original source bytes and their Phase 6 SHA-256 remain immutable. The
extraction checksum is separate because it identifies the parser's normalized
text output, not the uploaded binary.

## Text cleaning and chunking contract

The extractor produces readable text in source order. Before chunking, the
pipeline will normalize line endings, remove disallowed control characters,
preserve paragraph boundaries, and collapse only excessive blank-line runs.
It will not summarize, translate, redact, invent text, or use an LLM.

The chunker is deterministic for the same normalized text and configuration:

- chunks are emitted in source order with ordinals beginning at `0`;
- it prefers paragraph boundaries, then sentence boundaries, before splitting
  at a hard character boundary;
- adjacent chunks overlap by up to the configured overlap where text permits;
- no empty chunk is persisted;
- every chunk records its exact normalized-text character range; and
- a later reprocess with the same algorithm replaces the document's current
  result atomically instead of accumulating a second set of chunks.

The character-based policy avoids coupling Phase 8 to a future embedding
provider. Phase 9 can introduce provider-specific token measurement without
breaking the stored ordering, checksum, or traceability contract.

## Failure, retry, and reprocessing policy

External parser details, stack traces, storage paths, encryption hints, and
broker identifiers stay in worker logs. API responses and `processing_error`
use bounded messages such as:

| Condition | Safe stored/API message |
| --- | --- |
| Source cannot be read | `The stored source document could not be read.` |
| Text cannot be extracted | `Text could not be extracted from this document.` |
| No usable text | `No extractable text was found in this document.` |
| Extracted text exceeds the limit | `Extracted text exceeds the processing limit.` |
| Durable result cannot be written | `Extracted document content could not be saved.` |

Phase 7's job claim makes duplicate message delivery a no-op after completion.
For a failed extraction, the existing authorized job retry mechanism returns
the job to `QUEUED`; a later worker attempt replaces results only after it has
produced a complete valid extraction. A reprocess request for a `READY`
document will be designed as an explicit document-write operation in checkpoint
8.7. It never mutates original source metadata or bypasses the outbox.

## Authorization and API boundary

Phase 8 retains the global document permissions until Phase 12 introduces
permission-aware retrieval:

| Action | Required permission |
| --- | --- |
| Inspect extraction status, text metadata, and chunks | `documents:read` |
| Retry failed extraction or request reprocessing | `documents:write` |

The Phase 8 read API will be document-scoped. It will expose extraction and
chunk data needed to verify traceability, but no storage key, outbox payload,
broker task ID, parser exception, or raw stack trace. It is not a semantic
search endpoint and does not relax the current global document authorization
model.

## Delivery checklist

1. [x] Define the supported-format, lifecycle, traceability, resource-limit,
   failure, retry, and authorization contract (8.1).
2. [x] Add extraction adapters, dependencies, and configuration defaults (8.2).
3. [ ] Add extraction-result and chunk models with an Alembic migration (8.3).
4. [ ] Queue and dispatch the durable text-extraction pipeline stage (8.4).
5. [ ] Implement cleaning and deterministic chunking (8.5).
6. [ ] Run extraction in the worker with atomic persistence and reprocessing
   semantics (8.6).
7. [ ] Add authorized status, chunk-inspection, and reprocess APIs (8.7).
8. [ ] Complete tests, Docker verification, and consolidated documentation (8.8).
