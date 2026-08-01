# Document ingestion design

## Purpose

Phase 6 creates AegisAI's secure document boundary. At the end of this phase,
an authorized user can upload, list, inspect, rename, and delete document
records. PostgreSQL stores document metadata and a replaceable storage adapter
stores the original bytes.

This is the contract for the Phase 6 model, migration, storage, services, API,
and tests. It intentionally separates durable ingestion from later processing
and retrieval work.

## Completion criteria

Phase 6 is complete when all of the following are true:

- An active user with `documents:write` can upload an allowed file.
- A successful upload has one durable metadata record and one stored object.
- An active user with `documents:read` can list and inspect non-deleted
  document metadata.
- Authorized users can rename and delete documents without supplying a storage
  path.
- Failed uploads leave no visible metadata and attempt to remove any temporary
  or final object created during the operation.
- Unit tests cover validation, cleanup, service transactions, and RBAC; Docker
  startup continues to run tests and migrations.

## Scope boundaries

Phase 6 stores original files and metadata only. It does not run a worker,
extract text, create chunks, generate embeddings, write vectors to Qdrant,
retrieve or download content, add per-document ACLs, introduce tenancy, audit
events, malware scanning, retention, or restore workflows.

Those capabilities are deliberately sequenced later: Phase 7 adds durable
background-job orchestration and source-integrity validation; Phase 8 owns text
extraction and chunking; Phase 9 adds embeddings and Qdrant; Phase 10 adds
retrieval; Phase 12 adds permission-aware retrieval; and enterprise phases add
audit, tenancy, and retention controls.

## Architecture

```text
POST /documents (multipart file)
              │
              ▼
  require_permission(documents:write)
              │
              ▼
       DocumentService
       ├── validate metadata and streamed content
       ├── calculate SHA-256 and size
       ├── persist through DocumentStorage
       └── persist metadata through DocumentRepository
                    │                         │
                    ▼                         ▼
          local document volume          PostgreSQL documents table
```

`DocumentService` coordinates storage and database work. A filesystem cannot
participate in a PostgreSQL transaction, so the service uses compensating
cleanup: it removes a temporary or final object if a later validation or
database operation fails. A document becomes visible only after storage and
metadata persistence succeed.

## Lifecycle

The ingestion status describes content-processing readiness, not authorization.
Deletion is separate so a deleted document is never listed or picked up by a
future worker.

```text
upload accepted
      │
      ▼
PENDING ──► PROCESSING ──► READY
   │             │            │
   │             └────────► FAILED
   │
   └──────────────────────► deleted_at is set; stored object is removed
```

| State | Meaning | Introduced in |
| --- | --- | --- |
| `PENDING` | Original bytes and metadata are durable and await a content-transformation stage. A successful Phase 7 integrity-check job leaves the document pending for Phase 8 extraction. | Phase 6 |
| `PROCESSING` | A content transformation is actively running. Phase 8 uses this state for extraction and chunking. | Phase 7–8 |
| `READY` | Text/chunks are ready for later embedding and retrieval work. | Phase 8 |
| `FAILED` | Processing could not complete; a reason is retained for an authorized operator. | Phase 7–8 |

Every Phase 6 upload starts as `PENDING`; Phase 6 makes no automatic state
transition. `deleted_at` is a soft-delete marker for metadata, while deletion
also removes the stored object. Restore and retention are not promised yet.

Phase 7 introduces a separate processing-job lifecycle for queueing, retries,
and worker execution. Job state is operational; `Document.status` remains a
content-readiness state. The implemented job/outbox contract is in the
[background processing design](background-processing.md); the Phase 8
[text extraction and chunking design](text-extraction-and-chunking.md) defines
how a validated source later becomes `READY`.

## Metadata contract

The `documents` table inherits `id`, `created_at`, and `updated_at` from the
existing declarative base.

| Field | Purpose and rule |
| --- | --- |
| `uploader_user_id` | Required foreign key to the local uploader. It records attribution, not a document-level permission grant. |
| `title` | Validated display name derived from the original filename. It is the only mutable metadata in Phase 6. |
| `original_filename` | Untrusted client-supplied display metadata; never a storage path. |
| `content_type` | Allowed MIME type recorded at ingestion; it is not the only content-safety signal. |
| `size_bytes` | Actual streamed byte count, subject to the configured limit. |
| `sha256` | Digest computed while streaming. It provides integrity information but no Phase 6 deduplication. |
| `storage_key` | Server-generated opaque object key; a client never supplies it. |
| `status` | Processing lifecycle state; initial value is `PENDING`. |
| `processing_error` | Nullable failure reason reserved for later workers. |
| `deleted_at` | Nullable soft-delete timestamp. Normal reads and lists exclude deleted records. |

Equal content may be uploaded more than once. Deduplication is intentionally
deferred because equal bytes can have distinct provenance, future access rules,
or retention requirements.

## Storage contract

Phase 6 uses a `DocumentStorage` interface so application services depend on
storage behavior rather than a filesystem implementation. Its first adapter is
local persistent storage for Docker development.

| Concern | Contract |
| --- | --- |
| Local location | A dedicated Docker volume mounted at a configured document-storage directory, separate from application source and PostgreSQL data. |
| Key generation | The server creates an opaque UUID-based key. Neither an original filename nor a request path influences the on-disk path. |
| Write pattern | Stream to a temporary object, verify size and digest, then atomically promote it to the final key when possible. |
| Failure cleanup | If storage, validation, or database persistence fails, remove temporary and final objects best-effort before returning an error. |
| Delete pattern | On soft-delete, remove the final object best-effort and prevent future reads from returning the metadata. |
| Future replacement | An S3-compatible or managed object-storage adapter can implement the same interface without changing services or HTTP routes. |

The local adapter is a development choice, not a production storage strategy.

## Upload acceptance policy

The first release accepts the following formats, subject to the configured
`DOCUMENT_MAX_UPLOAD_BYTES` limit of 25 MiB by default. The upload endpoint
enforces that streamed byte limit.

| Format | Extensions | MIME type |
| --- | --- | --- |
| PDF | `.pdf` | `application/pdf` |
| Word document | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Plain text | `.txt` | `text/plain` |
| Markdown | `.md`, `.markdown` | `text/markdown` or `text/plain` |

The service will calculate size and SHA-256 incrementally while streaming. It
will validate the requested filename extension and declared MIME type against
this allowlist, reject empty files, and never trust a filename as a filesystem
path. Deeper file-signature checks and malware scanning are separate security
capabilities; Phase 6 does not claim that allowlist validation makes uploaded
content safe to execute or open.

## Authorization and ownership policy

The existing RBAC permissions apply consistently:

| Action | Required permission | Phase 6 behavior |
| --- | --- | --- |
| Upload, rename, or delete a document | `documents:write` | Allowed for an active user with the permission. |
| List or inspect document metadata | `documents:read` | Allowed for an active user with the permission. |

The current application is single-tenant and has no per-document ACL model.
These permissions are global within the deployment: a user with
`documents:write` may manage any non-deleted document, not only documents they
uploaded. `uploader_user_id` records provenance and prepares for later audit,
tenancy, and resource-level policies; it does not alter Phase 6 authorization.

Authorization runs at the API boundary before `DocumentService` is called.
Only `POST /documents` uses the authenticated user to set
`uploader_user_id`; a client cannot submit a different uploader ID. The
service intentionally does not make ownership-based allow/deny decisions,
because that would silently introduce a per-document ACL policy before tenant
and resource-policy rules have been designed.

## HTTP API contract

The document router uses `/documents` and requires an AegisAI access JWT plus
the documented permission.

| Method | Path | Permission | Intended response |
| --- | --- | --- | --- |
| `POST` | `/documents` | `documents:write` | Accept multipart field `file`; return `201 Created` and document metadata. |
| `GET` | `/documents?offset=0&limit=25` | `documents:read` | Return a bounded page of non-deleted metadata, including `items`, `offset`, `limit`, and `total`. The maximum limit is 100. |
| `GET` | `/documents/{document_id}` | `documents:read` | Return one non-deleted document's metadata. |
| `PATCH` | `/documents/{document_id}` | `documents:write` | Rename the document title only. |
| `DELETE` | `/documents/{document_id}` | `documents:write` | Soft-delete metadata, remove the stored object, and return `204 No Content`. |

Phase 6 intentionally has no raw-document download endpoint. Future access to
content must be designed together with retrieval permissions and audit rules.

Deletion commits the `deleted_at` marker before attempting filesystem cleanup.
If cleanup fails, the metadata remains deleted and the original is an
unreachable orphan pending future storage reconciliation; Phase 6 does not
restore active metadata after its stored bytes may already have been removed.

| Situation | Response |
| --- | --- |
| Missing, invalid, expired, or refresh token | `401 Unauthorized` |
| Active user lacks document permission | `403 Forbidden` |
| Invalid title, missing file, empty file, unsupported type, or size limit exceeded | `422 Unprocessable Content` |
| Document does not exist or is deleted | `404 Not Found` |
| Storage cannot safely complete the operation | `503 Service Unavailable` without storage internals in the response |

## Verification coverage

Phase 6 verification covers:

- permitted and rejected upload types;
- streamed size limits, empty uploads, and generated storage keys;
- SHA-256 persistence and no implicit deduplication;
- cleanup after storage, validation, flush, and commit failures;
- list pagination and exclusion of deleted records;
- rename and delete behavior;
- `documents:read` and `documents:write` authorization denial and success;
- migration upgrade and downgrade review; and
- Docker build/startup execution of the complete suite.

## Manual authenticated lifecycle check

After starting the stack with `docker compose up --build --force-recreate`:

1. Obtain an access token for an active user with `documents:read` and
   `documents:write` (the seeded administrator role has both permissions).
2. Open `http://localhost:8000/docs`, select **Authorize**, choose **AegisAI
   access token**, and paste the raw access token.
3. Call `POST /documents` with a small PDF, DOCX, TXT, or Markdown file.
4. Use `GET /documents` and `GET /documents/{document_id}` to inspect the
   metadata, then `PATCH` its title and `DELETE` it.
5. Confirm a final `GET /documents/{document_id}` returns `404` and the list
   omits the deleted document.

## Implementation sequence

1. [x] Define the document domain and lifecycle contract: allowed types, size
   limits, statuses, ownership, and the definition of an uploaded document
   (6.1).
2. [x] Add a replaceable storage abstraction and the local Docker volume for
   original bytes outside PostgreSQL (6.2).
3. [x] Add the document database model and Alembic migration for durable
   metadata, ownership, integrity data, lifecycle state, and timestamps (6.3).
4. [x] Add repository and service layers so database and storage operations
   remain transactional and testable outside HTTP routes (6.4).
5. [x] Add the secure multipart upload endpoint with generated keys, streamed
   limits, allowed content types, checksums, and safe filenames (6.5).
6. [x] Add document management APIs to list, inspect, rename, and safely
   delete documents (6.6).
7. [x] Verify RBAC and ownership rules: enforce `documents:read` and
   `documents:write` consistently, and preserve `uploader_user_id` as
   provenance for future tenant and document-level policies (6.7).
8. [x] Cover validation, storage cleanup, authorization, migrations, and the
   complete Compose startup path; consolidate user-facing documentation and
   provide the authenticated upload lifecycle check (6.8).
