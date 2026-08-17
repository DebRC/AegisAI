# RAG chat, streaming, and citations design

## Purpose

Phase 11 turns Phase 10's PostgreSQL-verified retrieval results into grounded,
streamed answers. The chat model receives bounded, labeled chunk context and
the application issues citations only for those verified sources. Phase 11 does
not persist conversations, add tenant isolation, or replace the current global
`documents:read` retrieval permission; those decisions belong to later phases.

## 11.1 Chat contract and grounding policy

The future endpoint is `POST /chat/stream`. The route and provider are deferred
until later checkpoints, but its public contract is now fixed.

`ChatStreamRequest` accepts one whitespace-normalized `question`, a bounded
`retrieval_limit` from 1 through 10 (default 6), and the same controlled
`document_ids` and `content_types` filters as Phase 10. Clients cannot override
the model, system instructions, collection, score threshold, source labels, or
raw Qdrant filters. Follow-up message history is deliberately deferred to 11.8.

The endpoint will use Server-Sent Events (SSE) with these JSON data payloads:

| Event | Meaning |
| --- | --- |
| `answer_delta` | A non-empty answer fragment. |
| `citations` | The terminal list of application-issued citations for a grounded answer. |
| `done` | Terminal success event. `answered=false` and zero citations means insufficient verified context. |
| `error` | Safe terminal operational failure; no provider, database, or credential details. |

Each citation has an application-generated source ID (`S1`, `S2`, ...), document
and chunk identity, document title/type, source locations, and retrieval score.
The model may be instructed to refer to source IDs, but later citation validation
will reject any ID that was not supplied in the verified prompt context.

Grounding policy:

1. Use only current retrieval results that Phase 10 validated against PostgreSQL.
2. Do not answer factual questions from model knowledge when verified context is
   absent or insufficient; return a clear insufficient-context completion.
3. Do not treat model-generated citation text as authoritative.
4. Never stream provider internals, prompts containing hidden instructions,
   credentials, point IDs, collections, or raw exception details.

## Delivery checkpoints

- [x] 11.1 Chat contract and grounding policy
- [ ] 11.2 Chat-model configuration and provider boundary
- [ ] 11.3 Safe prompt/context builder
- [ ] 11.4 Citation model and validation
- [ ] 11.5 RAG orchestration service
- [ ] 11.6 SSE streaming protocol
- [ ] 11.7 Protected chat API
- [ ] 11.8 Optional conversation contract
- [ ] 11.9 Tests, Docker verification, and documentation
