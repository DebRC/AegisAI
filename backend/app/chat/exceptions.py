"""Safe domain errors for external streaming chat providers."""


class ChatProviderConfigurationError(Exception):
    """Raised when a chat provider cannot be configured safely."""


class ChatProviderError(Exception):
    """Raised when a chat provider cannot produce a usable stream."""


class ChatProviderResponseError(ChatProviderError):
    """Raised when a provider stream violates the chat-provider contract."""
