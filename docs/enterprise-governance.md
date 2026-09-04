# Enterprise governance

Phase 20 adds the final organization controls without introducing paid hosting
or a separate control plane: tenant-scoped machine access, request limiting,
and source-document retention.

## API keys

An API key is a tenant machine credential, not a replacement for human login.
It has a name, a unique non-secret prefix, explicitly requested permission
scopes, creator, expiry/revocation state, and last-used timestamp. The complete
high-entropy key is returned once on creation; the database contains only an
HMAC-SHA-256 hash keyed by the deployment JWT secret. It cannot be recovered.

```text
human tenant administrator
        │ creates only scopes they already hold
        ▼
hashed tenant API key ── X-API-Key ──► tenant context ──► scope check ──► route
```

`api_keys:manage` is required to list, create, and revoke keys. The governance
endpoints reject API-key authentication entirely, so a key cannot use a broad
scope to mint another key or change policy. Normal API-key requests must have a
scope matching the existing route permission, for example `documents:read`.

| Method | Route | Outcome |
| --- | --- | --- |
| `GET` | `/governance/api-keys` | Lists metadata only; never returns plaintext key material. |
| `POST` | `/governance/api-keys` | Creates a scoped credential and returns `api_key` exactly once. |
| `DELETE` | `/governance/api-keys/{id}` | Immediately revokes a tenant-owned credential. |

## Rate limiting

Each protected request is counted in Redis by `(tenant_id, principal)`, where
the principal is the human user or API-key prefix. The fixed one-minute window
uses Redis `INCR` and TTL, so it works across backend replicas. A limit breach
returns HTTP `429` with `Retry-After`; inability to reach the configured rate
limiter returns HTTP `503` rather than failing open.

Set `RATE_LIMIT_ENABLED=false` only for an isolated local diagnostic. Production
use should keep it enabled and point `RATE_LIMIT_REDIS_URL` at an available,
access-controlled Redis logical database separate from Celery queues.

## Retention

`document_retention_days` is optional per tenant. `null` disables automatic
expiry. A positive value deletes documents older than that duration through the
existing lifecycle: active work is cancelled, vector cleanup is queued,
extractions are removed, metadata becomes inaccessible, and local source-file
removal is attempted. The operation is idempotent; the periodic Celery Beat
sweep and an authorized manual sweep use the same service.

| Method | Route | Permission |
| --- | --- | --- |
| `GET`, `PUT` | `/governance/retention` | `retention:manage` |
| `POST` | `/governance/retention/purge` | `retention:manage` |

The retention scheduler runs at `RETENTION_SWEEP_INTERVAL_SECONDS` (daily by
default). An external object store should eventually provide equivalent durable
deletion confirmation before using this local-storage implementation for a
regulated production retention promise.

## Audit and browser controls

Creating/revoking an API key, changing retention, and retention purges create
tenant-tagged, data-minimized audit events. The browser workspace provides
`/admin/governance` for policy changes and once-only API-key display; it keeps
the JWT in HTTP-only server-managed cookies and never writes it to browser
storage.

## Manual verification

1. Sign in as a tenant administrator, open `/admin/governance`, create a key
   with only `documents:read`, and copy it immediately.
2. Call `GET /documents` with `X-API-Key: <copied value>`; it should work only
   for that tenant. A document upload should receive `403` because the key has
   no write scope.
3. Revoke the key and repeat the read: it should return `401`.
4. Set a low retention period for a disposable document, create an old fixture
   in development or wait for the interval, then call `POST /governance/retention/purge`.
   Confirm it disappears from document listing and its job/vector cleanup is
   recorded.
5. Lower `RATE_LIMIT_REQUESTS_PER_MINUTE` locally, restart Compose, and make
   more protected requests than the limit. The final request must return `429`.
   Stop Redis only in a disposable environment and confirm a protected route
   returns `503`, not an unrestricted success.
