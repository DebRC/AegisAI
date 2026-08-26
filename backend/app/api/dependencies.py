from fastapi import Depends

from sqlalchemy.orm import Session

from app.chat.citations import CitationValidator
from app.chat.factory import create_chat_model_provider
from app.chat.prompting import GroundedPromptBuilder
from app.core.config import settings
from app.db.database import get_db
from app.embeddings.factory import create_embedding_provider
from app.integrations.vector_store.qdrant_client import create_qdrant_client
from app.integrations.vector_store.qdrant_store import QdrantVectorStore
from app.integrations.sso.factory import SsoProviderFactory
from app.security.sso_transactions import SsoTransactionManager
from app.services.auth_service import AuthService
from app.services.admin_user_service import AdminUserService
from app.services.admin_rbac_service import AdminRbacService
from app.services.admin_document_service import AdminDocumentService
from app.services.admin_processing_job_service import AdminProcessingJobService
from app.services.audit_event_service import AuditEventService
from app.services.audit_query_service import AuditQueryService
from app.services.document_service import DocumentService
from app.services.document_access_policy_service import DocumentAccessPolicyService
from app.services.document_access_grant_service import DocumentAccessGrantService
from app.services.document_extraction_query_service import DocumentExtractionQueryService
from app.services.document_embedding_status_service import DocumentEmbeddingStatusService
from app.services.processing_job_service import ProcessingJobService
from app.services.query_embedding_service import QueryEmbeddingService
from app.services.rbac_service import RbacService
from app.services.retrieval_authority_service import RetrievalAuthorityService
from app.services.retrieval_service import RetrievalService
from app.services.rag_chat_service import RagChatService
from app.services.sso_account_service import SsoAccountService
from app.storage.documents import DocumentStorage
from app.storage.documents import LocalDocumentStorage


def get_auth_service(
    db: Session = Depends(get_db),
) -> AuthService:
    return AuthService(db)


def get_admin_user_service(
    db: Session = Depends(get_db),
) -> AdminUserService:
    return AdminUserService(db)


def get_admin_rbac_service(
    db: Session = Depends(get_db),
) -> AdminRbacService:
    return AdminRbacService(db)

def get_admin_document_service(db: Session = Depends(get_db)) -> AdminDocumentService:
    return AdminDocumentService(db)

def get_admin_processing_job_service(db: Session = Depends(get_db)) -> AdminProcessingJobService:
    return AdminProcessingJobService(db)


def get_rbac_service(
    db: Session = Depends(get_db),
) -> RbacService:
    return RbacService(db)


def get_audit_event_service(
    db: Session = Depends(get_db),
) -> AuditEventService:
    return AuditEventService(db)


def get_audit_query_service(
    db: Session = Depends(get_db),
) -> AuditQueryService:
    return AuditQueryService(db)


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


def get_document_access_policy_service(
    db: Session = Depends(get_db),
) -> DocumentAccessPolicyService:
    return DocumentAccessPolicyService(db)


def get_document_access_grant_service(
    db: Session = Depends(get_db),
) -> DocumentAccessGrantService:
    return DocumentAccessGrantService(db)


def get_document_extraction_query_service(
    db: Session = Depends(get_db),
) -> DocumentExtractionQueryService:
    return DocumentExtractionQueryService(db)


def get_document_embedding_status_service(
    db: Session = Depends(get_db),
) -> DocumentEmbeddingStatusService:
    return DocumentEmbeddingStatusService(db, settings)


def get_processing_job_service(
    db: Session = Depends(get_db),
) -> ProcessingJobService:
    return ProcessingJobService(db)


def get_query_embedding_service() -> QueryEmbeddingService:
    return QueryEmbeddingService(
        settings,
        lambda: create_embedding_provider(settings),
    )


def get_retrieval_authority_service(
    db: Session = Depends(get_db),
) -> RetrievalAuthorityService:
    return RetrievalAuthorityService(db, settings)


def get_retrieval_service(
    query_embeddings: QueryEmbeddingService = Depends(get_query_embedding_service),
    authority: RetrievalAuthorityService = Depends(get_retrieval_authority_service),
    audit_events: AuditEventService = Depends(get_audit_event_service),
) -> RetrievalService:
    def create_vector_store() -> QdrantVectorStore:
        return QdrantVectorStore(create_qdrant_client(settings), settings)

    return RetrievalService(query_embeddings, authority, create_vector_store, audit_events)


def get_rag_chat_service(
    retrieval: RetrievalService = Depends(get_retrieval_service),
    audit_events: AuditEventService = Depends(get_audit_event_service),
) -> RagChatService:
    """Build one request-scoped RAG service and its closable chat provider."""
    return RagChatService(
        retrieval=retrieval,
        prompt_builder=GroundedPromptBuilder(settings.CHAT_MAX_CONTEXT_CHARACTERS),
        chat_provider=create_chat_model_provider(settings),
        citation_validator=CitationValidator(),
        audit_events=audit_events,
    )


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
