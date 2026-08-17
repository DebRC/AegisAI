"""Serialize grounded-chat domain events as a small, safe SSE protocol."""

from collections.abc import Iterator

from sqlalchemy.exc import SQLAlchemyError

from app.chat.exceptions import ChatProviderConfigurationError
from app.chat.exceptions import ChatProviderError
from app.embeddings.exceptions import EmbeddingProviderError
from app.integrations.vector_store.exceptions import VectorStoreError
from app.schemas.chat import ChatAnswerDeltaEvent
from app.schemas.chat import ChatCitationsEvent
from app.schemas.chat import ChatDoneEvent
from app.schemas.chat import ChatErrorEvent
from app.services.query_embedding_service import QueryEmbeddingError
from app.services.rag_chat_service import ChatAnswerFragment
from app.services.rag_chat_service import ChatCompletion
from app.services.rag_chat_service import ChatGenerationEvent
from app.services.rag_chat_service import RagChatServiceError


_SAFE_STREAM_ERROR = "Grounded chat is temporarily unavailable"


def encode_sse(event: ChatAnswerDeltaEvent | ChatCitationsEvent | ChatDoneEvent | ChatErrorEvent) -> str:
    """Render one application event using the SSE event/data framing format."""
    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"


def stream_chat_sse(events: Iterator[ChatGenerationEvent]) -> Iterator[str]:
    """Map domain events to SSE and convert expected failures into one safe terminal event."""
    try:
        for event in events:
            if isinstance(event, ChatAnswerFragment):
                yield encode_sse(ChatAnswerDeltaEvent(text=event.text))
            elif isinstance(event, ChatCompletion):
                if event.citations:
                    yield encode_sse(ChatCitationsEvent(citations=list(event.citations)))
                yield encode_sse(
                    ChatDoneEvent(
                        answered=event.answered,
                        citation_count=len(event.citations),
                    )
                )
            else:
                raise RagChatServiceError("Grounded chat produced an unsupported event")
    except (
        ChatProviderConfigurationError,
        ChatProviderError,
        EmbeddingProviderError,
        QueryEmbeddingError,
        RagChatServiceError,
        SQLAlchemyError,
        VectorStoreError,
    ):
        yield encode_sse(ChatErrorEvent(detail=_SAFE_STREAM_ERROR))
