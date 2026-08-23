"""HTTP API for direct, document-specific user sharing."""

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Response
from fastapi import status

from app.api.dependencies import get_document_access_grant_service
from app.api.document_access import require_document_write_access
from app.core.exceptions import DocumentAccessGranteeInactiveError
from app.core.exceptions import DocumentAccessGrantNotFoundError
from app.core.exceptions import DocumentAccessOwnerGrantError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import UserNotFoundError
from app.models.user import User
from app.schemas.document import DocumentAccessGrantRequest
from app.schemas.document import DocumentAccessGrantResponse
from app.services.document_access_grant_service import DocumentAccessGrantService


router = APIRouter(prefix="/documents", tags=["Document access"])


def _error_to_http_exception(error: Exception) -> HTTPException:
    if isinstance(error, DocumentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if isinstance(error, DocumentAccessGrantNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document access grant not found")
    if isinstance(error, UserNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if isinstance(error, DocumentAccessGranteeInactiveError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Grant target must be an active user")
    if isinstance(error, DocumentAccessOwnerGrantError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Document owner access is implicit")
    raise error


@router.get("/{document_id}/access", response_model=list[DocumentAccessGrantResponse])
def list_document_access_grants(
    document_id: int,
    current_user: User = Depends(require_document_write_access),
    service: DocumentAccessGrantService = Depends(get_document_access_grant_service),
) -> list[DocumentAccessGrantResponse]:
    try:
        return service.list_grants(actor_user_id=current_user.id, document_id=document_id)
    except DocumentNotFoundError as error:
        raise _error_to_http_exception(error) from error


@router.put("/{document_id}/access/{user_id}", response_model=DocumentAccessGrantResponse)
def upsert_document_access_grant(
    document_id: int,
    user_id: int,
    request: DocumentAccessGrantRequest,
    current_user: User = Depends(require_document_write_access),
    service: DocumentAccessGrantService = Depends(get_document_access_grant_service),
) -> DocumentAccessGrantResponse:
    try:
        return service.upsert_grant(
            actor_user_id=current_user.id,
            document_id=document_id,
            grantee_user_id=user_id,
            access_level=request.access_level,
        )
    except (
        DocumentNotFoundError,
        DocumentAccessGranteeInactiveError,
        DocumentAccessOwnerGrantError,
        UserNotFoundError,
    ) as error:
        raise _error_to_http_exception(error) from error


@router.delete("/{document_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_document_access_grant(
    document_id: int,
    user_id: int,
    current_user: User = Depends(require_document_write_access),
    service: DocumentAccessGrantService = Depends(get_document_access_grant_service),
) -> Response:
    try:
        service.revoke_grant(
            actor_user_id=current_user.id,
            document_id=document_id,
            grantee_user_id=user_id,
        )
    except (DocumentNotFoundError, DocumentAccessGrantNotFoundError) as error:
        raise _error_to_http_exception(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
