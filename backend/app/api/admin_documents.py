from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_admin_document_service
from app.core.exceptions import DocumentNotFoundError
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.admin import AdminDocumentListResponse, AdminDocumentResponse
from app.security.dependencies import require_administration_permission
from app.security.permissions import PermissionCode
from app.services.admin_document_service import AdminDocumentService

router = APIRouter(prefix="/admin/documents", tags=["Administration"])

def _response(document: Document) -> AdminDocumentResponse:
    return AdminDocumentResponse.model_validate(document)

@router.get("", response_model=AdminDocumentListResponse)
def list_documents(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), status_filter: DocumentStatus | None = Query(None, alias="status"), uploader_user_id: int | None = Query(None, ge=1), service: AdminDocumentService = Depends(get_admin_document_service), _: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE))) -> AdminDocumentListResponse:
    page = service.list_documents(offset=offset, limit=limit, status=status_filter, uploader_user_id=uploader_user_id)
    return AdminDocumentListResponse(items=[_response(item) for item in page.items], offset=page.offset, limit=page.limit, total=page.total)

@router.get("/{document_id}", response_model=AdminDocumentResponse)
def get_document(document_id: int, service: AdminDocumentService = Depends(get_admin_document_service), _: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE))) -> AdminDocumentResponse:
    try:
        return _response(service.get_document(document_id))
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from error
