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
from app.services.audit_event_service import AuditEventService
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType


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
        audit_events: AuditEventService | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.prompt_builder = prompt_builder
        self.chat_provider = chat_provider
        self.citation_validator = citation_validator
        self.audit_events = audit_events

    def stream(self, request: ChatStreamRequest, *, user_id: int) -> Iterator[ChatGenerationEvent]:
        """Retrieve, stream a model answer, then validate its cited source labels."""
        try:
            retrieval_response = self.retrieval.search(
                RetrievalSearchRequest(
                    query=request.question,
                    limit=request.retrieval_limit,
                    document_ids=request.document_ids,
                    content_types=request.content_types,
                ),
                user_id=user_id,
            )
        except Exception:
            self._record_chat_failure(user_id=user_id)
            raise
        if not retrieval_response.items:
            self._record_chat_request(user_id=user_id, result_count=0)
            yield ChatAnswerFragment(_INSUFFICIENT_CONTEXT_MESSAGE)
            yield ChatCompletion(answered=False, citations=())
            return

        try:
            prompt = self.prompt_builder.build(request.question, retrieval_response.items, request.history)
        except PromptContextError as error:
            self._record_chat_failure(user_id=user_id)
            raise RagChatServiceError("Verified retrieval context could not form a chat prompt") from error

        answer_fragments: list[str] = []
        for text in self.chat_provider.stream(prompt.messages):
            if not isinstance(text, str) or not text:
                self._record_chat_failure(user_id=user_id)
                raise RagChatServiceError("Chat provider returned an invalid answer fragment")
            answer_fragments.append(text)
            yield ChatAnswerFragment(text)

        answer = "".join(answer_fragments)
        if not answer.strip():
            self._record_chat_failure(user_id=user_id)
            raise RagChatServiceError("Chat provider returned an empty answer")
        try:
            citations = self.citation_validator.citations_for(answer, prompt)
        except CitationValidationError as error:
            self._record_chat_failure(user_id=user_id)
            raise RagChatServiceError("Generated answer referenced an unverified source") from error
        if not citations:
            self._record_chat_failure(user_id=user_id)
            raise RagChatServiceError("Generated answer did not include a verified source citation")
        self._record_chat_request(user_id=user_id, result_count=len(retrieval_response.items))
        yield ChatCompletion(answered=True, citations=citations)

    def _record_chat_request(self, *, user_id: int, result_count: int) -> None:
        if self.audit_events is None:
            return
        self.audit_events.record_best_effort(
            event_type=AuditEventType.CHAT_REQUEST,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=user_id,
            metadata={"result_count": result_count},
        )

    def _record_chat_failure(self, *, user_id: int) -> None:
        if self.audit_events is None:
            return
        self.audit_events.record_best_effort(
            event_type=AuditEventType.CHAT_REQUEST,
            outcome=AuditEventOutcome.FAILED,
            actor_user_id=user_id,
        )

    def close(self) -> None:
        """Release the per-request provider after its HTTP stream ends."""
        self.chat_provider.close()
