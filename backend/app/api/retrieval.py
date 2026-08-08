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
from app.services.query_embedding_service import QueryEmbeddingError
from app.services.retrieval_service import RetrievalService


router = APIRouter(prefix="/retrieval", tags=["Retrieval"])


@router.post(
    "/search",
    response_model=RetrievalSearchResponse,
    dependencies=[Depends(require_permission(PermissionCode.DOCUMENTS_READ))],
)
def search(
    request: RetrievalSearchRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> RetrievalSearchResponse:
    try:
        return service.search(request)
    except (QueryEmbeddingError, EmbeddingProviderError, VectorStoreError, SQLAlchemyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic retrieval is temporarily unavailable",
        ) from error
