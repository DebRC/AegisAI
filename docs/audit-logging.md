# Audit logging design

## Purpose

Phase 13 adds an append-only security audit trail for AegisAI. An audit event
answers: who initiated a security-relevant action, what action occurred, what
resource it affected, when it occurred, and whether it succeeded.

It is not an application-debug log, analytics dataset, request transcript, or
replacement for future operational observability in Phase 16.

## 13.1 Audit policy and event taxonomy

### Design principles

- **Append-only:** application code creates events but never changes or deletes
  them. Retention and export controls are deferred to Phase 20.
- **Minimal and safe:** events contain stable identifiers and bounded,
  allow-listed metadata only. They never contain credentials, bearer tokens,
  raw document content, uploaded bytes, prompts, model output, embeddings,
  source chunks, or raw infrastructure/provider errors.
- **Durable writes:** security-relevant state changes and their audit event use
  one PostgreSQL transaction. If either cannot commit, neither succeeds.
- **Best-effort read telemetry:** document-read, retrieval, and chat audit
  events must not turn an otherwise successful read into a user-visible server
  error. Their recording failure is logged safely for operations and does not
  expose internal details to the caller.
- **No secondary authorization source:** audits describe decisions already made;
  they never grant access or replace RBAC/document-access policy checks.

### Event record contract

Every event will have an immutable ID and UTC occurrence time, an event type,
an outcome, and safe actor/target fields:

| Field | Meaning |
| --- | --- |
| `actor_user_id` | Local authenticated user when one is known; `null` for unauthenticated attempts. |
| `event_type` | A stable, namespaced action from the taxonomy below. |
| `outcome` | `succeeded`, `denied`, or `failed`; it never stores an exception trace. |
| `target_type`, `target_id` | The affected resource, such as `document` / `42` or `user` / `7`; both are nullable when no safe target exists. |
| `metadata` | Small allow-listed context, such as an SSO provider name, a prior/new access level, or a count of returned retrieval candidates. |

The model will not store email addresses as targets. A local numeric user ID is
enough to link an event to the authoritative user record while minimizing PII
duplication. Client IP, user agent, and request correlation data are deferred
until Phase 16 establishes a structured observability contract.

### Initial taxonomy

| Area | Event types |
| --- | --- |
| Authentication | `auth.login.succeeded`, `auth.login.failed`, `auth.sso.succeeded`, `auth.sso.failed`, `auth.refresh.succeeded`, `auth.refresh.failed`, `auth.logout.succeeded` |
| RBAC administration | `rbac.role.created`, `rbac.role.deleted`, `rbac.role_permission.granted`, `rbac.role_permission.revoked`, `rbac.user_role.assigned`, `rbac.user_role.removed` |
| Document lifecycle | `document.uploaded`, `document.renamed`, `document.deleted`, `document.reprocess_queued` |
| Direct sharing | `document.access_grant.created`, `document.access_grant.updated`, `document.access_grant.revoked` |
| Protected reads | `document.read`, `retrieval.search`, `chat.request` |

Event names are intentionally action-oriented and stable. A future migration
rather than an ad-hoc string change is required to rename a published event
type.

### Outcome and failure rules

`denied` means policy rejected the action before its protected state changed.
`failed` means an attempted operation could not complete safely; its metadata
contains a bounded category such as `invalid_credentials`, `provider_rejected`,
or `persistence_failed`, never an unfiltered exception message.

Read events are emitted only after the caller is authorized. We do not write
events for arbitrary nonexistent or inaccessible document IDs because doing so
would create a sensitive enumeration record. Retrieval and chat events record
only aggregate request/outcome fields, not query or answer text.

### Scope boundaries

Phase 13 does not add a UI, event editing/deletion, long-term retention,
external SIEM export, tenant-scoped audit partitioning, client IP capture, or
full distributed tracing. Those belong to Phases 14, 16, 19, and 20.

## Delivery checkpoints

- [x] 13.1 Audit policy and event taxonomy
- [x] 13.2 Audit-event model and Alembic migration
- [x] 13.3 Repository and audit service
- [x] 13.4 Authentication and RBAC events
- [ ] 13.5 Document and sharing events
- [ ] 13.6 Retrieval and RAG access events
- [ ] 13.7 Protected audit-query API
- [ ] 13.8 Tests, Docker verification, and documentation
