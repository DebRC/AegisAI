from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentPersistenceError
from app.core.exceptions import DocumentValidationError
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.storage.documents import DocumentStorage
from app.storage.documents import StoredDocument


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
            self._commit()
            return document
        except Exception as error:
            self.db.rollback()
            self._remove_stored_document(stored)
            raise DocumentPersistenceError() from error

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

    def _remove_stored_document(self, stored: StoredDocument) -> None:
        try:
            self.storage.delete(stored.storage_key)
        except Exception:
            # Database rollback prevents metadata visibility; cleanup remains best-effort.
            pass
