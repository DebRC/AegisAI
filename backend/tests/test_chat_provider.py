import json
import unittest

import httpx

from app.chat.base import ChatMessage
from app.chat.exceptions import ChatProviderConfigurationError
from app.chat.exceptions import ChatProviderError
from app.chat.exceptions import ChatProviderResponseError
from app.chat.factory import create_chat_model_provider
from app.chat.openai import OpenAIChatModelProvider
from app.core.config import Settings


class ChatMessageTests(unittest.TestCase):
    def test_allows_only_non_empty_developer_and_user_messages(self) -> None:
        self.assertEqual(ChatMessage("developer", "Instructions").role, "developer")
        self.assertEqual(ChatMessage("user", "Question").content, "Question")

        for role, content in (("assistant", "No"), ("user", " ")):
            with self.subTest(role=role, content=content):
                with self.assertRaises(ValueError):
                    ChatMessage(role, content)  # type: ignore[arg-type]


class OpenAIChatModelProviderTests(unittest.TestCase):
    _REQUIRED_SETTINGS = {
        "APP_NAME": "AegisAI",
        "APP_VERSION": "test",
        "APP_ENV": "test",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "QDRANT_URL": "http://qdrant:6333",
        "JWT_SECRET_KEY": "test-secret",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
    }

    def test_streams_only_text_deltas_from_the_responses_api(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["url"] = str(request.url)
            observed["authorization"] = request.headers["Authorization"]
            observed["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    b"event: response.created\n"
                    b'data: {"type":"response.created"}\n\n'
                    b"event: response.output_text.delta\n"
                    b'data: {"type":"response.output_text.delta","delta":"Grounded "}\n\n'
                    b"event: response.output_text.delta\n"
                    b'data: {"type":"response.output_text.delta","delta":"answer"}\n\n'
                    b"event: response.completed\n"
                    b'data: {"type":"response.completed"}\n\n'
                ),
            )

        provider = self._provider(httpx.MockTransport(handler))

        result = list(
            provider.stream([ChatMessage("developer", "Use sources."), ChatMessage("user", "Question?")])
        )

        self.assertEqual(result, ["Grounded ", "answer"])
        self.assertEqual(observed["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(observed["authorization"], "Bearer test-openai-key")
        self.assertEqual(
            observed["payload"],
            {
                "model": "gpt-5.6",
                "input": [
                    {"role": "developer", "content": "Use sources."},
                    {"role": "user", "content": "Question?"},
                ],
                "max_output_tokens": 1024,
                "stream": True,
                "store": False,
            },
        )

    def test_rejects_missing_key_invalid_messages_failures_and_invalid_events(self) -> None:
        with self.assertRaises(ChatProviderConfigurationError):
            OpenAIChatModelProvider(self._configuration(OPENAI_API_KEY=""))

        provider = self._provider(httpx.MockTransport(lambda _: httpx.Response(200)))
        for invalid_messages in ([], ["not a message"]):
            with self.subTest(invalid_messages=invalid_messages):
                with self.assertRaises(ChatProviderError):
                    list(provider.stream(invalid_messages))  # type: ignore[arg-type]

        failed_provider = self._provider(httpx.MockTransport(lambda _: httpx.Response(429)))
        with self.assertRaises(ChatProviderError):
            list(failed_provider.stream([ChatMessage("user", "Question")]))

        for event_data in (
            b"data: not-json\n\n",
            b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":""}\n\n',
            b'event: error\ndata: {"type":"error","message":"raw provider detail"}\n\n',
        ):
            with self.subTest(event_data=event_data):
                provider = self._provider(
                    httpx.MockTransport(lambda _, event_data=event_data: httpx.Response(200, content=event_data))
                )
                with self.assertRaises((ChatProviderError, ChatProviderResponseError)):
                    list(provider.stream([ChatMessage("user", "Question")]))

    def test_factory_returns_the_configured_provider(self) -> None:
        provider = create_chat_model_provider(
            self._configuration(),
            http_client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
        )

        self.assertIsInstance(provider, OpenAIChatModelProvider)

    def _configuration(self, **overrides: object) -> Settings:
        return Settings(
            **(
                self._REQUIRED_SETTINGS
                | {
                    "OPENAI_API_KEY": "test-openai-key",
                    **overrides,
                }
            )
        )

    def _provider(self, transport: httpx.BaseTransport) -> OpenAIChatModelProvider:
        return OpenAIChatModelProvider(
            self._configuration(),
            httpx.Client(base_url="https://api.openai.com/v1/", transport=transport),
        )
