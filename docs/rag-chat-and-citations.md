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

## 11.2 Chat-model configuration and provider boundary

Chat generation has its own `CHAT_PROVIDER`, `CHAT_MODEL`,
`CHAT_REQUEST_TIMEOUT_SECONDS`, and `CHAT_MAX_OUTPUT_TOKENS` settings. This
keeps a generation-model change from changing the embedding model or vector
shape. The existing `OPENAI_API_KEY` and `OPENAI_BASE_URL` are shared only as
the authenticated OpenAI connection settings; neither is exposed to clients.

`ChatModelProvider` receives only application-owned `developer` and `user`
messages and yields non-empty answer text fragments. The first adapter uses
OpenAI's Responses API with `stream=true`, consumes typed SSE events, and
forwards only `response.output_text.delta` values. Provider event names, raw
payloads, HTTP errors, and credentials stay inside the adapter. Future RAG code
can use a fake provider in tests or add another configured implementation
without changing retrieval, citations, or the HTTP API.

## 11.3 Safe prompt and context builder

`GroundedPromptBuilder` accepts only the already-authoritative Phase 10
retrieval results. It gives each included result a deterministic application
label (`S1`, `S2`, ...) and separates the prompt into a trusted `developer`
message and a `user` message containing explicitly delimited source data and
the question. It never accepts instructions, model controls, source labels, or
raw vector data from the client.

`CHAT_MAX_CONTEXT_CHARACTERS` bounds the combined source headers and document
text in one prompt. Sources are included in retrieval order, the final source
is truncated to fit the exact remaining budget, and later sources are omitted.
The trusted instructions explicitly treat retrieved document text as untrusted
reference data and require an insufficient-context answer when it cannot
support the question. The builder retains the verified source metadata needed
for later application-side citation validation.

## 11.4 Citation model and validation

The model may write visible labels such as `[S1]`, but labels never create a
citation by themselves. `CitationValidator` reads only source labels issued by
`GroundedPromptBuilder`, rejects unknown or malformed labels, removes repeated
references, and creates `ChatCitation` records from the original verified
document, chunk, location, and score metadata. This means the model cannot
invent a document ID, title, location, score, or source outside the retrieved
prompt context.

An answer without a source label produces no citations; the later orchestration
checkpoint decides whether that answer may be considered grounded. Citation
records remain application data and never expose Qdrant point IDs, prompts, or
provider payloads.

## 11.5 RAG orchestration service

`RagChatService` is the single workflow boundary for a chat turn. It converts
the bounded chat request into a Phase 10 retrieval request, builds a prompt
only from PostgreSQL-verified results, streams non-empty provider text
fragments, accumulates the completed answer, then validates its source labels.
It emits provider-neutral domain events; the next checkpoint serializes those
events as SSE.

No retrieval results means no model call. The service returns a fixed
insufficient-context message and a terminal completion with `answered=false`
and no citations. A model answer must contain at least one application-issued
source label; empty, uncited, unknown, or malformed source output fails before
any success completion is issued. Retrieval filters remain exactly those from
the original request.

## 11.6 SSE streaming protocol

`stream_chat_sse` is the transport adapter between `RagChatService` and the
future FastAPI route. Every SSE message has an `event:` name and one JSON
`data:` payload using the public Phase 11 schemas. A successful grounded answer
emits zero or more `answer_delta` events, then one `citations` event, then one
`done` event. Insufficient context emits its fixed answer delta followed by
`done` with `answered=false` and `citation_count=0`.

Expected retrieval, database, vector, embedding, provider, or grounding errors
become one terminal `error` event with the fixed message `Grounded chat is
temporarily unavailable`. The stream never serializes exception text, provider
events, prompt contents, credentials, or vector-store identifiers. The public
route, response headers, and authorization are deliberately deferred to 11.7.

## 11.7 Protected chat API and current RBAC

`POST /chat/stream` accepts `ChatStreamRequest` and returns
`text/event-stream`. The existing `documents:read` permission is required
before a request can enter the chat workflow. The route creates a
request-scoped chat provider, passes the service event iterator through the SSE
adapter, disables proxy buffering with `X-Accel-Buffering: no`, and closes the
provider when the stream ends or the client disconnects.

This checkpoint authorizes access at the current global permission level only.
It does not add document-owner, organization, tenant, or per-document policies;
those are explicitly Phase 12 work. Use a POST-capable streaming client such as
`fetch` or `curl -N`; browser `EventSource` is GET-only and does not support
this authenticated request body.

## Delivery checkpoints

- [x] 11.1 Chat contract and grounding policy
- [x] 11.2 Chat-model configuration and provider boundary
- [x] 11.3 Safe prompt/context builder
- [x] 11.4 Citation model and validation
- [x] 11.5 RAG orchestration service
- [x] 11.6 SSE streaming protocol
- [x] 11.7 Protected chat API
- [ ] 11.8 Optional conversation contract
- [ ] 11.9 Tests, Docker verification, and documentation
