# AegisAI

AegisAI is an enterprise-focused Retrieval-Augmented Generation (RAG) platform in development. Its goal is to let organizations securely ingest, search, and chat with internal knowledge while enforcing authentication, authorization, and—later—tenant boundaries.

The project is deliberately being built in layers: establish a dependable backend and authentication foundation first, then add RBAC before document ingestion and permission-aware retrieval.

> **Current status:** Phases 1–3 (foundation, database, and JWT authentication) are complete. Phase 4.1 has established the RBAC contract; RBAC implementation is next.

## What is implemented

- FastAPI application with OpenAPI/Swagger documentation
- PostgreSQL, SQLAlchemy 2.x, and Alembic migrations
- Docker Compose services for the API, PostgreSQL 16, and Qdrant
- Environment-based configuration with Pydantic Settings
- Health and database-health endpoints
- User registration and bcrypt password hashing
- JWT access and refresh tokens
- Refresh-token persistence, rotation, expiry checks, and soft revocation
- Protected endpoints that accept access tokens only
- Service-owned database transactions, so related writes commit or roll back together

Qdrant is provisioned as infrastructure, but document ingestion, embeddings, and RAG retrieval have not yet been implemented.

## Technology

| Area | Technology |
| --- | --- |
| API | FastAPI, Uvicorn |
| Data layer | SQLAlchemy 2.x, Alembic |
| Relational database | PostgreSQL 16 |
| Vector database | Qdrant |
| Validation and configuration | Pydantic v2, Pydantic Settings |
| Authentication | Passlib/bcrypt, python-jose JWT |
| Containers | Docker and Docker Compose |

## Architecture

The backend currently uses a layered architecture:

```text
HTTP API → service → repository → PostgreSQL
                 ↓
          security and schemas
```

`AuthService` owns authentication use cases and transaction boundaries. Repositories perform persistence operations using `flush()`; they do not independently commit changes. This allows, for example, refresh-token revocation and issuance to be committed atomically.

The current structure is:

```text
backend/
├── alembic/                 # Migration environment and revisions
├── app/
│   ├── api/                 # HTTP routes and dependencies
│   ├── core/                # Configuration, logging, exceptions
│   ├── db/                  # Engine, session, declarative base
│   ├── models/              # SQLAlchemy models
│   ├── repositories/        # Database queries and persistence
│   ├── schemas/             # Request and response models
│   ├── security/            # Hashing, JWTs, access-token dependency
│   └── services/            # Application use cases
├── Dockerfile
├── requirements.txt
└── .env.example
```

This will remain layered until RBAC and SSO introduce enough domains to justify a vertical-slice refactor.

## Quick start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ for local development

### Configure the environment

```bash
cp backend/.env.example backend/.env
```

Set a long, unique `JWT_SECRET_KEY` before using the application outside local development. The example database URL uses the Docker service hostname (`postgres`).

### Start the stack

```bash
docker compose up --build
```

The stack exposes:

- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Qdrant: `http://localhost:6333`

Apply migrations from the backend container after it starts:

```bash
docker compose exec backend alembic upgrade head
```

For local, non-containerized development, run backend commands from `backend/` so `app` is importable:

```bash
cd backend
venv/bin/uvicorn app.main:app --reload
```

## API

Interactive API documentation is available at `http://localhost:8000/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service metadata |
| `GET` | `/health` | Application health check |
| `GET` | `/database/health` | PostgreSQL connectivity check |
| `POST` | `/auth/register` | Register a user |
| `POST` | `/auth/login` | Obtain access and refresh tokens |
| `GET` | `/auth/me` | Return the current user |
| `POST` | `/auth/refresh` | Rotate a refresh token and return a new pair |
| `POST` | `/auth/logout` | Revoke a refresh token |
| `GET` | `/protected` | Example access-token-protected endpoint |

### Authentication flow

1. `POST /auth/register` accepts JSON containing `email`, `full_name`, and `password`.
2. `POST /auth/login` uses OAuth2 form data: `username` is the email and `password` is the password.
3. Login returns an access token, refresh token, access-token lifetime in seconds, and the authenticated user.
4. Send the access token as `Authorization: Bearer <access_token>` to protected routes.
5. `POST /auth/refresh` validates the stored, unrevoked refresh token; it revokes that token and issues a new token pair in one transaction.
6. `POST /auth/logout` soft-revokes the supplied refresh token.

Access and refresh token lifetimes are configured with `ACCESS_TOKEN_EXPIRE_MINUTES` and `REFRESH_TOKEN_EXPIRE_DAYS`.

## Database migrations

Run Alembic from `backend/` locally, or inside the backend container when using Compose:

```bash
cd backend
venv/bin/alembic history
venv/bin/alembic upgrade head
venv/bin/alembic current
```

After changing SQLAlchemy models, generate and review a migration before applying it:

```bash
cd backend
venv/bin/alembic revision --autogenerate -m "describe the change"
venv/bin/alembic upgrade head
```

The current migration head includes users, refresh tokens, and the `refresh_tokens.revoked_at` column used for logout and token rotation. Review generated migrations for unintended constraints, indexes, or destructive changes before applying them.

When Alembic runs on the host, use a database URL reachable from the host—normally `localhost`, not the Compose-only hostname `postgres`.

## Current schema

All models inherit `id`, `created_at`, and `updated_at` from the declarative base.

### `users`

```text
id, email, full_name, password_hash, is_active,
created_at, updated_at, last_login
```

### `refresh_tokens`

```text
id, token, expires_at, revoked_at, user_id,
created_at, updated_at
```

## Roadmap

- [x] Phase 1 — Foundation and containerized services
- [x] Phase 2 — Database layer and Alembic
- [x] Phase 3 — Authentication, refresh-token lifecycle, and transaction boundaries
- [x] Phase 4.1 — RBAC contract and canonical permission catalogue
- [ ] Phase 4 — RBAC: roles, permissions, assignments, and authorization dependencies
- [ ] Phase 5 — Enterprise SSO: Google, GitHub, and Microsoft Entra ID
- [ ] Phase 6 — Document management and ingestion
- [ ] Phase 7 — Background processing with Redis/Celery
- [ ] Phase 8 — Text extraction and chunking
- [ ] Phase 9 — Embeddings and Qdrant indexing
- [ ] Phase 10 — Retrieval engine and metadata filtering
- [ ] Phase 11 — RAG chat with streaming and citations
- [ ] Phase 12 — Permission-aware retrieval
- [ ] Phase 13 — Audit logging
- [ ] Phase 14 — Admin dashboard
- [ ] Phase 15 — Next.js frontend
- [ ] Phase 16 — Observability
- [ ] Phase 17 — CI/CD
- [ ] Phase 18 — Kubernetes
- [ ] Phase 19 — Multi-tenancy
- [ ] Phase 20 — Enterprise features such as API keys, rate limiting, and retention policies

## Development workflow

1. Create a focused branch.
2. Change application code and SQLAlchemy models as needed.
3. Generate, inspect, and apply an Alembic migration for schema changes.
4. Validate the affected API flow and migration state.
5. Commit the application changes and migration together.
