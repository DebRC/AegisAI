# Frontend design

## Purpose

Phase 15 adds AegisAI's browser application. It is a Next.js and TypeScript
client for the existing FastAPI API; it does not duplicate business rules,
document access policy, or RBAC in the browser.

The frontend is a product interface for authentication, document work,
retrieval, grounded chat, and administration. FastAPI remains the sole
authority for identity, authorization, document access, job lifecycles, audit
events, and generated answers.

## 15.1 Frontend contract and boundaries

### Runtime boundary

```text
Browser
  |
  v
Next.js application :3000
  |                         no provider, database, or OpenAI secrets
  v
FastAPI API :8000 ----------> PostgreSQL, Redis/Celery, Qdrant, providers
```

The Next.js server is the browser-facing backend-for-frontend boundary. Browser
code calls only same-origin Next.js routes. Those routes forward requests to
FastAPI with the current AegisAI access token. The browser never receives the
refresh token and never calls PostgreSQL, Redis, Qdrant, OpenAI, or SSO
providers directly.

The initial local Compose deployment uses `http://localhost:3000` for Next.js
and `http://localhost:8000` for FastAPI. The API URL is server-only
configuration, not a `NEXT_PUBLIC_*` value.

### Session policy

1. A successful local login produces AegisAI's existing access and refresh
   tokens at FastAPI.
2. The Next.js server stores them in HttpOnly, `SameSite=Lax` cookies. Cookie
   `Secure` is enabled outside local HTTP development.
3. A proxy route sends the short-lived access token to FastAPI as a Bearer
   token. On an authentication failure it may make exactly one server-side
   refresh-token exchange, rotate both cookies, and retry the original request.
4. Logout calls FastAPI's existing refresh-token revocation endpoint, then
   clears both browser cookies even if the backend session has already expired.
5. No token is stored in `localStorage`, `sessionStorage`, client-side state,
   URL query parameters, logs, or error messages.

The current FastAPI SSO callback returns a token response rather than redirecting
to a frontend route. Phase 15 will add a narrowly scoped callback handoff so
the Next.js server can establish the same HttpOnly session after a verified SSO
login. It will preserve the backend's signed state, PKCE, nonce, verified-email,
account-linking, and inactive-user protections.

### Route map

| Route | Audience | Primary FastAPI contract | Notes |
| --- | --- | --- | --- |
| `/login` | Unauthenticated users | `POST /auth/login`, `GET /auth/sso/{provider}` | Form login, SSO entry points, safe error feedback. |
| `/register` | Unauthenticated users | `POST /auth/register` | Account creation; no automatic elevated role. |
| `/documents` | `documents:read` | `GET /documents` | Paginated readable-document workspace. |
| `/documents/upload` | `documents:write` | `POST /documents` | Multipart upload with the backend's type and size validation. |
| `/documents/[id]` | Direct document read access | Document, extraction, chunks, job, and indexing endpoints | Metadata, lifecycle, source locations, and permitted actions. |
| `/search` | `documents:read` | `POST /retrieval/search` | Semantic results with controlled metadata filters only. |
| `/chat` | `documents:read` | `POST /chat/stream` | Incremental SSE answer, terminal citations, and safe errors. |
| `/admin` | Relevant admin permissions | `GET /admin/overview` | Navigation is capability-aware; FastAPI remains authoritative. |
| `/admin/users`, `/admin/documents`, `/admin/jobs`, `/admin/audit` | Relevant admin permissions | Existing `/admin/*` and `/audit-events` endpoints | Each screen requests only its necessary backend capability. |

An unknown or unauthorized document must remain indistinguishable in the UI:
the document route renders a generic unavailable state for FastAPI `404` rather
than attempting to infer whether another user owns it.

### UI state contract

Every data screen implements these explicit states:

| State | User-visible behavior | Rules |
| --- | --- | --- |
| Loading | Skeleton or concise progress indicator | Do not show stale data as current without identifying it. |
| Empty | Explain that no permitted resources match | Offer only actions the user is allowed to take. |
| Validation error | Show field-level safe backend validation message | Preserve non-secret user input. |
| Unauthorized | Redirect unauthenticated users to login; show a capability-safe denied state for `403` | Never claim an administrator role locally. |
| Unavailable | Show retry guidance for `5xx`, retrieval, chat, or processing outages | Do not expose stack traces, provider errors, token data, or raw SSE frames. |
| Mutation success | Refresh the authoritative server state | Do not optimistically invent document/job lifecycle transitions. |

Document processing status is a backend-owned lifecycle. The frontend can poll
the existing job and indexing-status endpoints while a document is pending or
running; it must stop after a terminal state and respect cancellation/deletion.

### API and data rules

- TypeScript request and response types are derived manually from the published
  FastAPI/OpenAPI contract and covered by focused tests; frontend types do not
  create a competing contract.
- The proxy allow-lists known API paths and methods. It does not accept arbitrary
  target URLs, request headers, or external redirects from the browser.
- Uploads stream as multipart form data without reading whole documents into
  browser JavaScript memory. The FastAPI upload limit remains authoritative.
- Chat consumes only the documented SSE events: `answer_delta`, `citations`,
  `done`, and `error`. Citations are rendered from the terminal verified event,
  not guessed from generated answer text.
- The browser may hide unavailable navigation for usability, but every request
  handles FastAPI `401`, `403`, and `404`; hiding a link is never authorization.
- The frontend does not persist chat transcripts in Phase 15. The current
  per-turn client history remains bounded by FastAPI's Phase 11 validation.

### Out of scope

Phase 15 does not add a new identity provider, browser-held API keys, direct
provider calls, a database schema for UI preferences, persisted chat history,
tenant selection, audit-event editing, or alternate authorization semantics.
Observability and production browser deployment hardening are Phase 16 and
later work.

### Delivery checkpoints

- [x] 15.1 Frontend contract and screen map
- [x] 15.2 Next.js runtime and Docker integration
- [x] 15.3 Typed API client and server-managed session
- [x] 15.4 Authentication and SSO browser flows
- [x] 15.5 Document workspace
- [x] 15.6 Search and grounded chat
- [x] 15.7 Administration workspace
- [x] 15.8 Tests, Compose verification, and documentation

## Manual verification for 15.1

This checkpoint introduces no runnable frontend. Verify the contract before
implementation:

1. Confirm every planned screen maps to an existing FastAPI route in `/docs`.
2. Confirm the user-facing permissions in the route map match the backend's
   RBAC requirements.
3. Confirm the frontend will use server-only `API_BASE_URL` configuration and
   HttpOnly cookies, with no `NEXT_PUBLIC_*` token or provider-secret setting.
4. Keep `docker compose up --build --force-recreate` as the canonical backend
   verification command until the frontend service is added in 15.2.

## 15.2 Next.js runtime and Docker integration

The `frontend/` application is a strict TypeScript Next.js App Router project.
Its initial landing page is intentionally static: it proves the browser runtime
without prematurely implementing client-side authentication or a direct API
call. The `/login` link is the reserved entry point for 15.4.

The frontend Dockerfile installs reproducible dependencies from
`package-lock.json`, type-checks and builds the application, then copies only
the Next.js standalone output into its runtime image. Compose publishes the
frontend at port `3000` and supplies `API_BASE_URL=http://backend:8000` only to
the frontend container. That value is server-only and is not exposed to browser
JavaScript.

### Manual verification for 15.2

From the repository root, run:

```bash
docker compose up --build --force-recreate
```

Then open `http://localhost:3000`. The AegisAI landing page should appear and
its **Sign in** link should currently lead to an expected `404`; the login page
is introduced in 15.4. Confirm `http://localhost:8000/health` remains healthy.

## 15.3 Typed API client and server-managed session

`lib/server/api-client.ts` is the server-only FastAPI client. Its initial
allow-list contains only the session contracts needed at this stage:
`GET /auth/me` and `POST /auth/refresh`. Each call disables caching, supplies
the Bearer token only from server code, applies a bounded timeout, and maps
unexpected backend response details to a safe error.

`lib/server/session.ts` is the server-only token boundary. It stores AegisAI's
access and refresh tokens in separate HttpOnly, `SameSite=Lax` cookies. They
are never returned from `GET /api/session`. When an access token receives a
`401`, the session resolver makes one refresh request, rotates both cookies,
and retries `GET /auth/me`. A rejected refresh clears both cookies and returns
an anonymous session; an availability failure remains a safe `503` rather than
silently logging a user out.

`SESSION_COOKIE_SECURE` is explicitly `false` only in local HTTP Compose. It
must be `true` behind HTTPS. `SESSION_REFRESH_COOKIE_MAX_AGE_SECONDS` controls
only browser persistence and must not outlive FastAPI's refresh-token policy;
FastAPI continues to validate the actual refresh token.

### Manual verification for 15.3

Run the frontend checks:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Then start the stack and inspect the safe anonymous session response:

```bash
docker compose up --build --force-recreate
curl http://localhost:3000/api/session
```

Expected response before 15.4 creates a browser session:

```json
{"authenticated":false}
```

## 15.4 Authentication and SSO browser flows

`/login` and `/register` submit only to same-origin Next.js route handlers.
Those handlers call FastAPI, store a successful token pair in HttpOnly cookies,
and return only safe user data. `/api/auth/logout` asks FastAPI to revoke the
refresh token and clears cookies in all cases. Session refresh remains owned by
the 15.3 resolver.

SSO buttons navigate through an allow-listed Next.js route to FastAPI's
existing provider flow. Set `SSO_FRONTEND_REDIRECT_URL=http://localhost:3000`
in `backend/.env` for browser SSO. After backend verification, FastAPI sets the
same HttpOnly session cookies and redirects to `/login?provider=...`; tokens
never appear in the redirect URL or page body. Leave that setting blank only
for the existing API-only SSO callback contract.

### Manual verification for 15.4

```bash
docker compose up --build --force-recreate
```

1. Open `http://localhost:3000/register`, create an account, then sign in at
   `/login`.
2. Run `curl http://localhost:3000/api/session`; it should report
   `authenticated: true` with user data, but no tokens.
3. Send `POST /api/auth/logout` from the browser or DevTools, then repeat the
   session call; it should return `authenticated: false`.
4. For a configured provider, set `SSO_FRONTEND_REDIRECT_URL` as above and add
   FastAPI's existing callback URL (for example,
   `http://localhost:8000/auth/sso/google/callback`) to the provider
   registration. Complete sign-in and verify the browser returns to `/login`
   without tokens in its URL.

## 15.5 Document workspace

The workspace uses same-origin Next.js routes for upload, list, detail,
reprocess, rename, deletion, and direct-access grants. FastAPI remains
authoritative for every permission and lifecycle transition. A missing or
denied document renders the same unavailable state.

## 15.6 Search and grounded chat

`/search` calls the Phase 10 retrieval API through an authenticated server
route and labels scores as similarity, not certainty. `/chat` forwards the
Phase 11 SSE stream without buffering it. The browser renders answer text only
from `answer_delta`, citations only from the verified terminal `citations`
event, and safe text from `error`; it never calls OpenAI directly.

### Manual verification for 15.5–15.6

After Docker Desktop is running:

```bash
docker compose up --build --force-recreate
```

1. Sign in at `http://localhost:3000/login`, upload a supported fixture at
   `/documents`, and wait for its processing/indexing status to become ready.
2. Rename and reprocess it from `/documents/{id}`. Confirm FastAPI—not the UI—
   rejects an invalid lifecycle transition or unauthorized request.
3. Search from `/search`; a ready matching document should return chunk text
   and its similarity score. Stop Qdrant or remove embedding credits to verify
   the safe unavailable state.
4. Ask a matching question at `/chat`. The answer should stream, followed by
   citations. Ask an unrelated question to verify the backend's grounded,
   insufficient-context behavior. No OpenAI key or JWT should appear in browser
   storage, page source, or URLs.

## 15.7 Administration workspace

The frontend exposes `/admin`, `/admin/users`, `/admin/rbac`,
`/admin/documents`, and `/admin/operations`. Each calls a same-origin route
handler that forwards only the current server-held access token. Navigation is
for usability only: FastAPI still evaluates the precise existing permission for
every overview, user, RBAC, document, job, and audit request.

### Manual verification for 15.7

Sign in as an administrator and open each administration URL above. Confirm
the overview counts, user status change, role/permission summaries, global
document metadata, job states, and audit-event records. Sign in as a user
without the corresponding permissions and confirm each API call is denied or
reports a safe unavailable state without leaking data.

## 15.8 Final verification

Run the browser-independent quality gate from `frontend/`:

```bash
npm test
npm run typecheck
npm run build
```

Then, with Docker Desktop running, use the repository-root command below for
the final end-to-end verification:

```bash
docker compose up --build --force-recreate
```

Confirm the API health endpoint, sign in through the frontend, upload and
process a document, search it, receive a cited chat answer, and visit each
administration page as an administrator and a non-administrator. The phase is
complete only after that Compose/browser workflow succeeds.

Compose verification completed successfully on the local stack: the backend
ran 198 tests, applied migrations, served a healthy `/health` response, and
the frontend served its landing page at port 3000.
