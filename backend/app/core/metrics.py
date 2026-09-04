"""Low-cardinality Prometheus metrics for AegisAI operations."""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

HTTP_REQUESTS = Counter(
    "aegis_http_requests_total",
    "Completed HTTP requests",
    ["method", "route", "status_class"],
)
HTTP_DURATION = Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "route"],
)

def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
