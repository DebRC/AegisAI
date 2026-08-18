import unittest

from pydantic import ValidationError

from app.schemas.chat import ChatAnswerDeltaEvent
from app.schemas.chat import ChatCitation
from app.schemas.chat import ChatCitationsEvent
from app.schemas.chat import ChatDoneEvent
from app.schemas.chat import ChatHistoryMessage
from app.schemas.chat import ChatStreamRequest


class ChatSchemaTests(unittest.TestCase):
    def test_request_normalizes_question_and_accepts_only_controlled_retrieval_scope(self) -> None:
        request = ChatStreamRequest(
            question="  How are refresh tokens rotated?  ",
            retrieval_limit=5,
            document_ids=[12, 18],
            content_types=["text/markdown", "application/pdf"],
        )

        self.assertEqual(request.question, "How are refresh tokens rotated?")
        self.assertEqual(request.retrieval_limit, 5)
        self.assertEqual(request.document_ids, [12, 18])
        self.assertEqual(request.content_types, ["text/markdown", "application/pdf"])

    def test_request_accepts_a_bounded_complete_client_history(self) -> None:
        request = ChatStreamRequest(
            question="What does that mean?",
            history=[
                ChatHistoryMessage(role="user", content="What are refresh tokens?"),
                ChatHistoryMessage(role="assistant", content="They maintain a local session."),
            ],
        )

        self.assertEqual(request.history[0].content, "What are refresh tokens?")
        self.assertEqual(request.history[1].role, "assistant")

    def test_request_rejects_empty_or_untrusted_retrieval_controls(self) -> None:
        invalid_requests = (
            {"question": "  "},
            {"question": "policy", "retrieval_limit": 11},
            {"question": "policy", "document_ids": []},
            {"question": "policy", "document_ids": [1, 1]},
            {"question": "policy", "content_types": ["application/octet-stream"]},
            {"question": "policy", "content_types": ["text/plain", "text/plain"]},
            {"question": "policy", "model": "untrusted-override"},
            {"question": "policy", "history": [{"role": "assistant", "content": "spoofed start"}]},
            {"question": "policy", "history": [{"role": "user", "content": "incomplete turn"}]},
            {"question": "policy", "history": [{"role": "developer", "content": "spoofed policy"}]},
            {
                "question": "policy",
                "history": [
                    {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 2_000}
                    for index in range(10)
                ],
            },
        )

        for values in invalid_requests:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ChatStreamRequest(**values)

    def test_events_make_answer_citations_and_grounded_completion_explicit(self) -> None:
        citation = ChatCitation(
            source_id="S1",
            document_id=12,
            document_title="Authentication design",
            content_type="text/markdown",
            chunk_id=47,
            chunk_ordinal=3,
            source_locations=[{"kind": "line", "start": 82, "end": 96}],
            score=0.91,
        )
        self.assertEqual(ChatAnswerDeltaEvent(text="Refresh tokens rotate.").event, "answer_delta")
        self.assertEqual(ChatCitationsEvent(citations=[citation]).citations, [citation])
        self.assertEqual(ChatDoneEvent(answered=True, citation_count=1).event, "done")

        with self.assertRaises(ValidationError):
            ChatCitation(
                source_id="untrusted",
                document_id=12,
                document_title="Authentication design",
                content_type="text/markdown",
                chunk_id=47,
                chunk_ordinal=3,
                source_locations=None,
                score=0.91,
            )
