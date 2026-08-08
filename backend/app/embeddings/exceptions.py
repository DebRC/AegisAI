"""Safe domain errors for external embedding providers."""


class EmbeddingProviderConfigurationError(Exception):
    """Raised when an embedding provider cannot be configured safely."""


class EmbeddingProviderError(Exception):
    """Raised when an embedding provider cannot generate a usable result."""


class EmbeddingProviderResponseError(EmbeddingProviderError):
    """Raised when a provider response does not satisfy the embedding contract."""
