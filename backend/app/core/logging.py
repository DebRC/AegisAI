import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Serialize only explicitly supplied, safe fields into one log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "service": "aegisai",
            "event": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in ("method", "route", "status_code", "duration_ms", "task_name", "failure_category"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), default=str)

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger("aegis")
for handler in logging.getLogger().handlers:
    handler.setFormatter(JsonFormatter())
