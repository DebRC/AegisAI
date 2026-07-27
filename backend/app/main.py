from fastapi import FastAPI

try:
    from app.api.health import router as health_router
    from app.api.database import router as database_router
    from app.api.protected import router as protected_router
    from app.api.auth import router as auth_router
    from app.core.config import settings
    from app.core.logging import logger
except ModuleNotFoundError as exc:
    if exc.name != "app":
        raise
    from api.health import router as health_router
    from api.database import router as database_router
    from app.api.protected import router as protected_router
    from app.api.auth import router as auth_router
    from core.config import settings
    from core.logging import logger

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
)

app.include_router(health_router)
app.include_router(database_router)
app.include_router(protected_router)
app.include_router(auth_router)

@app.on_event("startup")
def startup():

    logger.info("Starting AegisAI...")


@app.get("/")
def root():

    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }
