import httpx
from fastapi import APIRouter, Response
from redis import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal
from app.core.metrics import metrics_response

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
def health():
    return {
        "status": "healthy"
    }

@router.get("/ready")
def readiness(response: Response):
    dependencies = {
        "database": "connected",
        "redis": "connected",
        "qdrant": "connected",
    }

    database_session = SessionLocal()
    try:
        database_session.execute(text("SELECT 1"))
    except Exception:
        dependencies["database"] = "unavailable"
    finally:
        database_session.close()

    try:
        Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=settings.OBSERVABILITY_DEPENDENCY_TIMEOUT_SECONDS,
            socket_timeout=settings.OBSERVABILITY_DEPENDENCY_TIMEOUT_SECONDS,
        ).ping()
    except Exception:
        dependencies["redis"] = "unavailable"

    try:
        with httpx.Client(timeout=settings.OBSERVABILITY_DEPENDENCY_TIMEOUT_SECONDS) as client:
            client.get(f"{settings.QDRANT_URL}/healthz").raise_for_status()
    except Exception:
        dependencies["qdrant"] = "unavailable"

    if any(status != "connected" for status in dependencies.values()):
        response.status_code = 503
        return {"status": "not_ready", "dependencies": dependencies}
    return {"status": "ready", "dependencies": dependencies}

@router.get("/metrics", include_in_schema=False)
def metrics():
    payload, content_type = metrics_response()
    return Response(content=payload, media_type=content_type)
