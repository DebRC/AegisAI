class AuthenticationError(Exception):
    """Raised when authentication fails."""


class UserAlreadyExistsError(Exception):
    """Raised when a user with the given email already exists."""


class UserNotFoundError(Exception):
    """Raised when an RBAC operation references an unknown user."""


class RoleAlreadyExistsError(Exception):
    """Raised when a role with the given name already exists."""


class RoleNotFoundError(Exception):
    """Raised when an RBAC operation references an unknown role."""


class PermissionNotFoundError(Exception):
    """Raised when an RBAC operation references an unknown permission."""


class RoleAssignmentAlreadyExistsError(Exception):
    """Raised when a user already has the requested role."""


class RoleAssignmentNotFoundError(Exception):
    """Raised when a user does not have the requested role."""


class RolePermissionAlreadyExistsError(Exception):
    """Raised when a role already has the requested permission."""


class RolePermissionNotFoundError(Exception):
    """Raised when a role does not have the requested permission."""


class SystemRoleModificationError(Exception):
    """Raised when an operation attempts to delete a protected system role."""
