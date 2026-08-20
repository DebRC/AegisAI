# Permission-aware retrieval design

## Purpose

Phase 12 changes AegisAI from deployment-wide document visibility to
document-specific access control. A user must first hold the existing global
RBAC permission and then be authorized for the particular document. The same
resource decision applies to document APIs, semantic retrieval, RAG prompt
context, and citations.

Phase 12 is deliberately a user-to-document sharing model. It does not add
organizations, tenant isolation, provider-group synchronization, public links,
time-limited grants, or audit history; those require later tenancy and
governance phases.

## 12.1 Access contract and policy

### Two-layer authorization

```text
access JWT
    │
    ▼
global RBAC capability ── denied ──► HTTP 403
    │
    ▼
document resource policy ── denied ──► hide resource / omit retrieval candidate
    │
    ▼
document API, retrieval result, RAG context, or citation
```

The existing global permissions remain capability gates:

| Capability | Required global permission | Required document access |
| --- | --- | --- |
| Read metadata, extraction, chunks, indexing state, search, or chat | `documents:read` | `read` or `write` access. |
| Rename, delete, reprocess, retry, or manage sharing | `documents:write` | Owner, `write` access, or an administrator override. |
| Bypass a document grant for support or administration | `documents:manage` | None; this is an explicit global override. |

`documents:manage` is new in Phase 12 and is granted to the seeded
`administrator` role. It is deliberately separate from `documents:write`, so a
user who can edit a shared document does not automatically gain access to every
document in the deployment.

### Ownership and grants

`Document.uploader_user_id` becomes the initial owner identity for access
decisions while retaining its existing provenance meaning. The uploader has
implicit `read` and `write` access and does not need a database grant. Phase 12
does not support ownership transfer.

An owner, a user with document `write` access, or a `documents:manage`
administrator can create, change, and revoke one direct grant for another
active local user. A grant is either:

| Grant | Effective access |
| --- | --- |
| `read` | May read this active document and receive its chunks/citations. |
| `write` | Includes `read` and may perform document write actions and manage its grants. |

There is one current grant per `(document_id, user_id)`. Re-granting changes
the level rather than creating duplicate history rows. Self-grants are not
stored because owner access is implicit; a grant to the owner is rejected.
Deleted documents cannot be shared. Inactive users cannot receive or exercise
access.

### Visibility and non-disclosure

Global capability failures remain `403 Forbidden`. Once a user has the global
permission but lacks resource access, direct document, extraction, chunk,
indexing, job, and grant routes return `404 Not Found`; this avoids confirming
that another user's document exists. Lists omit inaccessible documents.

Retrieval never returns a candidate that fails the PostgreSQL resource policy.
It does not reveal an inaccessible document ID, title, chunk, similarity score,
or count. RAG receives only the filtered retrieval results, so it cannot cite
an inaccessible document. Revoking a grant affects later retrieval and chat
requests immediately because PostgreSQL is checked for every request; stale
Qdrant vectors remain harmless candidates.

### Scope boundaries

Phase 12 grants access directly to local users only. It does not:

- introduce tenant IDs or organization boundaries;
- copy SSO provider groups into authorization;
- add public, anonymous, expiring, or link-based sharing;
- persist a grant audit trail (Phase 13); or
- remove the existing global RBAC checks.

## Delivery checkpoints

- [x] 12.1 Access contract and policy
- [ ] 12.2 Document-access models and Alembic migration
- [ ] 12.3 Repository and policy service
- [ ] 12.4 Document API resource enforcement
- [ ] 12.5 Retrieval authority enforcement
- [ ] 12.6 RAG and citation enforcement
- [ ] 12.7 Sharing-management API and RBAC
- [ ] 12.8 Tests, Docker verification, and documentation
