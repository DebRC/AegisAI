"""Global, read-only document lifecycle views for administrators."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentNotFoundError
from app.models.document import Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository


@dataclass(frozen=True)
class AdminDocumentPage:
    items: list[Document]
    offset: int
    limit: int
    total: int


class AdminDocumentService:
    def __init__(self, db: Session):
        self.documents = DocumentRepository(db)

    def list_documents(self, *, offset: int, limit: int, status: DocumentStatus | None, uploader_user_id: int | None, tenant_id: int | None = None) -> AdminDocumentPage:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid offset")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Invalid limit")
        if uploader_user_id is not None and (not isinstance(uploader_user_id, int) or uploader_user_id <= 0):
            raise ValueError("Invalid uploader filter")
        status_value = status.value if status else None
        return AdminDocumentPage(
            items=self.documents.list_for_administration(offset=offset, limit=limit, status=status_value, uploader_user_id=uploader_user_id, tenant_id=tenant_id),
            offset=offset, limit=limit,
            total=self.documents.count_for_administration(status=status_value, uploader_user_id=uploader_user_id, tenant_id=tenant_id),
        )

    def get_document(self, document_id: int, *, tenant_id: int | None = None) -> Document:
        document = self.documents.get_active_by_id(document_id, tenant_id=tenant_id) if tenant_id is not None else self.documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document
