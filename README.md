# AegisAI

AegisAI is a secure, enterprise-oriented knowledge platform in development. It lets organizations ingest internal content, retrieve it safely, and chat with it through a grounded RAG experience.

The backend foundation, document ingestion, background processing, text processing, embeddings, semantic retrieval, grounded streaming chat, and permission-aware access controls are complete: containerized FastAPI services, PostgreSQL, JWT authentication, database-backed RBAC, enterprise SSO, secure document management, Redis/Celery workers, traceable chunks, validated Qdrant indexing, PostgreSQL-authoritative search, direct document sharing, and citation-verified RAG responses.

## Overview

### What is available now

| Capability | Status | Outcome |
| --- | --- | --- |
| API and local platform | Available | FastAPI API, PostgreSQL 16, Qdrant, Docker Compose, health checks, and Alembic migrations. |
| Local authentication | Available | User registration, bcrypt password hashing, short-lived access JWTs, rotatable refresh tokens, logout, and inactive-user protection. |
| Authorization | Available | Local roles and permissions, administrator bootstrap, request-time RBAC, and direct document read/write sharing. |
| Enterprise SSO | Available | Google OpenID Connect, GitHub OAuth, and Microsoft Entra ID adapters with PKCE, signed state, nonce validation, account linking, and local AegisAI sessions. |
| Document ingestion | Available | RBAC-protected upload, metadata management, local persistent original-file storage, SHA-256 integrity metadata, and soft deletion. |
| Background processing | Available | Redis/Celery workers verify durable uploaded sources outside HTTP requests, with PostgreSQL-backed job state, retries, cancellation, and failure handling. |
| Knowledge processing | Available | Workers safely extract supported files, normalize text, create deterministic chunks, and persist traceable output for later embedding. |
| Vector indexing | Available | Workers queue and process OpenAI embeddings into validated Qdrant collections with traceable PostgreSQL records, cleanup, and safe progress visibility. |
| Semantic retrieval | Available | Bounded metadata-filtered search validates Qdrant candidates against current PostgreSQL documents, chunks, and embedding records. |
| RAG chat | Available | RBAC-protected RAG chat streams grounded answers and verified citations, with bounded client-supplied history. |
| Web application | Available locally | Next.js browser workspace for authentication, documents, search, grounded chat, and administration; FastAPI remains authoritative. |

Qdrant is already provisioned as local infrastructure. Phase 6 stores original document bytes in the persistent local `document_data` volume and metadata in PostgreSQL; Phase 9.6 automatically indexes document vectors after extraction when `OPENAI_API_KEY` is configured.

### Technology

| Area | Technology |
| --- | --- |
| API | FastAPI and Uvicorn |
| Web application | Next.js 16, React, and TypeScript |
| Application and data layer | Python 3.12, SQLAlchemy 2.x, Alembic |
| Relational database | PostgreSQL 16 |
| Vector database | Qdrant |
| Identity and authorization | Passlib/bcrypt, python-jose JWT, local RBAC, OAuth 2.0/OpenID Connect adapters |
| Configuration and validation | Pydantic v2 and Pydantic Settings |
| Local platform | Docker and Docker Compose |

### Delivery progress

| Milestone | Status | Delivered or planned outcome |
| --- | --- | --- |
| Phases 1–5 — Foundation, data, identity, and access control | Complete | Containerized backend, migrations, local authentication, RBAC, and enterprise SSO. |
| Phase 6 — Document ingestion | Complete | Secure local storage, upload validation, metadata lifecycle, RBAC enforcement, and document-management APIs. |
| Phase 7 — Background processing | Complete | Redis/Celery runtime, durable outbox delivery, worker integrity checks, job status, retry, and cancellation. |
| Phase 8 — Text extraction and chunking | Complete | Safe TXT/Markdown/PDF/DOCX extraction, normalized traceable chunks, worker lifecycle, reprocessing, and RBAC-protected inspection APIs. |
| Phase 9 — Embeddings and Qdrant indexing | Complete | OpenAI embedding boundary, Qdrant collection safety, durable indexing and cleanup jobs, traceable vector records, and safe status visibility. |
| Phase 10 — Retrieval and metadata filtering | Complete | Query embedding, safe Qdrant search, controlled filters, PostgreSQL authority checks, deterministic ranking, and RBAC-protected search API. |
| Phase 11 — RAG chat, streaming, and citations | Complete | RBAC-protected streaming answers, bounded untrusted client history, verified citations, safe failures, and no persisted transcript. |
| Phase 12 — Permission-aware retrieval | Complete | Direct document sharing filters document APIs, retrieval, RAG context, and citations; tenant isolation remains Phase 19. |
| Phase 13 — Audit logging | Complete | Append-only security events, privacy-safe read telemetry, and protected audit queries. |
| Phase 14 — Administration control plane | Complete | Secure APIs for users, RBAC summaries, document/job operations, and operational overview. |
| Phase 15 — Next.js frontend | Complete | Browser workspace, server-managed sessions, document/search/chat, administration, and full Compose verification are complete. |
| Phase 16 — Observability | Complete | Privacy-safe JSON logs and request correlation, safe failure telemetry, liveness/readiness, Prometheus metrics, worker task signals, and operating guidance. |
| Phases 17–20 — Production scale | Planned | CI/CD, Kubernetes, multi-tenancy, API keys, rate limits, and retention controls. |

### Engineering documents

- [RBAC design](docs/rbac.md) explains the current role and permission model.
- [Document ingestion design](docs/document-ingestion.md) defines the implemented Phase 6 storage, lifecycle, authorization, and API contract.
- [Background processing design](docs/background-processing.md) defines the implemented Phase 7 job, outbox, worker, and retry contract.
- [Text extraction and chunking design](docs/text-extraction-and-chunking.md) defines the implemented Phase 8 format, lifecycle, traceability, safety, and manual-verification contract.
- [Embeddings and Qdrant indexing design](docs/embeddings-and-qdrant-indexing.md) defines the Phase 9 vector, lifecycle, idempotency, and safety contract.
- [Retrieval and metadata filtering design](docs/retrieval-and-metadata-filtering.md) defines the implemented Phase 10 search contract, authority checks, API, and verification workflow.
- [RAG chat and citations design](docs/rag-chat-and-citations.md) defines the implemented Phase 11 grounding, streaming, citation, and verification contract.
- [Permission-aware retrieval design](docs/permission-aware-retrieval.md) defines the implemented Phase 12 document-access policy, sharing API, and verification contract.
- [Audit logging design](docs/audit-logging.md) defines the active Phase 13 event policy, data-minimization rules, and delivery checkpoints.
- [Administrative control-plane design](docs/admin-dashboard.md) defines the implemented Phase 14 permissions, routes, safety boundaries, and verification workflow.
- [Frontend design](docs/frontend.md) defines the active Phase 15 browser architecture, session policy, screen map, and safety boundaries.
- [Observability design](docs/observability.md) defines the active Phase 16 telemetry, privacy, health, and operations contract.

## Architecture

### Runtime architecture

```text
                                  Available now

 Browser, CLI, or future frontend
              │
              ▼
        FastAPI API :8000
              │
    ┌─────────┼───────────────────────────────────────────────┐
    │         │                                               │
    ▼         ▼                                               ▼
Local login  Enterprise SSO                              Protected route
or refresh   Google | GitHub | Entra                         dependency
    │         │                                               │
    └────┬────┘                                               ▼
         ▼                                      authenticate access JWT
  AuthService / SsoAccountService                            │
         │                                                    ▼
         ▼                                        evaluate local RBAC policy
  AegisAI access + refresh tokens                            │
         │                                                    ▼
         └───────────────► PostgreSQL ◄──────────── allow or deny request
                             users
                             refresh_tokens
                             external_identities
                             roles / permissions

Documents ──► PostgreSQL outbox ──► Redis ──► Celery workers
                                           │
                                           ▼
                         source integrity ──► extraction and chunks
                                           │
                                           ▼
                              PostgreSQL extraction/chunk records

                                  Available now

                     embeddings ──► Qdrant ──► semantic retrieval ──► RAG chat + citations
                                                                    │
                                                                    ▼
                                                          streamed SSE response
```

The backend follows a layered design so that HTTP, business rules, and persistence remain independently testable:

```text
API routes and dependencies → services → repositories → PostgreSQL
                                 │
                           schemas and security
```

Services own transaction boundaries. Repositories add, query, flush, and delete records but do not independently commit, so related changes either commit together or roll back together.

### Authentication and authorization

Authentication establishes a local AegisAI user. Authorization then decides whether that user may perform a specific action.

```text
Password login or verified SSO identity
                 │
                 ▼
      local AegisAI user and session
      access JWT + persisted refresh token
                 │
                 ▼
       Authorization: Bearer <access JWT>
                 │
                 ▼
       get_current_user validates token and loads user
                 │
                 ▼
 require_permission checks PostgreSQL-backed RBAC
                 │
        ┌────────┴────────┐
        ▼                 ▼
     HTTP 403          route handler
```

The access JWT contains identity and token metadata, not permissions. Each permission-aware request checks PostgreSQL, so a role or permission change applies immediately instead of waiting for an old JWT to expire.

RBAC is represented by the following relationships:

```text
users ──< user_roles >── roles ──< role_permissions >── permissions
```

A user can have several roles, and a role can grant several permissions. The seeded `administrator` system role has every currently defined permission. Local roles are the only authorization source: SSO provider roles, groups, and access tokens are never copied into AegisAI authorization decisions.

### Enterprise SSO behavior

SSO supports Google, GitHub, and Microsoft Entra ID. The browser flow uses short-lived signed state, PKCE, and OIDC nonce validation where applicable. Provider tokens are used only to verify identity; AegisAI issues and stores its own tokens.

The local-account policy is deliberately conservative:

1. An existing unique `(provider, provider_subject)` binding always resolves to its linked AegisAI user.
2. A new provider identity can link to an existing local user only when the provider supplies a verified email that exactly matches that user.
3. Otherwise, a verified-email identity receives a just-in-time local AegisAI account and identity binding.
4. An identity without a verified email is rejected rather than allowed to create or take over an account.

Just-in-time SSO users receive an unknown, cryptographically random password hash. This keeps the existing user model consistent without creating a password credential that anyone knows. An inactive user cannot create or refresh an AegisAI session.

## Quick start

### Prerequisites

- Docker Engine and Docker Compose
- A free local port for each of `8000`, `5432`, and `6333`

### Start the full local stack

Create the local configuration file once:

```bash
cp backend/.env.example backend/.env
```

Set a long, unique `JWT_SECRET_KEY` in `backend/.env` before using the application outside local experimentation. Keep SSO disabled until at least one provider is configured.

Then run the one canonical startup command from the repository root:

```bash
docker compose up --build --force-recreate
```

That command builds the backend image, runs unit tests during image build, validates the Alembic migration chain, waits for PostgreSQL to become healthy, runs the tests again, applies `alembic upgrade head` to PostgreSQL, and starts Uvicorn. The backend does not start if its tests or migration fail.

When startup completes:

| Service | URL |
| --- | --- |
| API | `http://localhost:8000` |
| Web application | `http://localhost:3000` |
| Health check | `http://localhost:8000/health` |
| Readiness check | `http://localhost:8000/health/ready` |
| Prometheus metrics | `http://localhost:8000/health/metrics` |
| Interactive OpenAPI docs | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5432` |
| Qdrant API | `http://localhost:6333` |

### Everyday local operations

```bash
# Follow backend startup and application logs
docker compose logs -f backend

# Check service state
docker compose ps

# Stop services while retaining PostgreSQL and Qdrant volumes
docker compose down

# Repeat the complete build, test, migrate, and start workflow
docker compose up --build --force-recreate
```

Docker Compose is the supported local-development workflow. It is not yet a production deployment recipe; production hardening, observability, CI/CD, Kubernetes, and multi-tenancy are planned later.

## Configuration

Copy [backend/.env.example](backend/.env.example) to `backend/.env`. Do not commit `backend/.env`, OAuth client secrets, JWT secrets, refresh tokens, or access tokens.

### Core settings

| Setting | Purpose |
| --- | --- |
| `APP_NAME`, `APP_VERSION`, `APP_ENV` | Application identity and environment label. |
| `HOST`, `PORT` | Backend listener configuration. Compose exposes port `8000`. |
| `DATABASE_URL` | PostgreSQL connection URL. Inside Compose, the hostname must remain `postgres`. |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME` | Qdrant connection and active derived-vector collection. A key is optional for local Docker. |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_VECTOR_DIMENSION` | Active embedding shape. Changing the dimension requires a new collection and deliberate reindex. |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | Shared OpenAI endpoint and secret for configured embedding and chat providers. The key is required only when an indexing, retrieval, or chat operation uses OpenAI. |
| `CHAT_PROVIDER`, `CHAT_MODEL`, `CHAT_REQUEST_TIMEOUT_SECONDS`, `CHAT_MAX_OUTPUT_TOKENS`, `CHAT_MAX_CONTEXT_CHARACTERS` | Phase 11 streaming-generation provider, model, request timeout, output budget, and bounded verified-source prompt context. These do not change the embedding collection shape. |
| `DOCUMENT_STORAGE_PATH` | Local original-document storage path. Compose mounts the persistent `document_data` volume at this path. |
| `DOCUMENT_MAX_UPLOAD_BYTES` | Maximum streamed upload size. The default is 25 MiB and is enforced by the upload service. |
| `DOCUMENT_MAX_EXTRACTED_TEXT_CHARACTERS` | Maximum parser output retained from one document; default 5,000,000 characters. |
| `DOCUMENT_CHUNK_TARGET_CHARACTERS`, `DOCUMENT_CHUNK_OVERLAP_CHARACTERS` | Model-neutral Phase 8 chunking defaults: 1,200 target characters with 200 characters of context overlap. |
| `JWT_SECRET_KEY` | Long, unique secret used to sign AegisAI access and refresh JWTs. |
| `JWT_ALGORITHM` | JWT signing algorithm; the supplied configuration uses `HS256`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Local token lifetimes. |

### Optional SSO settings

SSO is disabled by default. Enable it only after configuring one provider application and registering its exact redirect URI.

| Setting | Purpose |
| --- | --- |
| `SSO_ENABLED` | Enables provider-based browser sign-in. |
| `SSO_CALLBACK_BASE_URL` | Public API base URL used to build provider redirect URIs. Use HTTPS in deployed environments. |
| `SSO_STATE_SECRET_KEY` | A distinct long random secret for signed, temporary SSO state. Do not reuse `JWT_SECRET_KEY`. |
| `SSO_TRANSACTION_EXPIRE_MINUTES` | Short expiry for state, PKCE, and nonce transaction data. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OpenID Connect web-application credentials. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub OAuth application credentials. |
| `MICROSOFT_ENTRA_CLIENT_ID`, `MICROSOFT_ENTRA_CLIENT_SECRET` | Microsoft Entra ID application credentials. |
| `MICROSOFT_ENTRA_TENANT_ID` | A tenant ID to restrict Entra sign-in, or `organizations` only when multi-tenant organizational access is intended. |

Register one exact callback URL for each configured provider:

```text
{SSO_CALLBACK_BASE_URL}/auth/sso/google/callback
{SSO_CALLBACK_BASE_URL}/auth/sso/github/callback
{SSO_CALLBACK_BASE_URL}/auth/sso/microsoft/callback
```

For production, use a publicly reachable HTTPS callback base URL, distinct random secrets, and a tenant-specific Entra ID whenever access should be limited to one organization.

## Using the API

OpenAPI documentation is available at `http://localhost:8000/docs`. It is the complete live endpoint contract; the summary below highlights the current API surface.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service metadata. |
| `GET` | `/health` | Application health check. |
| `GET` | `/health/ready` | Required local dependency readiness: PostgreSQL, Redis, and Qdrant. |
| `GET` | `/health/metrics` | Prometheus-format operational metrics; expose internally only outside local development. |
| `GET` | `/database/health` | PostgreSQL connectivity check. |
| `POST` | `/auth/register` | Create a local email/password user. |
| `POST` | `/auth/login` | Exchange OAuth2 form credentials for AegisAI tokens. |
| `GET` | `/auth/me` | Return the authenticated local user. |
| `POST` | `/auth/refresh` | Rotate a valid refresh token and return a new pair. |
| `POST` | `/auth/logout` | Soft-revoke a refresh token. |
| `GET` | `/auth/sso/{provider}` | Start a browser SSO flow for `google`, `github`, or `microsoft`. |
| `GET` | `/protected` | Minimal protected-route example. |
| `/rbac/*` | See the RBAC section below | Manage roles and assignments with administrator permissions. |
| `POST` | `/documents` | Upload an allowed document with `documents:write`. |
| `GET` | `/documents?offset=0&limit=25` | List document metadata with `documents:read`. |
| `GET`, `PATCH`, `DELETE` | `/documents/{document_id}` | Inspect with `documents:read`; rename or delete with `documents:write`. |
| `GET` | `/documents/{document_id}/processing-jobs` | Inspect safe job history with `documents:read`. |
| `POST` | `/documents/{document_id}/processing-jobs/{job_id}/retry` | Requeue one failed job with `documents:write`. |
| `GET` | `/documents/{document_id}/indexing-status` | Inspect current vector progress and safe indexing state with `documents:read`. |
| `GET` | `/documents/{document_id}/access` | List direct grants with document-level write access. |
| `PUT`, `DELETE` | `/documents/{document_id}/access/{user_id}` | Create/update or revoke a direct `read`/`write` grant with document-level write access. |
| `POST` | `/retrieval/search` | Perform bounded semantic search with metadata filters and `documents:read`. |
| `POST` | `/chat/stream` | Stream a grounded answer and verified citations with `documents:read`. |
| `GET` | `/documents/{document_id}/extraction` | Inspect safe extraction metadata with `documents:read`. |
| `GET` | `/documents/{document_id}/extraction/chunks` | Inspect ordered, paginated chunks with `documents:read`. |
| `POST` | `/documents/{document_id}/reprocess` | Queue replacement extraction with `documents:write`; returns `202 Accepted`. |

### Local login and token use

1. Register through `POST /auth/register`, or create a local user through a verified SSO flow.
2. Use `POST /auth/login` with OAuth2 form data (`username` is the email) for password login.
3. Send the returned access token to protected routes.
4. Send the refresh token only to `/auth/refresh` or `/auth/logout`; do not use it as a bearer token.

```bash
curl http://localhost:8000/auth/me \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

### Document management

`POST /documents` accepts one multipart `file` field. PDFs, DOCX, TXT, and
Markdown are supported, and the default streamed limit is 25 MiB. The server
derives the title, generates the storage key, and records the authenticated
uploader; clients never supply a storage path or uploader ID.

Document actions require both a global RBAC permission and per-document access.
The uploader is the implicit owner; a direct `read` or `write` grant can share
the document with another active local user, while `documents:manage` is the
explicit administrator override. Unauthorized resources are hidden as `404`.
Retrieval, chat context, and citations use the same policy. See the
[permission-aware retrieval design](docs/permission-aware-retrieval.md) for the
sharing API and policy, and the [document ingestion design](docs/document-ingestion.md)
for lifecycle and storage behavior.

After an upload, the durable outbox sends source validation and then text
extraction to the worker. A successful extraction makes the document `READY`.
Readers can inspect only extraction metadata and bounded chunk pages; original
storage keys, broker identifiers, and parser errors stay internal. See the
[text extraction and chunking design](docs/text-extraction-and-chunking.md)
for the lifecycle and a manual verification walkthrough.

### Vector indexing

Set `OPENAI_API_KEY` in the uncommitted `backend/.env` to enable real vector
generation. After a document reaches `READY`, its worker queues an
`embedding_indexing` job. Inspect its safe progress without exposing vector,
Qdrant, or provider details:

```bash
curl http://localhost:8000/documents/DOCUMENT_ID/indexing-status \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

The caller needs `documents:read`. A `succeeded` response means every current
chunk has a traceable vector in the configured collection. If `indexing_status`
is `failed`, inspect the safe job history and retry that specific failed job
with `documents:write`; do not retry while it is `queued` or `running`.
Changing `EMBEDDING_MODEL` or `EMBEDDING_VECTOR_DIMENSION` requires a new
`QDRANT_COLLECTION_NAME` and deliberate reprocessing. Never delete or alter an
existing collection just to make a changed configuration fit.

### Semantic retrieval

Set `OPENAI_API_KEY` in the uncommitted `backend/.env`, upload and process a
supported document, and wait until its indexing status is `succeeded`. Then
search with the same access token:

```bash
curl -X POST http://localhost:8000/retrieval/search \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"query":"refresh token rotation","limit":5}'
```

Optional filters are controlled document IDs and supported MIME types:

```json
{
  "query": "retention policy",
  "limit": 5,
  "document_ids": [12, 18],
  "content_types": ["text/markdown", "application/pdf"]
}
```

The caller needs `documents:read` and receives only chunks from documents they
can currently read. Results contain current chunk text, source locations,
document metadata, and similarity scores; Qdrant candidates are always checked
against PostgreSQL access policy before they are returned.

For a safe manual end-to-end dataset, use the 30 fictional files in
[sample-data/knowledge-base](sample-data/knowledge-base/README.md). They include
overlapping topics that make ingestion, retrieval, citations, and
document-level authorization easy to verify without real internal data.

### Grounded RAG chat

After at least one relevant document is indexed, use a POST-capable streaming
client (not browser `EventSource`) to request a grounded answer:

```bash
curl --no-buffer -N -X POST http://localhost:8000/chat/stream \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"question":"How are refresh tokens rotated?","retrieval_limit":5}'
```

The SSE response contains `answer_delta` fragments and, for a grounded answer,
terminal `citations` then `done` events. The citations are generated from the
current PostgreSQL-verified retrieval results; model labels alone never create
them. If no verified context is available, `done` reports `answered: false` and
the server does not call the chat model. The route requires `documents:read`
and can use only documents the requester is authorized to read.

Optional `history` is stateless, bounded to ten alternating complete prior
messages, and treated as untrusted transcript data. It is not stored by AegisAI
or used as evidence. See the [RAG chat design](docs/rag-chat-and-citations.md)
for the event and safety contract.

### Browser SSO and Swagger

Start browser SSO by visiting, for example:

```text
http://localhost:8000/auth/sso/google
```

After a successful provider sign-in, AegisAI returns its own access and refresh tokens, plus the local user and provider name. The callback response is marked `Cache-Control: no-store`, and the temporary SSO transaction cookie is cleared.

To test an SSO session in Swagger:

1. Copy only the returned `access_token`.
2. Open `/docs` and select **Authorize**.
3. Choose **AegisAI access token**.
4. Paste the raw JWT without the `Bearer ` prefix; Swagger adds that header prefix.
5. Call `GET /auth/me` or another protected endpoint.

The separate **OAuth2PasswordBearer** option in Swagger is for local password login. Both documentation options reach the same JWT validation and RBAC checks.

### RBAC administration

The current permission catalogue contains:

```text
documents:read     documents:write
documents:manage
users:read         users:manage
roles:read         roles:manage         roles:assign
```

The `/rbac` management API requires both an active local user and the indicated database-backed permission.

| Endpoint group | Required permission | Purpose |
| --- | --- | --- |
| `GET /rbac/permissions`, `GET /rbac/roles`, role-permission reads | `roles:read` | View the permission catalogue, roles, and grants. |
| Role creation/deletion and role-permission changes | `roles:manage` | Manage non-system roles and their permissions. |
| User-role reads | `users:read` | View a user's role assignments. |
| User-role assignment/removal | `roles:assign` | Grant or revoke roles. |

Bootstrap the first administrator only after that user exists locally (through registration or SSO):

```bash
docker compose exec backend python -m scripts.bootstrap_administrator admin@example.com
```

The command is idempotent. New SSO users have no role by default, so protected RBAC management calls correctly return HTTP 403 until an administrator grants an appropriate local role.

## Testing, migrations, and development

### Run tests locally

Run backend Python commands from `backend/`; that directory makes the `app` package importable.

```bash
cd backend
venv/bin/python -m unittest discover -s tests -v
```

The unit suite uses isolated SQLite databases and mocks where appropriate. It covers API handlers, services, repositories, JWT handling, refresh-token rotation, RBAC enforcement, SSO provider adapters, account linking, session issuance, document cleanup, background-job state, extraction, chunking, reprocessing, embedding validation and idempotency, Qdrant collection safety, document-access grants, permission-aware retrieval, grounded chat and SSE behavior, Swagger security schemes, migrations, and application startup.

The Dockerfile runs this suite during image build and produces the complete Alembic upgrade SQL. Compose runs the suite again before applying migrations and launching the API.

### Work with migrations

Compose normally applies migrations automatically at startup. For development work, run Alembic from `backend/`:

```bash
cd backend
venv/bin/alembic history
venv/bin/alembic revision --autogenerate -m "describe the change"
venv/bin/alembic upgrade head
venv/bin/alembic current
```

Review every generated migration before applying it, particularly constraint and index changes. The current migration chain creates users, refresh tokens, RBAC tables and seeded permissions, the `administrator` system role, external-identity bindings, documents, direct document-access grants, processing/outbox records, extraction/chunk records, embedding pointers, and durable vector-cleanup requests.

When running Alembic from the host, use a database URL reachable from the host—normally `localhost`, not Compose's internal `postgres` hostname. `ALEMBIC_DATABASE_URL` can override the configured database URL for that command.

### Repository layout

```text
.
├── backend/
│   ├── alembic/             # Migration environment and revisions
│   ├── app/
│   │   ├── api/             # HTTP routes and FastAPI dependencies
│   │   ├── core/            # Settings, logging, and domain exceptions
│   │   ├── db/              # Engine, sessions, and declarative base
│   │   ├── integrations/    # External provider adapters, including SSO
│   │   ├── models/          # SQLAlchemy models
│   │   ├── repositories/    # Database queries and persistence operations
│   │   ├── schemas/         # Request and response contracts
│   │   ├── security/        # Password hashing, JWTs, RBAC guards, SSO state
│   │   └── services/        # Transactional application use cases
│   ├── scripts/             # Startup and administrator bootstrap commands
│   ├── tests/               # Unit and API-boundary tests
│   ├── Dockerfile
│   └── .env.example
└── docker-compose.yaml      # Local API, PostgreSQL, and Qdrant stack
```

## Security notes

- Keep `backend/.env`, OAuth secrets, JWTs, and refresh tokens out of source control, issue trackers, screenshots, and shared terminal output.
- Rotate a token if it is exposed. `/auth/logout` revokes its refresh token; the associated access token remains valid only until its configured short expiry.
- Keep `JWT_SECRET_KEY` and `SSO_STATE_SECRET_KEY` distinct to limit the impact of a compromised secret.
- Register exact HTTPS OAuth callback URLs in deployed environments. OAuth providers reject mismatched redirect URIs.
- Provider access tokens are not returned as AegisAI session tokens and are not used for AegisAI authorization.
- The current project has no published vulnerability-reporting policy. Do not disclose security-sensitive material in a public issue.

## Roadmap

The next implementation milestones are:

1. **Phase 13:** audit logging.
2. **Phase 14:** administration dashboard.
3. **Phase 15:** Next.js frontend.
4. **Phase 16:** observability.
5. **Phase 17:** CI/CD.
6. **Phase 18:** Kubernetes.
7. **Phase 19:** multi-tenancy.
8. **Phase 20:** enterprise API keys, rate limits, and retention policies.
