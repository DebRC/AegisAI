# RBAC design

## Purpose

Phase 4 adds database-backed role-based access control (RBAC) to AegisAI. It
will determine what an authenticated user may do without changing the existing
JWT authentication flow.

## Authorization model

```text
User ──< user_roles >── Role ──< role_permissions >── Permission
```

- A user may have multiple roles.
- A role may have multiple permissions.
- Permissions are the smallest unit used to authorize an action.
- Roles grant permissions; users do not receive direct permission grants in
  this phase.

The database will be the source of truth. Access tokens identify the user but
will not contain roles or permissions. This means role changes and revocations
take effect on the next request instead of waiting for an access token to
expire.

## Permission contract

Permission values use the stable format `resource:action`. The canonical
application values are defined in
`backend/app/security/permissions.py` as `PermissionCode`.

| Permission | Intended use |
| --- | --- |
| `documents:read` | Read documents and their metadata |
| `documents:write` | Upload, update, or delete documents |
| `users:read` | View users for administration |
| `users:manage` | Activate, deactivate, or otherwise administer users |
| `roles:read` | View roles and their permissions |
| `roles:manage` | Create, change, or delete roles and role permissions |
| `roles:assign` | Assign or remove roles for users |

The catalogue is seeded as database records by the Phase 4.3 migration. A new
protected capability must add its permission here, seed it through a reviewed
migration, and use it in its authorization dependency.

## Rules and boundaries

- Permissions are assigned explicitly to roles; no implicit permission is
  granted by a role name.
- New users receive no privileged role automatically.
- The seeded `administrator` role receives every canonical permission, but is
  not assigned automatically. After registering the first operator and applying
  migrations, run the explicit bootstrap command:

  ```bash
  cd backend
  venv/bin/python -m scripts.bootstrap_administrator admin@example.com
  ```
- Inactive users must not pass permission checks.
- Role and permission changes are committed transactionally by the service
  layer, consistent with the authentication implementation.

## Not part of Phase 4

The following remain out of scope until later phases:

- SSO or external identity-provider roles
- Direct user-to-permission grants or explicit deny rules
- Role hierarchies and inherited roles
- Tenant-scoped roles or permissions
- Audit-log event publishing

## Implementation sequence

1. Define this contract and the permission catalogue (4.1).
2. Add the RBAC models and schema migration (4.2).
3. Seed permissions and bootstrap the administrator role (4.3).
4. Add repositories, service operations, management APIs, and the
   `require_permission()` dependency (4.4–4.7).
5. Verify authorization behavior, bootstrap operations, and migration state
   (4.8).
