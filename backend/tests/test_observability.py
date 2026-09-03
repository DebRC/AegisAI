"""Focused tests for Phase 16's safe operational signals."""

import asyncio
import importlib
import json
import logging
import unittest
from unittest.mock import MagicMock, patch

from fastapi import Request, Response

from app.api import health as health_api
from app.core.logging import JsonFormatter
from app.core.metrics import metrics_response
from app.core.request_logging import log_request
from app.main import unhandled_exception
celery_runtime = importlib.import_module("app.workers.celery_app")


class ObservabilityTests(unittest.TestCase):
    def test_json_formatter_includes_only_explicit_safe_fields(self) -> None:
        record = logging.LogRecord(
            name="aegis",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="http_request_completed",
            args=(),
            exc_info=None,
        )
        record.route = "/documents/{document_id}"
        record.status_code = 200
        record.access_token = "must-not-appear"

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["event"], "http_request_completed")
        self.assertEqual(payload["route"], "/documents/{document_id}")
        self.assertEqual(payload["status_code"], 200)
        self.assertNotIn("access_token", payload)

    def test_request_middleware_preserves_valid_correlation_id(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/health",
                "headers": [(b"x-request-id", b"incident-123")],
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
            }
        )

        async def successful_response(_: Request) -> Response:
            return Response(status_code=204)

        response = asyncio.run(log_request(request, successful_response))

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["X-Request-ID"], "incident-123")

    def test_readiness_reports_all_required_dependencies(self) -> None:
        session = MagicMock()
        redis_client = MagicMock()
        qdrant_response = MagicMock()
        http_client = MagicMock()
        http_client.get.return_value = qdrant_response
        http_client.__enter__.return_value = http_client

        with (
            patch.object(health_api, "SessionLocal", return_value=session),
            patch.object(health_api.Redis, "from_url", return_value=redis_client),
            patch.object(health_api.httpx, "Client", return_value=http_client),
        ):
            response = Response()
            payload = health_api.readiness(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(
            payload["dependencies"],
            {"database": "connected", "redis": "connected", "qdrant": "connected"},
        )
        session.close.assert_called_once()
        redis_client.ping.assert_called_once()
        qdrant_response.raise_for_status.assert_called_once()

    def test_readiness_returns_generic_failure_status(self) -> None:
        session = MagicMock()
        session.execute.side_effect = RuntimeError("database password is secret")
        redis_client = MagicMock()
        redis_client.ping.side_effect = RuntimeError("redis password is secret")
        http_client = MagicMock()
        http_client.__enter__.return_value = http_client
        http_client.get.side_effect = RuntimeError("qdrant token is secret")

        with (
            patch.object(health_api, "SessionLocal", return_value=session),
            patch.object(health_api.Redis, "from_url", return_value=redis_client),
            patch.object(health_api.httpx, "Client", return_value=http_client),
        ):
            response = Response()
            payload = health_api.readiness(response)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(
            payload["dependencies"],
            {"database": "unavailable", "redis": "unavailable", "qdrant": "unavailable"},
        )
        self.assertNotIn("secret", json.dumps(payload))

    def test_metrics_payload_contains_aegis_metrics(self) -> None:
        payload, content_type = metrics_response()

        self.assertIn("text/plain", content_type)
        self.assertIn(b"aegis_http_requests_total", payload)

    def test_worker_signal_records_only_task_name_and_outcome(self) -> None:
        task = MagicMock(name="task")
        task.name = "app.workers.tasks.process_document"

        with (
            patch.object(celery_runtime.logger, "info") as info,
            patch.object(celery_runtime.logger, "warning") as warning,
        ):
            celery_runtime.record_worker_success(sender=task, state="SUCCESS")
            celery_runtime.record_worker_failure(sender=task, exception=RuntimeError("token"))

        info.assert_called_once()
        warning.assert_called_once()
        self.assertNotIn("token", str(warning.call_args))

    def test_unhandled_exception_is_generic_to_the_client(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/unexpected",
                "headers": [],
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("testclient", 50000),
            }
        )

        with patch("app.main.logger.exception") as exception_log:
            response = asyncio.run(
                unhandled_exception(request, RuntimeError("access token must not escape"))
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            json.loads(response.body),
            {"detail": "AegisAI is temporarily unavailable"},
        )
        self.assertNotIn("access token", str(exception_log.call_args))


if __name__ == "__main__":
    unittest.main()
