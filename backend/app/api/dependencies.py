from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.auth_service import AuthService
from app.services.rbac_service import RbacService


def get_auth_service(
    db: Session = Depends(get_db),
) -> AuthService:
    return AuthService(db)


def get_rbac_service(
    db: Session = Depends(get_db),
) -> RbacService:
    return RbacService(db)
