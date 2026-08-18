import unittest

from app.chat.citations import CitationValidator
from app.chat.prompting import GroundedPromptBuilder
from app.schemas.chat import ChatStreamRequest
from app.schemas.retrieval import RetrievalSearchResponse
from app.schemas.retrieval import RetrievalSearchResult
from app.services.rag_chat_service import ChatAnswerFragment
from app.services.rag_chat_service import ChatCompletion
from app.services.rag_chat_service import RagChatService
from app.services.rag_chat_service import RagChatServiceError


class _RetrievalStub:
    def __init__(self, response: RetrievalSearchResponse) -> None:
        self.response = response
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return self.response


class _ChatProviderStub:
    def __init__(self, fragments: tuple[str, ...]) -> None:
        self.fragments = fragments
        self.messages = []

    def stream(self, messages):
        self.messages.append(messages)
        yield from self.fragments

    def close(self) -> None:
        pass


class RagChatServiceTests(unittest.TestCase):
    def _result(self) -> RetrievalSearchResult:
        return RetrievalSearchResult(
            document_id=3,
            document_title="Security guide",
            content_type="text/markdown",
            chunk_id=7,
            chunk_ordinal=2,
            content="AegisAI uses verified retrieval results.",
            source_locations=[{"page": 4}],
            score=0.91,
        )

    def _service(self, items, fragments: tuple[str, ...]):
        retrieval = _RetrievalStub(RetrievalSearchResponse(items=items, limit=6))
        provider = _ChatProviderStub(fragments)
        return (
            RagChatService(
                retrieval=retrieval,
                prompt_builder=GroundedPromptBuilder(1_000),
                chat_provider=provider,
                citation_validator=CitationValidator(),
            ),
            retrieval,
            provider,
        )

    def test_retrieves_streams_and_issues_only_verified_citations(self) -> None:
        service, retrieval, provider = self._service([self._result()], ("It uses verified ", "results [S1]."))

        events = list(
            service.stream(
                ChatStreamRequest(
                    question="How does it work?",
                    retrieval_limit=4,
                    document_ids=[3],
                    content_types=["text/markdown"],
                    history=[
                        {"role": "user", "content": "Tell me about the guide."},
                        {"role": "assistant", "content": "It covers AegisAI."},
                    ],
                )
            )
        )

        self.assertEqual([event.text for event in events if isinstance(event, ChatAnswerFragment)], ["It uses verified ", "results [S1]."])
        completion = events[-1]
        self.assertIsInstance(completion, ChatCompletion)
        self.assertTrue(completion.answered)
        self.assertEqual(completion.citations[0].document_id, 3)
        self.assertEqual(retrieval.requests[0].query, "How does it work?")
        self.assertEqual(retrieval.requests[0].limit, 4)
        self.assertEqual(retrieval.requests[0].document_ids, [3])
        self.assertEqual(provider.messages[0][0].role, "developer")
        self.assertIn("untrusted_conversation_history_json", provider.messages[0][1].content)

    def test_returns_an_insufficient_context_completion_without_calling_the_model(self) -> None:
        service, retrieval, provider = self._service([], ("should not be used",))

        events = list(service.stream(ChatStreamRequest(question="What is this?")))

        self.assertEqual(events[0], ChatAnswerFragment(
            "I don't have enough verified context in the available documents to answer that question."
        ))
        self.assertEqual(events[1], ChatCompletion(answered=False, citations=()))
        self.assertEqual(len(retrieval.requests), 1)
        self.assertEqual(provider.messages, [])

    def test_rejects_empty_or_uncited_or_unknown_citation_answers(self) -> None:
        for fragments in ((), ("An uncited answer.",), ("An invented source [S2].",), ("",)):
            with self.subTest(fragments=fragments):
                service, _, _ = self._service([self._result()], fragments)
                with self.assertRaises(RagChatServiceError):
                    list(service.stream(ChatStreamRequest(question="Question")))
