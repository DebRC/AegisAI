from fastapi import APIRouter
from sqlalchemy import text

from app.db.database import SessionLocal

router = APIRouter(
    prefix="/database",
    tags=["Database"],
)


@router.get("/health")
def database_health():

    db = SessionLocal()

    try:

        db.execute(text("SELECT 1"))

        return {
            "database": "connected"
        }

    finally:

        db.close()