# Administrative control-plane design

## Purpose

Phase 14 creates the secure administrative control plane behind AegisAI's
future dashboard. This phase delivers backend contracts and APIs; the browser
dashboard itself is deliberately deferred to Phase 15's Next.js application.

An administrator can use these APIs to inspect and operate local users, RBAC,
documents, processing jobs, and security audit history without bypassing the
existing authorization or lifecycle rules.

## 14.1 Contract and boundaries

### Authorization model

There is no new broad "dashboard administrator" bypass. Every administrative
operation keeps an explicit existing permission, so custom roles can receive
only the capability they need.

| Administrative area | Read permission | Mutation permission | Scope |
| --- | --- | --- | --- |
| Users | `users:read` | `users:manage` | List and inspect users; later activate/deactivate accounts. |
| Roles and permissions | `roles:read` | `roles:manage`, `roles:assign` | Existing role, permission, and assignment operations. |
| Documents and jobs | `documents:manage` | `documents:manage` | Global document/job inspection and lifecycle recovery, subject to each operation's rules. |
| Audit trail | `audit:read` | None | Immutable event search only. |

The system `administrator` role receives all of these permissions through the
existing migrations. A user without the relevant permission receives `403` at
the global RBAC boundary. Existing document-specific access checks still hide
unreadable documents as `404`; global administration will be explicit rather
than inferred from ownership.

### API conventions

- New administration routes will live below `/admin` and will be read-only
  unless a specific mutation endpoint is documented.
- List endpoints use `offset` and `limit`, with a maximum limit of 100, a
  deterministic order, and an authoritative `total`.
- Filters are allow-listed typed fields. Clients cannot send arbitrary SQL,
  ORM, Qdrant, JSON, or audit-metadata predicates.
- Responses contain local IDs and safe operational metadata only. They omit
  password hashes, access/refresh tokens, SSO tokens, original storage keys,
  document bytes, chunk text, embedding vectors, broker task identifiers, and
  raw provider or parser exceptions.
- State-changing actions validate the current resource state, use the service
  layer, and produce Phase 13 audit events in the same database transaction.
- Administrative reads do not create a new authorization source and do not
  allow audit-event modification or deletion.

### Operational boundaries

- User deletion is out of scope. Phase 14 will safely activate/deactivate
  existing accounts while retaining documents and audit history.
- Document deletion keeps the Phase 6 soft-delete and cleanup behavior;
  administrators do not receive a destructive database bypass.
- Job retries and cancellation retain the Phase 7/8/9 state-machine checks.
- Audit events remain append-only. Retention, exports, SIEM integrations, and
  tenant partitioning remain future work in Phases 16, 19, and 20.
- Phase 14 does not persist dashboard layout, preferences, analytics, or chat
  transcripts.

### Delivery checkpoints

- [x] 14.1 Administrative contract and boundaries
- [x] 14.2 Administrator authorization boundary
- [x] 14.3 User administration
- [x] 14.4 Role and permission administration refinement
- [x] 14.5 Document administration
- [x] 14.6 Processing-job operations
- [x] 14.7 Audit and operational overview
- [x] 14.8 Tests, Docker verification, and documentation

## Manual verification

After `docker compose up --build`, use an administrator access token to inspect
the control plane. The API is available in `/docs`.

```bash
curl http://localhost:8000/admin/overview \
  -H "Authorization: Bearer $OWNER_ACCESS_TOKEN"

curl "http://localhost:8000/admin/users?is_active=true&limit=25" \
  -H "Authorization: Bearer $OWNER_ACCESS_TOKEN"

curl http://localhost:8000/admin/roles \
  -H "Authorization: Bearer $OWNER_ACCESS_TOKEN"

curl "http://localhost:8000/admin/documents?status=failed" \
  -H "Authorization: Bearer $OWNER_ACCESS_TOKEN"

curl "http://localhost:8000/admin/processing-jobs?status=failed" \
  -H "Authorization: Bearer $OWNER_ACCESS_TOKEN"
```

Retry only a failed job and cancel only a running job; invalid transitions
return `409`. Test user deactivation only with a separate account because
self-deactivation is rejected and an inactive user cannot use protected APIs.
