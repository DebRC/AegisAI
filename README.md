# AegisAI

AegisAI is an enterprise-focused Retrieval-Augmented Generation (RAG) platform in development. Its goal is to let organizations securely ingest, search, and chat with internal knowledge while enforcing authentication, authorization, and—later—tenant boundaries.

The project is deliberately being built in layers: establish a dependable backend and authentication foundation first, then add RBAC before document ingestion and permission-aware retrieval.

> **Current status:** Phases 1–4 (foundation, database, JWT authentication, and RBAC) are complete. Phase 4 established database-backed roles, permissions, management APIs, request-time authorization enforcement, and operational verification.

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

### Container startup architecture

```text
docker compose up --build --force-recreate
                    │
                    ▼
          PostgreSQL health check passes
                    │
                    ▼
      backend/scripts/start_backend.sh
        ├── run unit tests
        ├── alembic upgrade head
        └── exec Uvicorn (FastAPI API)
                    │
                    ▼
       API :8000  •  PostgreSQL :5432  •  Qdrant :6333
```

The backend does not start when the tests or database migration fail. PostgreSQL
is persistent in the `postgres_data` Docker volume; Qdrant persists data in
`qdrant_data`.

### Authentication and authorization architecture

Authentication answers **who is making this request?** Authorization answers **may that authenticated user perform this action?** They are separate checks that happen in order:

```text
Client
  │
  ├── POST /auth/login (email + password)
  │     AuthService verifies the password and creates a token pair
  │
  └── receives:
        access JWT: short-lived proof of identity
        refresh JWT: longer-lived token used only to obtain a new pair
```

For every protected request, the backend first authenticates the access token:

```text
Authorization: Bearer <access JWT>
                │
                ▼
       get_current_user dependency
       1. Verify JWT signature and expiry
       2. Require token type = access
       3. Read the user ID from the token subject
       4. Load that user from PostgreSQL
                │
                ▼
       authenticated User, or HTTP 401
```

RBAC then authorizes the authenticated user against the permission required by the route:

```text
authenticated User + required permission (for example, documents:read)
                │
                ▼
       require_permission dependency
                │
                ▼
PostgreSQL source of truth
users ──< user_roles >── roles ──< role_permissions >── permissions
                │                                      │
          a user may have                       documents:read
          several roles                         roles:manage
                                               users:manage
                │
                ▼
       permission assigned through any role?
          ├── yes → run the route handler
          └── no  → HTTP 403 Forbidden
```

The access JWT contains identity and token metadata, not a list of permissions. Keeping permissions in PostgreSQL means an administrator can change a user's role or a role's permissions and the next request uses the new policy without waiting for an old JWT to expire. The trade-off is one authorization query per protected, permission-aware request. This is the safer default for enterprise controls; caching can be introduced later only with deliberate invalidation rules.

The seeded `administrator` system role is assigned every permission in the canonical catalogue. It is the initial operational access path, while regular roles and their assignments are managed through protected administrative APIs. `require_permission()` composes with `get_current_user`, so routes declare their required permission instead of implementing JWT or role checks themselves.

### Enterprise SSO configuration (Phase 5.1)

SSO is an additional authentication method. Email/password login remains available, and a successful SSO login will eventually create the same local access and refresh token pair described above. Roles and permissions remain attached to the local AegisAI user, not to provider-specific claims.

SSO is disabled by default. Copy the values from `backend/.env.example` into `backend/.env`, then set `SSO_ENABLED=true` only after configuring at least one provider application. Keep provider secrets and `SSO_STATE_SECRET_KEY` out of version control.

| Setting | Purpose |
| --- | --- |
| `SSO_CALLBACK_BASE_URL` | Public base URL of this API. In production this must be an HTTPS address reachable by the identity provider. |
| `SSO_STATE_SECRET_KEY` | A distinct, long random secret used to sign temporary OAuth state. It is separate from the JWT signing secret to limit blast radius. |
| `SSO_TRANSACTION_EXPIRE_MINUTES` | Lifetime of the signed browser transaction holding temporary state, PKCE, and nonce values. Keep this short; the default is five minutes. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Credentials for a Google OpenID Connect web application. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Credentials for a GitHub OAuth application. |
| `MICROSOFT_ENTRA_CLIENT_ID`, `MICROSOFT_ENTRA_CLIENT_SECRET` | Credentials for a Microsoft Entra ID OpenID Connect application. |
| `MICROSOFT_ENTRA_TENANT_ID` | Entra directory ID, or `organizations` while intentionally allowing organizational accounts from multiple tenants. |

Phase 5 will register one redirect URI per provider, all handled by AegisAI:

```text
{SSO_CALLBACK_BASE_URL}/auth/sso/google/callback
{SSO_CALLBACK_BASE_URL}/auth/sso/github/callback
{SSO_CALLBACK_BASE_URL}/auth/sso/microsoft/callback
```

For production, do not use the localhost example URLs. Register the exact HTTPS callback URLs with each provider; OAuth providers reject redirect URIs that do not match exactly. Use a tenant-specific Entra ID value whenever AegisAI is intended for one organization, rather than accepting identities from every organization.

The callback flow uses short-lived, signed `state` values to bind the callback to the login request, PKCE to protect authorization-code exchange, and `nonce` validation for OpenID Connect ID tokens. Google and Entra ID supply OpenID Connect identity tokens; GitHub's OAuth flow retrieves the authenticated profile and verified email through GitHub's API. Provider access tokens are used only for this exchange and profile lookup, never returned as AegisAI session tokens or stored as a substitute for local authorization.

### SSO browser flow (Phase 5.4)

`GET /auth/sso/{provider}` begins a browser login for `google`, `github`, or `microsoft`. It generates random state, PKCE, and nonce values; stores them only in a signed, `HttpOnly`, `SameSite=Lax` temporary cookie scoped to that provider's callback path; then redirects to the provider. The cookie expires after `SSO_TRANSACTION_EXPIRE_MINUTES` (five minutes by default). It is marked `Secure` whenever `SSO_CALLBACK_BASE_URL` uses HTTPS.

`GET /auth/sso/{provider}/callback` requires the provider's returned state to match the signed cookie before exchanging the authorization code. It then verifies the external identity through the provider adapter and always clears the transaction cookie on a completed or failed callback. Provider configuration errors return HTTP 503, invalid/expired callback transactions return HTTP 400, and upstream provider verification failures return HTTP 502 without exposing provider token details.

### SSO account linking and provisioning (Phase 5.5)

After provider verification, `SsoAccountService` resolves the external identity in one database transaction. An existing `(provider, provider_subject)` binding always selects its already-linked local user; it never selects a user by a mutable provider email. On each successful provider login, the binding's email metadata and verification flag are refreshed.

For a provider identity that has not been linked before, AegisAI requires a verified provider email. It links to a local user only when that email exactly matches an existing local account; otherwise, it just-in-time provisions an active local user and creates the external-identity binding. Identities with absent or unverified email are rejected, so an untrusted provider claim cannot take over or create a local account. Microsoft Entra email remains unverified by default and therefore requires an explicit future linking policy or a provider configuration that supplies a verifiable identifier.

Just-in-time SSO users receive a cryptographically random password hash that is never returned or known to anyone. This satisfies the existing non-null password field without creating a usable password-login credential. A successful Phase 5.5 callback confirms that the external identity is linked to a local account, but still does not issue AegisAI access or refresh tokens; Phase 5.6 will create those local sessions and preserve the database-backed RBAC behavior.

### SSO provider integration (Phase 5.3)

Provider-specific protocol work is isolated in `backend/app/integrations/sso/`. Future HTTP routes will call a provider adapter and receive one `ProviderIdentity` result: provider name, immutable provider subject, optional email, email-verification status, and optional display name. This prevents provider JSON shapes and endpoint URLs from leaking into API routes or the local-user service.

| Provider | Authentication protocol | Requested scopes | Identity source |
| --- | --- | --- | --- |
| Google | OpenID Connect authorization code + PKCE | `openid email profile` | Validated ID-token claims |
| GitHub | OAuth authorization code + PKCE | `read:user user:email` | `/user` plus primary verified `/user/emails` result |
| Microsoft Entra ID | OpenID Connect authorization code + PKCE | `openid email profile` | Validated ID-token claims |

For Google and Entra, the adapter loads OIDC discovery metadata, retrieves the matching JWKS signing key, and validates the ID token's RS256 signature, issuer, audience, expiry, and expected nonce before using its claims. Entra validates the token tenant and issuer explicitly, including when `organizations` deliberately permits more than one Entra tenant. Entra does not provide a universal `email_verified` claim, so its email metadata is not treated as verified for automatic account linking. GitHub's stable numeric account ID—not its login or email—is converted to the stored provider subject.

### External identities (Phase 5.2)

The `external_identities` table links one local `users` row to an identity at an external provider:

```text
users 1 ───< external_identities
                provider              google | github | microsoft
                provider_subject      provider's stable account identifier
                provider_email        optional profile metadata
                email_verified        whether the provider confirmed that email
```

`(provider, provider_subject)` is unique across the whole database. This is the authoritative account-binding rule: the same Google, GitHub, or Entra account cannot sign in as two different AegisAI users. Provider email is deliberately not unique because it can change and is not always available. A local user may link identities from more than one provider; deleting the local user cascades to its identity links.

### RBAC management API

The following typed `/rbac` endpoints are registered. Each requires a bearer access token, an active user, and the indicated database-backed permission.

| Method | Path | Required permission | Purpose |
| --- | --- | --- |
| `GET` | `/rbac/permissions` | `roles:read` | List the seeded permission catalogue |
| `GET` | `/rbac/roles` | `roles:read` | List roles |
| `POST` | `/rbac/roles` | `roles:manage` | Create a role |
| `DELETE` | `/rbac/roles/{role_id}` | `roles:manage` | Delete a non-system role |
| `GET` | `/rbac/roles/{role_id}/permissions` | `roles:read` | View role permissions |
| `POST`, `DELETE` | `/rbac/roles/{role_id}/permissions/{permission_id}` | `roles:manage` | Grant or revoke a role permission |
| `GET` | `/rbac/users/{user_id}/roles` | `users:read` | View user roles |
| `POST`, `DELETE` | `/rbac/users/{user_id}/roles/{role_id}` | `roles:assign` | Assign or remove a user role |

## Testing

Run the complete Phase 1–4 unit-test suite from `backend/`:

```bash
venv/bin/python -m unittest discover -s tests -v
```

The suite uses mocks for HTTP handlers and an isolated in-memory SQLite database
for service and repository behavior. It covers authentication, JWT handling,
refresh-token rotation, RBAC authorization, repositories, schemas, bootstrap
operations, dependencies, API handlers, and application startup.

The backend Dockerfile runs this same command during `docker compose build
backend`, then generates the complete Alembic upgrade SQL offline. A failing
unit test or invalid migration fails the image build. The build uses temporary
test settings only for those steps; runtime configuration still comes from
Compose and `backend/.env` is excluded from the image context.

Compose also runs the tests again, applies Alembic migrations to PostgreSQL,
and only then starts Uvicorn. Use this single command to force that complete
startup sequence even when Docker reuses cached image layers:

```bash
docker compose up --build --force-recreate
```

### RBAC verification

Run the dependency-free RBAC test suite from `backend/`:

```bash
venv/bin/python -m unittest discover -s tests -v
```

The tests use an isolated in-memory SQLite database. They verify that a user is
authorized only after both the role assignment and role-permission grant exist,
that revocation takes effect immediately, and that duplicate roles, system-role
deletion, inactive users, and missing permissions are rejected.

For the real PostgreSQL migration and seeded administrator role, run the
following in the Compose environment after registering an operator:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
docker compose exec backend python -m scripts.bootstrap_administrator admin@example.com
```

Run the bootstrap command again to confirm it makes no duplicate assignment.

## Run the entire project

### One-time setup

Install Docker with Docker Compose, then create your local configuration:

```bash
cp backend/.env.example backend/.env
```

Set a long, unique `JWT_SECRET_KEY` in `backend/.env` before using the
application outside local development. Keep the example `DATABASE_URL` hostname
as `postgres`: it is the database service name used inside Compose.

### Start everything

```bash
docker compose up --build --force-recreate
```

This single command:

1. Builds the backend image.
2. Runs all unit tests; it stops if any test fails.
3. Waits for PostgreSQL to be healthy.
4. Applies `alembic upgrade head` to PostgreSQL.
5. Starts the FastAPI backend, PostgreSQL, and Qdrant services.

When startup completes, open:

- API: `http://localhost:8000`
- Interactive API documentation: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`
- Qdrant: `http://localhost:6333`

Stop the stack with:

```bash
docker compose down
```

### Everyday Compose operations

```bash
# Follow backend startup or request logs
docker compose logs -f backend

# Re-run the full build, test, migration, and startup sequence
docker compose up --build --force-recreate

# Check running services
docker compose ps
```

### Local Python development

Docker is sufficient to run the entire project. Python 3.12+ is only required
when running the backend without Docker. Run local backend commands from
`backend/` so `app` is importable:

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

The current migration head includes users, refresh tokens, RBAC tables, the seeded permission catalogue, and the `administrator` system role. Review generated migrations for unintended constraints, indexes, or destructive changes before applying them.

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

### Bootstrap the first administrator

After applying migrations and registering the intended administrator account,
assign the seeded role explicitly:

```bash
docker compose exec backend python -m scripts.bootstrap_administrator admin@example.com
```

The command is idempotent: running it again for the same user makes no change.

## Roadmap

- [x] Phase 1 — Foundation and containerized services
- [x] Phase 2 — Database layer and Alembic
- [x] Phase 3 — Authentication, refresh-token lifecycle, and transaction boundaries
- [x] Phase 4 — RBAC: roles, permissions, assignments, and authorization dependencies
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
