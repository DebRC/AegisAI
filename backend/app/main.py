from contextlib import asynccontextmanager

from fastapi import FastAPI

try:
    from app.api.health import router as health_router
    from app.api.database import router as database_router
    from app.api.protected import router as protected_router
    from app.api.auth import router as auth_router
    from app.api.sso import router as sso_router
    from app.api.rbac import router as rbac_router
    from app.api.documents import router as documents_router
    from app.api.retrieval import router as retrieval_router
    from app.core.config import settings
    from app.core.logging import logger
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
    from app.api.retrieval import router as retrieval_router
    from core.config import settings
    from core.logging import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AegisAI...")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(database_router)
app.include_router(protected_router)
app.include_router(auth_router)
app.include_router(sso_router)
app.include_router(rbac_router)
app.include_router(documents_router)
app.include_router(retrieval_router)

@app.get("/")
def root():

    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }
