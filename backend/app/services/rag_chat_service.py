"""Orchestrate retrieval, grounded generation, and application-issued citations."""

from collections.abc import Iterator
from dataclasses import dataclass

from app.chat.base import ChatModelProvider
from app.chat.citations import CitationValidationError
from app.chat.citations import CitationValidator
from app.chat.prompting import GroundedPromptBuilder
from app.chat.prompting import PromptContextError
from app.schemas.chat import ChatCitation
from app.schemas.chat import ChatStreamRequest
from app.schemas.retrieval import RetrievalSearchRequest
from app.services.retrieval_service import RetrievalService


_INSUFFICIENT_CONTEXT_MESSAGE = (
    "I don't have enough verified context in the available documents to answer that question."
)


class RagChatServiceError(Exception):
    """Raised when a generated response cannot satisfy AegisAI grounding rules."""


@dataclass(frozen=True)
class ChatAnswerFragment:
    """One validated non-empty model text fragment for a future transport layer."""

    text: str


@dataclass(frozen=True)
class ChatCompletion:
    """Terminal grounded-chat outcome and its application-issued citations."""

    answered: bool
    citations: tuple[ChatCitation, ...]


ChatGenerationEvent = ChatAnswerFragment | ChatCompletion


class RagChatService:
    """Produce a grounded chat event sequence without coupling it to HTTP or SSE."""

    def __init__(
        self,
        retrieval: RetrievalService,
        prompt_builder: GroundedPromptBuilder,
        chat_provider: ChatModelProvider,
        citation_validator: CitationValidator,
    ) -> None:
        self.retrieval = retrieval
        self.prompt_builder = prompt_builder
        self.chat_provider = chat_provider
        self.citation_validator = citation_validator

    def stream(self, request: ChatStreamRequest) -> Iterator[ChatGenerationEvent]:
        """Retrieve, stream a model answer, then validate its cited source labels."""
        retrieval_response = self.retrieval.search(
            RetrievalSearchRequest(
                query=request.question,
                limit=request.retrieval_limit,
                document_ids=request.document_ids,
                content_types=request.content_types,
            )
        )
        if not retrieval_response.items:
            yield ChatAnswerFragment(_INSUFFICIENT_CONTEXT_MESSAGE)
            yield ChatCompletion(answered=False, citations=())
            return

        try:
            prompt = self.prompt_builder.build(request.question, retrieval_response.items)
        except PromptContextError as error:
            raise RagChatServiceError("Verified retrieval context could not form a chat prompt") from error

        answer_fragments: list[str] = []
        for text in self.chat_provider.stream(prompt.messages):
            if not isinstance(text, str) or not text:
                raise RagChatServiceError("Chat provider returned an invalid answer fragment")
            answer_fragments.append(text)
            yield ChatAnswerFragment(text)

        answer = "".join(answer_fragments)
        if not answer.strip():
            raise RagChatServiceError("Chat provider returned an empty answer")
        try:
            citations = self.citation_validator.citations_for(answer, prompt)
        except CitationValidationError as error:
            raise RagChatServiceError("Generated answer referenced an unverified source") from error
        if not citations:
            raise RagChatServiceError("Generated answer did not include a verified source citation")
        yield ChatCompletion(answered=True, citations=citations)

    def close(self) -> None:
        """Release the per-request provider after its HTTP stream ends."""
        self.chat_provider.close()
