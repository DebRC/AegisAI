class AuthenticationError(Exception):
    """Raised when authentication fails."""


class SsoProviderConfigurationError(Exception):
    """Raised when an SSO provider has incomplete configuration."""


class SsoProviderError(Exception):
    """Raised when an external SSO provider rejects or cannot complete a flow."""


class SsoTransactionError(Exception):
    """Raised when an SSO browser transaction is invalid or expired."""


class SsoEmailVerificationError(Exception):
    """Raised when an SSO identity cannot safely identify a local account."""


class SsoAccountResolutionError(Exception):
    """Raised when a concurrent SSO account-linking operation conflicts."""


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
