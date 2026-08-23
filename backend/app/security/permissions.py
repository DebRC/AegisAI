from enum import Enum


class PermissionCode(str, Enum):
    """Canonical permission identifiers enforced by the application."""

    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    DOCUMENTS_MANAGE = "documents:manage"
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    ROLES_READ = "roles:read"
    ROLES_MANAGE = "roles:manage"
    ROLES_ASSIGN = "roles:assign"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(permission.value for permission in cls)


PERMISSION_DESCRIPTIONS: dict[PermissionCode, str] = {
    PermissionCode.DOCUMENTS_READ: "Read documents and their metadata.",
    PermissionCode.DOCUMENTS_WRITE: "Create, update, and delete documents.",
    PermissionCode.DOCUMENTS_MANAGE: "Manage access to every document.",
    PermissionCode.USERS_READ: "View users for administration.",
    PermissionCode.USERS_MANAGE: "Manage user accounts.",
    PermissionCode.ROLES_READ: "View roles and their permissions.",
    PermissionCode.ROLES_MANAGE: "Create, update, and delete roles.",
    PermissionCode.ROLES_ASSIGN: "Assign and remove user roles.",
}

SYSTEM_ADMIN_ROLE_NAME = "administrator"
SYSTEM_ADMIN_ROLE_DESCRIPTION = "Full access to all AegisAI permissions."
