from collections.abc import Iterator

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Response
from fastapi import UploadFile
from fastapi import status

from app.api.dependencies import get_document_service
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentValidationError
from app.models.user import User
from app.schemas.document import DocumentListResponse
from app.schemas.document import DocumentRenameRequest
from app.schemas.document import DocumentResponse
from app.security.dependencies import require_permission
from app.security.permissions import PermissionCode
from app.services.document_service import DocumentService
from app.storage.documents import DocumentStorageError
from app.storage.documents import EmptyDocumentError
from app.storage.documents import StorageLimitExceededError


router = APIRouter(prefix="/documents", tags=["Documents"])

_UPLOAD_CHUNK_SIZE = 64 * 1024


def _document_error_to_http_exception(error: Exception) -> HTTPException:
    if isinstance(
        error,
        (DocumentValidationError, EmptyDocumentError, StorageLimitExceededError),
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid document upload",
        )

    if isinstance(error, DocumentNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if isinstance(error, (DocumentPersistenceError, DocumentStorageError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable",
        )

    raise error


def _file_chunks(file: UploadFile) -> Iterator[bytes]:
    """Read the spooled multipart upload in bounded synchronous chunks."""
    while chunk := file.file.read(_UPLOAD_CHUNK_SIZE):
        yield chunk


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(PermissionCode.DOCUMENTS_WRITE)),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    try:
        return service.upload(
            uploader_user_id=current_user.id,
            original_filename=file.filename or "",
            content_type=file.content_type or "",
            chunks=_file_chunks(file),
        )
    except (
        DocumentValidationError,
        EmptyDocumentError,
        StorageLimitExceededError,
        DocumentPersistenceError,
        DocumentStorageError,
    ) as error:
        raise _document_error_to_http_exception(error) from error


@router.get(
    "",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_permission(PermissionCode.DOCUMENTS_READ))],
)
def list_documents(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    page = service.list_documents(offset=offset, limit=limit)
    return DocumentListResponse(
        items=page.items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    dependencies=[Depends(require_permission(PermissionCode.DOCUMENTS_READ))],
)
def get_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    try:
        return service.get_document(document_id)
    except DocumentNotFoundError as error:
        raise _document_error_to_http_exception(error) from error


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
)
def rename_document(
    document_id: int,
    request: DocumentRenameRequest,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(require_permission(PermissionCode.DOCUMENTS_WRITE)),
) -> DocumentResponse:
    try:
        return service.rename_document(document_id, request.title)
    except (
        DocumentValidationError,
        DocumentNotFoundError,
        DocumentPersistenceError,
    ) as error:
        raise _document_error_to_http_exception(error) from error


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
    _: User = Depends(require_permission(PermissionCode.DOCUMENTS_WRITE)),
) -> Response:
    try:
        service.delete_document(document_id)
    except (DocumentNotFoundError, DocumentPersistenceError) as error:
        raise _document_error_to_http_exception(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
