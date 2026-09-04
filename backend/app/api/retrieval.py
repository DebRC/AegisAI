from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_retrieval_service
from app.embeddings.exceptions import EmbeddingProviderError
from app.integrations.vector_store.exceptions import VectorStoreError
from app.schemas.retrieval import RetrievalSearchRequest
from app.schemas.retrieval import RetrievalSearchResponse
from app.security.permissions import PermissionCode
from app.security.dependencies import require_permission
from app.security.dependencies import TenantContext, get_current_tenant_context
from app.models.user import User
from app.services.query_embedding_service import QueryEmbeddingError
from app.services.retrieval_service import RetrievalService


router = APIRouter(prefix="/retrieval", tags=["Retrieval"])


@router.post(
    "/search",
    response_model=RetrievalSearchResponse,
)
def search(
    request: RetrievalSearchRequest,
    current_user: User = Depends(require_permission(PermissionCode.DOCUMENTS_READ)),
    service: RetrievalService = Depends(get_retrieval_service),
    context: TenantContext | None = Depends(get_current_tenant_context),
) -> RetrievalSearchResponse:
    try:
        tenant_id = getattr(getattr(context, "tenant", None), "id", None)
        if tenant_id is None:
            return service.search(request, user_id=current_user.id)
        return service.search(request, user_id=current_user.id, tenant_id=tenant_id)
    except (QueryEmbeddingError, EmbeddingProviderError, VectorStoreError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic retrieval is temporarily unavailable",
        ) from error
