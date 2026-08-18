"""Provider-neutral values and protocol for streamed chat generation."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    """One trusted prompt message prepared by the application."""

    role: Literal["developer", "user"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"developer", "user"}:
            raise ValueError("Chat message role must be developer or user")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Chat message content must be a non-empty string")


class ChatModelProvider(Protocol):
    """Generate plain answer fragments from application-owned messages."""

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        """Yield non-empty text fragments in model order."""

    def close(self) -> None:
        """Release provider-owned resources when an operation ends."""
