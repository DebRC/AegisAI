from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import DocumentValidationError
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_extraction_repository import DocumentExtractionRepository
from app.services.processing_job_service import ProcessingJobService
from app.storage.documents import DocumentStorage
from app.storage.documents import StoredDocument


@dataclass(frozen=True)
class DocumentPage:
    """One bounded page of active document metadata."""

    items: list[Document]
    offset: int
    limit: int
    total: int


class DocumentService:
    """Coordinate document storage and metadata persistence with cleanup."""

    _ALLOWED_CONTENT_TYPES = {
        ".pdf": {"application/pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        },
        ".txt": {"text/plain"},
        ".md": {"text/markdown", "text/plain"},
        ".markdown": {"text/markdown", "text/plain"},
    }

    def __init__(self, db: Session, storage: DocumentStorage):
        self.db = db
        self.documents = DocumentRepository(db)
        self.extractions = DocumentExtractionRepository(db)
        self.processing_jobs = ProcessingJobService(db)
        self.storage = storage

    def upload(
        self,
        *,
        uploader_user_id: int,
        original_filename: str,
        content_type: str,
        chunks: Iterable[bytes],
    ) -> Document:
        """Store a valid original document and commit its matching metadata."""
        filename, normalized_content_type, title = self._validate_metadata(
            uploader_user_id=uploader_user_id,
            original_filename=original_filename,
            content_type=content_type,
        )
        stored = self.storage.store(chunks)

        try:
            document = self.documents.create(
                Document(
                    uploader_user_id=uploader_user_id,
                    title=title,
                    original_filename=filename,
                    content_type=normalized_content_type,
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    storage_key=stored.storage_key,
                )
            )
            self.processing_jobs.create_source_integrity_job(document_id=document.id)
            self._commit()
            return document
        except Exception as error:
            self.db.rollback()
            self._remove_stored_document(stored)
            raise DocumentPersistenceError() from error

    def list_documents(self, *, offset: int, limit: int) -> DocumentPage:
        """Return a bounded page of non-deleted document metadata."""
        if not isinstance(offset, int) or offset < 0:
            raise DocumentValidationError()
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise DocumentValidationError()

        return DocumentPage(
            items=self.documents.list_active(offset=offset, limit=limit),
            offset=offset,
            limit=limit,
            total=self.documents.count_active(),
        )

    def get_document(self, document_id: int) -> Document:
        """Return non-deleted metadata or hide deleted records as not found."""
        document = self.documents.get_active_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document

    def rename_document(self, document_id: int, title: str) -> Document:
        """Change only an active document's display title."""
        normalized_title = self._validate_title(title)
        document = self.get_document(document_id)
        document.title = normalized_title

        try:
            self.documents.update()
            self._commit()
            return document
        except Exception as error:
            self.db.rollback()
            raise DocumentPersistenceError() from error

    def delete_document(self, document_id: int) -> None:
        """Soft-delete metadata, then make a best-effort object cleanup attempt."""
        document = self.get_document(document_id)

        try:
            self.processing_jobs.cancel_document_jobs(document_id=document.id)
            self.extractions.delete_by_document_id(document.id)
            document.deleted_at = datetime.now(timezone.utc)
            self.documents.update()
            self._commit()
        except Exception as error:
            self.db.rollback()
            raise DocumentPersistenceError() from error

        self._remove_stored_document(document.storage_key)

    def _commit(self) -> None:
        self.db.commit()

    @classmethod
    def _validate_metadata(
        cls,
        *,
        uploader_user_id: int,
        original_filename: str,
        content_type: str,
    ) -> tuple[str, str, str]:
        if not isinstance(uploader_user_id, int) or uploader_user_id <= 0:
            raise DocumentValidationError()
        if not isinstance(original_filename, str) or "\x00" in original_filename:
            raise DocumentValidationError()
        if not isinstance(content_type, str):
            raise DocumentValidationError()

        filename = original_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        extension = Path(filename).suffix.lower()
        normalized_content_type = content_type.partition(";")[0].strip().lower()
        allowed_content_types = cls._ALLOWED_CONTENT_TYPES.get(extension)
        title = Path(filename).stem.strip()

        if (
            not filename
            or len(filename) > 255
            or not title
            or len(title) > 255
            or allowed_content_types is None
            or normalized_content_type not in allowed_content_types
        ):
            raise DocumentValidationError()

        return filename, normalized_content_type, title

    @staticmethod
    def _validate_title(title: str) -> str:
        if not isinstance(title, str):
            raise DocumentValidationError()

        normalized_title = title.strip()
        if not normalized_title or len(normalized_title) > 255:
            raise DocumentValidationError()
        return normalized_title

    def _remove_stored_document(self, stored: StoredDocument | str) -> None:
        storage_key = stored.storage_key if isinstance(stored, StoredDocument) else stored
        try:
            self.storage.delete(storage_key)
        except Exception:
            # Database rollback prevents metadata visibility; cleanup remains best-effort.
            pass
