# Observability design

## Purpose

Phase 16 makes AegisAI diagnosable in local and future production deployments
without turning documents, prompts, tokens, credentials, or personal data into
operational telemetry. Observability reports system behavior; it is not a
second audit trail, authorization system, or analytics product.

## 16.1 Observability contract and privacy policy

### Signals

| Signal | Purpose | Audience | Exposure |
| --- | --- | --- | --- |
| Structured application logs | Diagnose one request, task, or failure | Operators | Container logs; never public API responses. |
| Health endpoints | Determine liveness and dependency readiness | Load balancers and operators | Unauthenticated, safe status only. |
| Prometheus metrics | Aggregate HTTP rates, latency, and status outcomes | Monitoring system | Separate internal metrics endpoint. |
| Audit events | Security and administrative history | Authorized administrators | Existing Phase 13 API only. |

Audit events remain the immutable source for security-relevant actions.
Structured logs and metrics must not replace or duplicate their privacy policy.

### Required structured log fields

Backend HTTP and worker logs use JSON records with these safe fields where
available: timestamp, severity, service, event name, request ID, HTTP method,
route template, status code, duration, task name, and a bounded failure
category. Any later correlation field must be explicitly allow-listed. Email
addresses, names, document titles, and filenames are not allowed.

### Prohibited data

Never place any of the following in logs, metric labels, health payloads,
traces, or exception messages returned to clients:

- Access JWTs, refresh tokens, SSO state, PKCE verifier, cookies, passwords,
  OAuth client secrets, API keys, database URLs, or authorization headers.
- Document bytes, extracted text, chunks, prompts, chat history, generated
  answer text, citations, file names, storage keys, checksums, or embeddings.
- Raw provider responses, stack traces in HTTP responses, database statements,
  broker payloads, or unbounded exception text.
- Email addresses, full names, IP addresses, or free-form request bodies.

Metric labels must remain low-cardinality. Route templates, method, status
class, service, task type, provider name, and bounded outcome category are
allowed; IDs, query text, document metadata, and exception strings are not.

### Health semantics

`/health` remains the inexpensive liveness endpoint: the process can answer a
request. Phase 16 will add a distinct readiness endpoint that checks required
dependencies with bounded timeouts. A failed optional OpenAI call must not make
the core API unready; configured required local dependencies do.

### Delivery checkpoints

- [x] 16.1 Observability contract and privacy policy
- [x] 16.2 Structured request logging and correlation IDs
- [x] 16.3 Safe exception telemetry
- [x] 16.4 Liveness, readiness, and dependency health
- [x] 16.5 Prometheus metrics
- [x] 16.6 Worker observability
- [x] 16.7 Operational guidance
- [x] 16.8 Tests, Compose verification, and documentation

## Manual verification for 16.1

Review this contract before implementation. In particular, confirm that a
request ID is the only browser-visible diagnostic correlation value and that
no planned metric or log field contains a token, document content, chat text,
email, filename, or unbounded exception message.

## Runtime operations

- `GET /health` is liveness; `GET /health/ready` verifies PostgreSQL, Redis,
  and Qdrant with a short bounded timeout.
- `GET /health/metrics` emits Prometheus text metrics. Keep it internal in a
  deployed environment; local Compose exposes it only through the API port.
- Correlate an operator report with `X-Request-ID`; never request tokens or
  document content to diagnose it.
- Alert on sustained readiness failures, elevated `5xx` rate, worker task
  failures, or processing queues that stop progressing. HTTP conditions come
  from Prometheus; worker conditions come from structured task-name logs until
  a dedicated worker exporter is introduced. Investigate using safe request ID
  and task-name logs first.

## Manual verification

Start the platform with the root `docker compose up --build --force-recreate`
command. Its backend build and startup gates run the complete unit suite and
apply the database migration head before Uvicorn starts.

```bash
# Liveness returns 200 and echoes a safe, caller-supplied correlation ID.
curl -i http://localhost:8000/health -H 'X-Request-ID: local-check-001'

# Readiness returns all required local dependencies without credentials or
# connection details.
curl http://localhost:8000/health/ready

# The API process exposes only low-cardinality Prometheus measurements.
curl http://localhost:8000/health/metrics | rg '^aegis_'

# Follow JSON request records or safe worker completion/failure records.
docker compose logs -f backend
docker compose logs -f celery-worker
```

Expected readiness output is `status: ready` with `database`, `redis`, and
`qdrant` all `connected`. If an operator deliberately stops one of those
dependencies, readiness must instead return HTTP `503`, list only the affected
dependency as `unavailable`, and never reveal credentials or exception text.
