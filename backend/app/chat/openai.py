"""OpenAI Responses API implementation of the streaming chat contract."""

from collections.abc import Iterator, Sequence
import json
from typing import Any

import httpx

from app.chat.base import ChatMessage
from app.chat.exceptions import ChatProviderConfigurationError
from app.chat.exceptions import ChatProviderError
from app.chat.exceptions import ChatProviderResponseError
from app.core.config import Settings


class OpenAIChatModelProvider:
    """Yield only OpenAI text deltas, hiding transport event details from RAG."""

    provider_name = "openai"

    def __init__(self, configuration: Settings, http_client: httpx.Client | None = None):
        api_key = configuration.OPENAI_API_KEY
        secret = api_key.get_secret_value().strip() if api_key is not None else ""
        if not secret:
            raise ChatProviderConfigurationError(
                "OPENAI_API_KEY must be configured before chat responses can be generated"
            )
        self.model = configuration.CHAT_MODEL
        self.max_output_tokens = configuration.CHAT_MAX_OUTPUT_TOKENS
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=f"{configuration.OPENAI_BASE_URL}/",
            timeout=configuration.CHAT_REQUEST_TIMEOUT_SECONDS,
        )
        self._headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        }

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        """Request a Responses API SSE stream and yield validated text deltas."""
        payload = self._request_payload(messages)
        event_name: str | None = None
        try:
            with self._client.stream(
                "POST",
                "responses",
                headers=self._headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        event_name = None
                        continue
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    yield from self._parse_event(event_name, line.removeprefix("data:").strip())
        except httpx.HTTPError as error:
            raise ChatProviderError("OpenAI chat request failed") from error

    def close(self) -> None:
        """Close only the HTTP client owned by this provider."""
        if self._owns_client:
            self._client.close()

    def _request_payload(self, messages: Sequence[ChatMessage]) -> dict[str, object]:
        if isinstance(messages, (str, bytes)) or not messages:
            raise ChatProviderError("Chat messages are invalid")
        validated_messages = list(messages)
        if any(not isinstance(message, ChatMessage) for message in validated_messages):
            raise ChatProviderError("Chat messages are invalid")
        return {
            "model": self.model,
            "input": [
                {"role": message.role, "content": message.content}
                for message in validated_messages
            ],
            "max_output_tokens": self.max_output_tokens,
            "stream": True,
            # Phase 11 owns its chat state and never needs provider-side storage.
            "store": False,
        }

    def _parse_event(self, event_name: str | None, data: str) -> Iterator[str]:
        try:
            payload: Any = json.loads(data)
        except json.JSONDecodeError as error:
            raise ChatProviderResponseError("OpenAI chat stream contained invalid event data") from error
        if not isinstance(payload, dict):
            raise ChatProviderResponseError("OpenAI chat stream contained invalid event data")

        event_type = payload.get("type", event_name)
        if event_type == "response.output_text.delta":
            delta = payload.get("delta")
            if not isinstance(delta, str) or not delta:
                raise ChatProviderResponseError("OpenAI chat stream contained an invalid text delta")
            yield delta
        elif event_type == "error" or event_name == "error":
            raise ChatProviderError("OpenAI chat generation failed")
