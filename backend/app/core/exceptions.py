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


class AdministratorSelfDeactivationError(Exception):
    """Raised when an administrator tries to disable their own current account."""


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


class DocumentValidationError(Exception):
    """Raised when uploaded document metadata violates the ingestion policy."""


class DocumentPersistenceError(Exception):
    """Raised when document metadata cannot be committed after storage succeeds."""


class DocumentNotFoundError(Exception):
    """Raised when a requested document is absent or has been soft-deleted."""


class DocumentExtractionNotFoundError(Exception):
    """Raised when an active document does not yet have extracted output."""


class DocumentAccessGrantNotFoundError(Exception):
    """Raised when a direct document-access grant does not exist."""


class DocumentAccessOwnerGrantError(Exception):
    """Raised when an operation tries to store a redundant owner grant."""


class DocumentAccessGranteeInactiveError(Exception):
    """Raised when a grant target is not an active local user."""


class AuditEventValidationError(Exception):
    """Raised when code attempts to record unsafe audit-event data."""


class ProcessingJobNotFoundError(Exception):
    """Raised when a processing job is absent or belongs to another document."""


class ProcessingJobStateError(Exception):
    """Raised when an operation is incompatible with a job's current state."""


class ProcessingJobPersistenceError(Exception):
    """Raised when durable job or outbox state cannot be committed."""


class ApiKeyAuthenticationError(Exception):
    """Raised when a presented machine credential is absent, expired, or invalid."""


class ApiKeyValidationError(Exception):
    """Raised when API-key lifecycle input violates the governance contract."""


class RateLimitExceededError(Exception):
    """Raised when a tenant principal exceeds its bounded request allowance."""


class RateLimitUnavailableError(Exception):
    """Raised when the configured rate-limit authority cannot be reached."""


class RetentionPolicyValidationError(Exception):
    """Raised when automatic source-document expiry is configured unsafely."""
