from fastapi import Depends

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.integrations.sso.factory import SsoProviderFactory
from app.security.sso_transactions import SsoTransactionManager
from app.services.auth_service import AuthService
from app.services.rbac_service import RbacService
from app.services.sso_account_service import SsoAccountService


def get_auth_service(
    db: Session = Depends(get_db),
) -> AuthService:
    return AuthService(db)


def get_rbac_service(
    db: Session = Depends(get_db),
) -> RbacService:
    return RbacService(db)


def get_sso_account_service(
    db: Session = Depends(get_db),
) -> SsoAccountService:
    return SsoAccountService(db)


def get_sso_provider_factory() -> SsoProviderFactory:
    return SsoProviderFactory(settings)


def get_sso_transaction_manager() -> SsoTransactionManager:
    return SsoTransactionManager(
        secret_key=settings.SSO_STATE_SECRET_KEY,
        expires_in_minutes=settings.SSO_TRANSACTION_EXPIRE_MINUTES,
        secure_cookie=settings.SSO_CALLBACK_BASE_URL.startswith("https://"),
    )
