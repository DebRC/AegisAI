from enum import Enum


class PermissionCode(str, Enum):
    """Canonical permission identifiers enforced by the application."""

    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    ROLES_READ = "roles:read"
    ROLES_MANAGE = "roles:manage"
    ROLES_ASSIGN = "roles:assign"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(permission.value for permission in cls)
