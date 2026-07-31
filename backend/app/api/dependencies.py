from fastapi import Depends

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.integrations.sso.factory import SsoProviderFactory
from app.security.sso_transactions import SsoTransactionManager
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.rbac_service import RbacService
from app.services.sso_account_service import SsoAccountService
from app.storage.documents import DocumentStorage
from app.storage.documents import LocalDocumentStorage


def get_auth_service(
    db: Session = Depends(get_db),
) -> AuthService:
    return AuthService(db)


def get_rbac_service(
    db: Session = Depends(get_db),
) -> RbacService:
    return RbacService(db)


def get_document_storage() -> DocumentStorage:
    return LocalDocumentStorage(
        settings.DOCUMENT_STORAGE_PATH,
        settings.DOCUMENT_MAX_UPLOAD_BYTES,
    )


def get_document_service(
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_document_storage),
) -> DocumentService:
    return DocumentService(db, storage)


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
