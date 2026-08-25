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
from app.api.dependencies import get_document_access_policy_service
from app.api.dependencies import get_document_extraction_query_service
from app.api.dependencies import get_document_embedding_status_service
from app.api.dependencies import get_processing_job_service
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentExtractionNotFoundError
from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentValidationError
from app.core.exceptions import ProcessingJobNotFoundError
from app.core.exceptions import ProcessingJobPersistenceError
from app.core.exceptions import ProcessingJobStateError
from app.api.document_access import require_document_read_access
from app.api.document_access import require_document_write_access
from app.models.user import User
from app.schemas.document import DocumentListResponse
from app.schemas.document import DocumentChunkListResponse
from app.schemas.document import DocumentExtractionResponse
from app.schemas.document import DocumentEmbeddingStatusResponse
from app.schemas.document import DocumentRenameRequest
from app.schemas.document import DocumentResponse
from app.schemas.document import ProcessingJobListResponse
from app.schemas.document import ProcessingJobResponse
from app.security.dependencies import require_permission
from app.security.permissions import PermissionCode
from app.services.document_service import DocumentService
from app.services.document_extraction_query_service import DocumentExtractionQueryService
from app.services.document_embedding_status_service import DocumentEmbeddingStatusService
from app.services.document_access_policy_service import DocumentAccessPolicyService
from app.services.processing_job_service import ProcessingJobService
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

    if isinstance(error, DocumentExtractionNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document extraction not found",
        )

    if isinstance(error, ProcessingJobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found")

    if isinstance(error, ProcessingJobStateError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document processing operation cannot be completed",
        )

    if isinstance(error, (DocumentPersistenceError, ProcessingJobPersistenceError, DocumentStorageError)):
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
)
def list_documents(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    current_user: User = Depends(require_permission(PermissionCode.DOCUMENTS_READ)),
    policy: DocumentAccessPolicyService = Depends(get_document_access_policy_service),
) -> DocumentListResponse:
    page = policy.list_readable_documents(
        user_id=current_user.id,
        offset=offset,
        limit=limit,
    )
    return DocumentListResponse(
        items=page.items,
        offset=offset,
        limit=limit,
        total=page.total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(require_document_read_access),
) -> DocumentResponse:
    try:
        return service.get_document(document_id, audit_actor_user_id=current_user.id)
    except DocumentNotFoundError as error:
        raise _document_error_to_http_exception(error) from error


@router.get(
    "/{document_id}/extraction",
    response_model=DocumentExtractionResponse,
)
def get_document_extraction(
    document_id: int,
    service: DocumentExtractionQueryService = Depends(get_document_extraction_query_service),
    _: User = Depends(require_document_read_access),
) -> DocumentExtractionResponse:
    try:
        return service.get_extraction(document_id)
    except (DocumentNotFoundError, DocumentExtractionNotFoundError) as error:
        raise _document_error_to_http_exception(error) from error


@router.get(
    "/{document_id}/indexing-status",
    response_model=DocumentEmbeddingStatusResponse,
)
def get_document_indexing_status(
    document_id: int,
    service: DocumentEmbeddingStatusService = Depends(get_document_embedding_status_service),
    _: User = Depends(require_document_read_access),
) -> DocumentEmbeddingStatusResponse:
    try:
        return service.get_status(document_id)
    except DocumentNotFoundError as error:
        raise _document_error_to_http_exception(error) from error


@router.get(
    "/{document_id}/extraction/chunks",
    response_model=DocumentChunkListResponse,
)
def list_document_chunks(
    document_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    service: DocumentExtractionQueryService = Depends(get_document_extraction_query_service),
    _: User = Depends(require_document_read_access),
) -> DocumentChunkListResponse:
    try:
        page = service.list_chunks(document_id=document_id, offset=offset, limit=limit)
        return DocumentChunkListResponse(
            items=page.items,
            offset=page.offset,
            limit=page.limit,
            total=page.total,
        )
    except (
        DocumentValidationError,
        DocumentNotFoundError,
        DocumentExtractionNotFoundError,
    ) as error:
        raise _document_error_to_http_exception(error) from error


@router.post(
    "/{document_id}/reprocess",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_document(
    document_id: int,
    service: DocumentExtractionQueryService = Depends(get_document_extraction_query_service),
    current_user: User = Depends(require_document_write_access),
) -> ProcessingJobResponse:
    try:
        return service.request_reprocessing(document_id, actor_user_id=current_user.id)
    except (
        DocumentNotFoundError,
        ProcessingJobPersistenceError,
        ProcessingJobStateError,
    ) as error:
        raise _document_error_to_http_exception(error) from error


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
)
def rename_document(
    document_id: int,
    request: DocumentRenameRequest,
    service: DocumentService = Depends(get_document_service),
    current_user: User = Depends(require_document_write_access),
) -> DocumentResponse:
    try:
        return service.rename_document(
            document_id,
            request.title,
            actor_user_id=current_user.id,
        )
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
    current_user: User = Depends(require_document_write_access),
) -> Response:
    try:
        service.delete_document(document_id, actor_user_id=current_user.id)
    except (DocumentNotFoundError, DocumentPersistenceError) as error:
        raise _document_error_to_http_exception(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{document_id}/processing-jobs",
    response_model=ProcessingJobListResponse,
)
def list_processing_jobs(
    document_id: int,
    service: ProcessingJobService = Depends(get_processing_job_service),
    _: User = Depends(require_document_read_access),
) -> ProcessingJobListResponse:
    try:
        return ProcessingJobListResponse(items=service.list_document_jobs(document_id))
    except DocumentNotFoundError as error:
        raise _document_error_to_http_exception(error) from error


@router.get(
    "/{document_id}/processing-jobs/{job_id}",
    response_model=ProcessingJobResponse,
)
def get_processing_job(
    document_id: int,
    job_id: int,
    service: ProcessingJobService = Depends(get_processing_job_service),
    _: User = Depends(require_document_read_access),
) -> ProcessingJobResponse:
    try:
        return service.get_document_job(document_id=document_id, job_id=job_id)
    except ProcessingJobNotFoundError as error:
        raise _document_error_to_http_exception(error) from error


@router.post(
    "/{document_id}/processing-jobs/{job_id}/retry",
    response_model=ProcessingJobResponse,
)
def retry_processing_job(
    document_id: int,
    job_id: int,
    service: ProcessingJobService = Depends(get_processing_job_service),
    _: User = Depends(require_document_write_access),
) -> ProcessingJobResponse:
    try:
        return service.retry_failed_job(document_id=document_id, job_id=job_id)
    except (
        ProcessingJobNotFoundError,
        ProcessingJobStateError,
        ProcessingJobPersistenceError,
    ) as error:
        raise _document_error_to_http_exception(error) from error
