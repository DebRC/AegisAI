"""Create configured chat providers without leaking a provider choice to RAG."""

import httpx

from app.chat.base import ChatModelProvider
from app.chat.openai import OpenAIChatModelProvider
from app.core.config import Settings


def create_chat_model_provider(
    configuration: Settings,
    http_client: httpx.Client | None = None,
) -> ChatModelProvider:
    """Create the selected streaming chat provider."""
    if configuration.CHAT_PROVIDER == "openai":
        return OpenAIChatModelProvider(configuration, http_client=http_client)
    raise ValueError("Unsupported chat provider")
