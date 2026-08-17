import json
import unittest

from app.chat.streaming import encode_sse
from app.chat.streaming import stream_chat_sse
from app.schemas.chat import ChatAnswerDeltaEvent
from app.services.rag_chat_service import ChatAnswerFragment
from app.services.rag_chat_service import ChatCompletion
from app.services.rag_chat_service import RagChatServiceError
from app.schemas.chat import ChatCitation


def _decoded_events(stream: list[str]) -> list[tuple[str, dict[str, object]]]:
    return [
        (
            message.splitlines()[0].removeprefix("event: "),
            json.loads(message.splitlines()[1].removeprefix("data: ")),
        )
        for message in stream
    ]


class ChatSseTests(unittest.TestCase):
    def test_encodes_framed_json_events(self) -> None:
        encoded = encode_sse(ChatAnswerDeltaEvent(text="A newline\nand JSON-safe quotes: \"yes\"."))

        self.assertTrue(encoded.startswith("event: answer_delta\ndata: "))
        self.assertTrue(encoded.endswith("\n\n"))
        self.assertEqual(json.loads(encoded.splitlines()[1].removeprefix("data: "))["text"], "A newline\nand JSON-safe quotes: \"yes\".")

    def test_streams_answer_citations_then_terminal_done(self) -> None:
        citation = ChatCitation(
            source_id="S1",
            document_id=3,
            document_title="Security guide",
            content_type="text/markdown",
            chunk_id=7,
            chunk_ordinal=2,
            source_locations=None,
            score=0.91,
        )

        messages = list(stream_chat_sse(iter((ChatAnswerFragment("Answer [S1]."), ChatCompletion(True, (citation,))))))

        events = _decoded_events(messages)
        self.assertEqual([event[0] for event in events], ["answer_delta", "citations", "done"])
        self.assertEqual(events[1][1]["citations"][0]["source_id"], "S1")
        self.assertEqual(events[2][1], {"event": "done", "answered": True, "citation_count": 1})

    def test_emits_insufficient_context_done_without_citations(self) -> None:
        events = _decoded_events(
            list(stream_chat_sse(iter((ChatAnswerFragment("Insufficient context."), ChatCompletion(False, ())))))
        )

        self.assertEqual([event[0] for event in events], ["answer_delta", "done"])
        self.assertEqual(events[-1][1]["answered"], False)
        self.assertEqual(events[-1][1]["citation_count"], 0)

    def test_replaces_expected_failures_with_one_safe_error_event(self) -> None:
        def failing_events():
            yield ChatAnswerFragment("Partial output")
            raise RagChatServiceError("provider-specific detail must not cross HTTP")

        events = _decoded_events(list(stream_chat_sse(failing_events())))

        self.assertEqual([event[0] for event in events], ["answer_delta", "error"])
        self.assertEqual(events[-1][1], {
            "event": "error",
            "detail": "Grounded chat is temporarily unavailable",
        })
