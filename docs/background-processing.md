# Background processing design

## Purpose

Phase 7 adds reliable asynchronous job orchestration to AegisAI. HTTP requests
will create durable work records, while separate workers perform long-running
tasks outside the API process. The first worker task validates that an uploaded
source document remains accessible and matches its recorded integrity metadata.

This phase establishes the execution, retry, and failure-handling foundation
that Phase 8 will use for text extraction and chunking. It does not extract
text, create chunks, create embeddings, or query Qdrant.

## Completion criteria

Phase 7 is complete when all of the following are true:

- A successful document upload creates a durable queued processing job.
- A committed job is eventually published to Redis, including when Redis is
  temporarily unavailable at upload time.
- A separate Celery worker claims a job safely, verifies the stored source
  document, and records a terminal job outcome.
- Re-delivered queue messages do not run the same completed work twice.
- A transient failure is retried within a bounded policy; a terminal failure
  records a safe message without exposing an internal traceback through the
  API.
- Deleting a document cancels outstanding work, and a worker that receives a
  stale message exits without processing deleted content.
- Authorized users can inspect processing status and retry a failed job.
- Unit tests cover state transitions, outbox recovery, duplicate delivery,
  retry, cancellation, and Docker starts the API, Redis, scheduler, and worker.

## Scope boundaries

Phase 7 owns job orchestration, source-file integrity validation, and the
runtime services needed to execute those jobs. It does not claim that a
document is retrieval-ready: text extraction and chunk creation remain Phase
8 responsibilities. Malware scanning, document download, per-document ACLs,
audit events, tenancy, and retention remain out of scope.

## Runtime architecture

```text
POST /documents
       │
       ▼
DocumentService transaction
  ├── document metadata and stored source bytes
  ├── processing job (QUEUED)
  └── outbox event (PENDING)
       │
       ▼
PostgreSQL commits atomically
       │
       ▼
Celery Beat dispatcher ── publishes ──► Redis ──► Celery worker
                                                │
                                                ▼
                                    source integrity validation
                                    job state and safe failure result
```

The processing job and its outbox event are persisted in the same database
transaction as the document metadata. This is a transactional-outbox pattern:
if Redis cannot accept the message after the database commit, the event remains
in PostgreSQL and the dispatcher can publish it later. Uploads are therefore
not lost merely because the broker is briefly unavailable.

Redis is the development message broker and result backend. Docker Compose runs
three distinct application processes from the same backend image:

- FastAPI accepts HTTP requests.
- Celery Beat periodically dispatches unpublished outbox events.
- Celery workers execute published jobs and mount the same persistent document
  volume as FastAPI.

Redis has no public host port and holds no authoritative business data. Its
queue contents and short-lived task results may be lost during development;
the PostgreSQL outbox lets the dispatcher republish durable work afterward.

## State model

### Document status

`Document.status` remains the content-readiness state introduced in Phase 6:

| State | Meaning in Phase 7 |
| --- | --- |
| `PENDING` | Source bytes and metadata are durable and await a content-transformation stage. A completed Phase 7 integrity-check job leaves the document in this state. |
| `PROCESSING` | A content transformation is active. Phase 8 will use this during extraction and chunking. |
| `READY` | Text and chunks exist and are suitable for later embedding. This remains a Phase 8 outcome. |
| `FAILED` | An intake or content-processing stage could not complete. `processing_error` contains a safe, bounded explanation. |

Document status is deliberately not a queue indicator. A document can remain
`PENDING` after its Phase 7 preflight job has succeeded because it is still
waiting for the Phase 8 extraction stage.

### Processing-job status

Each processing job has an independent operational state:

```text
QUEUED ──► RUNNING ──► SUCCEEDED
   │          │
   │          └──────► FAILED ──► QUEUED  (authorized retry)
   │
   └─────────────────► CANCELLED
```

| Job state | Meaning | Allowed next states |
| --- | --- | --- |
| `QUEUED` | Durable work awaits broker publication or worker execution. | `RUNNING`, `CANCELLED` |
| `RUNNING` | One worker has claimed the job. | `SUCCEEDED`, `FAILED`, `CANCELLED` |
| `SUCCEEDED` | The current task completed once. Duplicate messages become no-ops. | None |
| `FAILED` | The task exhausted its retry policy or encountered a non-retryable failure. | `QUEUED` by an authorized retry |
| `CANCELLED` | The document was deleted or work was explicitly invalidated. | None |

The job records its attempt count, last broker task identifier, queued/started/
finished timestamps, and a bounded safe failure message. Worker tracebacks
belong in logs only; API responses expose neither exception classes nor storage
paths.

## Reliability and idempotency rules

- The database is the source of truth for jobs. Redis transports messages but
  does not determine whether work is complete.
- The worker claims a job by an atomic database state transition. Only the
  successful claimant may execute it.
- A repeated, late, or duplicate Celery delivery reads the terminal job state
  and exits successfully without repeating side effects.
- Publication is at-least-once. Execution is effectively once per successful
  claim because the database claim is idempotent.
- The dispatcher retries unpublished outbox events with bounded backoff. A
  Celery Beat sweep also recovers events left pending by an API-process crash.
- Retry creates another attempt on the same failed job only after an authorized
  user requests it. Automatic retries are limited to transient worker or
  infrastructure errors.
- A document deletion cancels non-terminal jobs before its source object is
  removed. A task that starts after deletion checks this state and performs no
  source-file work.

## First task: intake integrity validation

The first Celery task is intentionally narrow. It safely opens the stored
source object through the storage abstraction, streams it, and confirms the
recorded size and SHA-256 digest. This proves that the API and worker share the
same durable source content and exercises the failure/retry path without
pretending extraction has happened.

On success, the job becomes `SUCCEEDED` and the document remains `PENDING`.
On a non-recoverable integrity or source-storage failure, the job and document
become `FAILED`; the document retains only a safe bounded error message.

## Authorization policy

Phase 7 keeps the existing global document permissions:

| Action | Required permission |
| --- | --- |
| Inspect a document's processing jobs or job status | `documents:read` |
| Retry a failed job | `documents:write` |

The application is still single-tenant and has no resource-level document ACL.
Job visibility follows the existing global document-read policy; it does not
create a new ownership rule.

## Planned HTTP contract

The later API implementation will use document-scoped endpoints so job access
remains tied to the source document:

| Method | Path | Outcome |
| --- | --- | --- |
| `GET` | `/documents/{document_id}/processing-jobs` | List the source document's jobs and their safe status fields. |
| `GET` | `/documents/{document_id}/processing-jobs/{job_id}` | Return one job after confirming that it belongs to the document. |
| `POST` | `/documents/{document_id}/processing-jobs/{job_id}/retry` | Requeue one failed job when the caller has document-write permission. |

Exact response schemas, pagination limits, and error mappings will be added
with the API implementation in checkpoint 7.7.
