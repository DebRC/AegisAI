# Multi-tenancy and tenant isolation

Phase 19 turns AegisAI from a single shared installation into an
organization-isolated platform. It preserves the current single-organization
development data by migrating it into one default tenant.

## 19.1 Tenant boundary and migration contract

### Goal

A user can belong to one or more tenants. Every organization-owned resource is
read, written, processed, retrieved, cited, and audited only within the active
tenant selected for that authenticated request.

```text
Global identity                         Tenant-owned data

User ──< TenantMembership >── Tenant ──< Document ──< extraction/chunks/jobs
  │              │               │            │
  │              └──< tenant role assignments │
  └── refresh tokens / SSO identities          └── Qdrant payload tenant_id
```

### Data ownership policy

| Record | Scope | Reason |
| --- | --- | --- |
| User, password hash, refresh tokens, external identity | Global | One human identity can legitimately join multiple organizations. |
| Tenant | Organization | The immutable isolation boundary. A slug is a safe, human-readable identifier, not an authorization credential. |
| Tenant membership | User + tenant | Determines whether a user may select the tenant and whether the membership is active. |
| Roles and role assignments | Tenant | The same user can be an administrator in one tenant and a reader in another. Permissions remain a global catalog. |
| Documents and direct access grants | Tenant | A document and every user receiving a direct grant must belong to the same tenant. |
| Jobs, outbox records, extraction, chunks, embeddings, cleanup requests | Inherit document tenant | Worker execution derives tenant ownership from the authoritative document; no worker task accepts a caller-controlled tenant. |
| Qdrant vectors | Tenant-tagged derived data | `tenant_id` is used as a candidate prefilter. PostgreSQL tenant and membership checks remain authoritative. |
| Audit events | Tenant-tagged when the event concerns tenant data | Tenant administrators can view only their tenant's events; platform bootstrap events remain separately controlled. |

### Active-tenant request policy

1. Authentication proves the global AegisAI user identity.
2. A short-lived access token carries one active `tenant_id`; a refresh token is
   bound to the same selected tenant when it issues the next token pair.
3. The request dependency loads an active membership for `(user_id, tenant_id)`.
   Missing, inactive, or foreign membership is rejected before RBAC or resource
   lookup.
4. Permission evaluation uses the active tenant's role assignments only.
5. Every repository query accepts the resolved tenant context and includes it in
   the database predicate. A guessed ID must look the same as an absent ID.

There is no client-provided tenant header accepted as authority. A browser
tenant switch is an authenticated server operation that verifies membership and
returns a newly scoped AegisAI token pair.

### Role model migration

The current roles, role-permission links, and permission catalog are useful but
their user assignment is global. Phase 19 will change that safely:

- Permissions remain global, stable capability definitions such as
  `documents:read`.
- Each role belongs to exactly one tenant; role names become unique within that
  tenant rather than globally.
- A role assignment targets a tenant membership, not a bare user. This prevents
  an assignment from granting a role in a different organization.
- The existing `administrator` system role is copied/seeded per tenant. It is
  powerful only inside that tenant, not across all tenants.

### Legacy data migration

The migration is forward-only and preserves IDs where possible:

1. Create one active `Default organization` tenant with a deterministic local
   slug.
2. Create an active membership in that tenant for every existing user.
3. Move existing roles and user-role assignments into the default tenant.
4. Add the default tenant to every existing document, then derive all related
   processing, extraction, embedding, retrieval, and audit ownership through
   that document.
5. Preserve existing document access grants because every existing grantee is
   a member of the same default tenant after step 2.
6. Make tenant foreign keys non-nullable only after the backfill succeeds and
   add tenant-scoped unique constraints and indexes.

This maintains the current behavior for local Compose users while making later
tenant creation and invitation explicit. The migration never silently exposes a
legacy document to a new tenant.

### Storage, retrieval, and worker rules

- New storage keys begin with a server-generated tenant segment; original
  filenames never determine a path.
- Upload creates a document only in the active tenant. A worker re-reads the
  document row and derives the tenant after it claims work.
- Qdrant payloads include the document tenant ID and Qdrant search receives an
  enforced tenant filter. PostgreSQL then validates the current document,
  membership, direct grant, extraction, and embedding records before returning
  any text.
- Tenant-scoped document deletion queues only tenant-owned vector cleanup.
- RAG prompts and citations are built only from verified tenant-scoped
  retrieval results.

### Explicit non-goals

- Cross-tenant document sharing, cross-tenant search, and cross-tenant roles.
- A global super-administrator API exposed to ordinary browser users.
- Database-per-tenant or Qdrant-collection-per-tenant. The first deployment
  model is shared infrastructure with strict row/query and vector-payload
  isolation; a future deployment can shard tenants without changing the API
  contract.
- Billing, per-tenant API keys, quota enforcement, and retention policies;
  those belong to Phase 20.

## Implemented design

### Database migration and membership model

The forward-only migration creates `tenants` and `tenant_memberships`, moves
all legacy users and tenant-owned records into `Default organization`, and then
makes the relevant tenant foreign keys non-null in PostgreSQL. Roles and
`user_roles` are tenant-owned; their names and assignments are therefore unique
within the organization, not across the installation. Existing administrator
roles are preserved in the default tenant. Creating a later tenant clones the
system roles and assigns its creator the tenant-local administrator role.

`POST /tenants/{tenant_id}/memberships` adds an already-existing active AegisAI
user to the selected organization. Membership grants no role by itself. An
administrator must explicitly use the normal RBAC route to assign one.

### Request and data enforcement

Access JWTs and persisted refresh tokens carry a selected `tenant_id`.
`get_current_tenant_context` verifies that the authenticated user has an active
membership before resource authorization. RBAC checks include that tenant ID;
each protected repository/service query receives the same context. The browser
switcher calls `POST /tenants/{tenant_id}/select`, which returns replacement
server-managed session cookies only after that membership check.

The following use the active tenant boundary:

- document upload/list/read/update/delete and direct access checks;
- document storage keys, processing ownership, indexing metadata, Qdrant
  candidate payload/filter, retrieval authority checks, RAG context, and citations;
- role and user-role administration, document/job administration, overview
  aggregates, and tenant audit queries;
- created API keys and retention policies (Phase 20).

Qdrant is only a tenant-filtered candidate source. PostgreSQL remains the
authority for document state, tenant ownership, membership, direct grant, and
current extraction/embedding relationships. Existing vectors created before
this migration lack the tenant payload and are safely suppressed; reprocess
affected documents to index tenant-tagged replacements.

### Manual verification

1. Start with the canonical local command in the repository README and sign in
   as the bootstrap administrator.
2. `GET /tenants` lists the `Default organization`; create a second tenant with
   `POST /tenants`, then select it with `POST /tenants/{id}/select` and replace
   the bearer token with the returned access token.
3. Upload a document in each tenant. Each tenant token must list only its own
   document, and fetching the other tenant’s numeric document ID returns `404`.
4. Use the browser at `http://localhost:3000/tenants` to perform the same
   switch. Documents and administrative counts change with the selected tenant.
5. For a second existing local user, add a membership then explicitly assign a
   tenant role. Confirm their token cannot select or read the other tenant.
6. Reprocess a pre-tenant document and confirm retrieval/RAG results only cite
   documents from the selected tenant.

### Phase 19 checkpoints

- [x] 19.1 Tenant boundary, active-context, and safe legacy-migration contract
- [x] 19.2 Tenant, membership, role, and token schema migration
- [x] 19.3 Tenant-context authentication and RBAC enforcement
- [x] 19.4 Tenant-scoped document, processing, extraction, administration, and audit paths
- [x] 19.5 Tenant-safe vector indexing, retrieval, and RAG citations
- [x] 19.6 Tenant creation, membership management, and browser switching
- [x] 19.7 Isolation tests, Docker verification, and consolidated documentation
