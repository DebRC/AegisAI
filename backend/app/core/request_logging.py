"""Privacy-preserving HTTP request correlation and completion logging."""

from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

from app.core.logging import logger, request_id_context
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS

_REQUEST_ID_HEADER = "X-Request-ID"


async def log_request(request: Request, call_next) -> Response:
    request_id = request.headers.get(_REQUEST_ID_HEADER)
    if not request_id or len(request_id) > 128 or not request_id.replace("-", "").isalnum():
        request_id = str(uuid4())
    token = request_id_context.set(request_id)
    started = perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        status_code = locals().get("response", None)
        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "route": route_template,
                "status_code": getattr(status_code, "status_code", 500),
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        status = getattr(status_code, "status_code", 500)
        HTTP_REQUESTS.labels(request.method, route_template, f"{status // 100}xx").inc()
        HTTP_DURATION.labels(request.method, route_template).observe(perf_counter() - started)
        request_id_context.reset(token)
        if "response" in locals():
            response.headers[_REQUEST_ID_HEADER] = request_id
