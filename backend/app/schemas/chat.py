"""Public grounded-chat contract for Phase 11 streaming RAG."""

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from app.schemas.retrieval import MAX_RETRIEVAL_DOCUMENT_FILTERS
from app.schemas.retrieval import RetrievalContentType


MAX_CHAT_QUESTION_CHARACTERS = 10_000
MAX_CHAT_RETRIEVAL_LIMIT = 10
MAX_CHAT_HISTORY_MESSAGES = 10
MAX_CHAT_HISTORY_MESSAGE_CHARACTERS = 4_000
MAX_CHAT_HISTORY_TOTAL_CHARACTERS = 16_000


class ChatHistoryMessage(BaseModel):
    """One client-supplied, untrusted prior conversational turn."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_HISTORY_MESSAGE_CHARACTERS)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ChatStreamRequest(BaseModel):
    """One bounded question and controlled retrieval scope for grounded chat."""

    question: str = Field(min_length=1, max_length=MAX_CHAT_QUESTION_CHARACTERS)
    retrieval_limit: int = Field(default=6, ge=1, le=MAX_CHAT_RETRIEVAL_LIMIT)
    document_ids: list[int] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_RETRIEVAL_DOCUMENT_FILTERS,
    )
    content_types: list[RetrievalContentType] | None = Field(default=None, min_length=1, max_length=4)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY_MESSAGES)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(document_id < 1 for document_id in value) or len(set(value)) != len(value):
            raise ValueError("document_ids must contain unique positive integers")
        return value

    @field_validator("content_types")
    @classmethod
    def validate_content_types(
        cls,
        value: list[RetrievalContentType] | None,
    ) -> list[RetrievalContentType] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("content_types must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_history(self) -> "ChatStreamRequest":
        """Accept only complete alternating client transcript turns before this question."""
        if sum(len(message.content) for message in self.history) > MAX_CHAT_HISTORY_TOTAL_CHARACTERS:
            raise ValueError("history exceeds the total character limit")
        for index, message in enumerate(self.history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError("history must alternate user and assistant messages starting with user")
        if self.history and self.history[-1].role != "assistant":
            raise ValueError("history must end with an assistant message before the current question")
        return self


class ChatCitation(BaseModel):
    """Application-issued citation to one verified retrieval result."""

    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    document_id: int = Field(ge=1)
    document_title: str = Field(min_length=1, max_length=255)
    content_type: RetrievalContentType
    chunk_id: int = Field(ge=1)
    chunk_ordinal: int = Field(ge=0)
    source_locations: list[dict[str, int | str]] | None
    score: float = Field(allow_inf_nan=False)


class ChatAnswerDeltaEvent(BaseModel):
    """One non-empty streamed answer fragment."""

    event: Literal["answer_delta"] = "answer_delta"
    text: str = Field(min_length=1, max_length=8_000)


class ChatCitationsEvent(BaseModel):
    """Terminal source list for an answer grounded in retrieval context."""

    event: Literal["citations"] = "citations"
    citations: list[ChatCitation] = Field(min_length=1, max_length=MAX_CHAT_RETRIEVAL_LIMIT)


class ChatDoneEvent(BaseModel):
    """Terminal event that distinguishes grounded answers from insufficient context."""

    event: Literal["done"] = "done"
    answered: bool
    citation_count: int = Field(ge=0, le=MAX_CHAT_RETRIEVAL_LIMIT)


class ChatErrorEvent(BaseModel):
    """Safe terminal stream error; provider internals never cross this boundary."""

    event: Literal["error"] = "error"
    detail: str = Field(min_length=1, max_length=255)
