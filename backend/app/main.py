from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from app.api.health import router as health_router
    from app.api.database import router as database_router
    from app.api.protected import router as protected_router
    from app.api.auth import router as auth_router
    from app.api.sso import router as sso_router
    from app.api.rbac import router as rbac_router
    from app.api.documents import router as documents_router
    from app.api.document_access_grants import router as document_access_grants_router
    from app.api.retrieval import router as retrieval_router
    from app.api.chat import router as chat_router
    from app.api.audit_events import router as audit_events_router
    from app.api.admin_users import router as admin_users_router
    from app.api.admin_rbac import router as admin_rbac_router
    from app.api.admin_documents import router as admin_documents_router
    from app.api.admin_processing_jobs import router as admin_processing_jobs_router
    from app.api.admin_overview import router as admin_overview_router
    from app.core.config import settings
    from app.core.logging import logger
    from app.core.request_logging import log_request
except ModuleNotFoundError as exc:
    if exc.name != "app":
        raise
    from api.health import router as health_router
    from api.database import router as database_router
    from app.api.protected import router as protected_router
    from app.api.auth import router as auth_router
    from app.api.sso import router as sso_router
    from app.api.rbac import router as rbac_router
    from app.api.documents import router as documents_router
    from app.api.document_access_grants import router as document_access_grants_router
    from app.api.retrieval import router as retrieval_router
    from app.api.chat import router as chat_router
    from app.api.audit_events import router as audit_events_router
    from app.api.admin_users import router as admin_users_router
    from app.api.admin_rbac import router as admin_rbac_router
    from app.api.admin_documents import router as admin_documents_router
    from app.api.admin_processing_jobs import router as admin_processing_jobs_router
    from app.api.admin_overview import router as admin_overview_router
    from core.config import settings
    from core.logging import logger
    from core.request_logging import log_request

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AegisAI...")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.middleware("http")(log_request)

@app.exception_handler(Exception)
async def unhandled_exception(request: Request, _: Exception):
    logger.exception(
        "unhandled_request_failure",
        extra={
            "method": request.method,
            "route": getattr(request.scope.get("route"), "path", "unmatched"),
            "failure_category": "unhandled",
        },
    )
    return JSONResponse(status_code=500, content={"detail": "AegisAI is temporarily unavailable"})

app.include_router(health_router)
app.include_router(database_router)
app.include_router(protected_router)
app.include_router(auth_router)
app.include_router(sso_router)
app.include_router(rbac_router)
app.include_router(documents_router)
app.include_router(document_access_grants_router)
app.include_router(retrieval_router)
app.include_router(chat_router)
app.include_router(audit_events_router)
app.include_router(admin_users_router)
app.include_router(admin_rbac_router)
app.include_router(admin_documents_router)
app.include_router(admin_processing_jobs_router)
app.include_router(admin_overview_router)

@app.get("/")
def root():

    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }
