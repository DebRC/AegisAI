from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    """Database boundary for document metadata without transaction ownership."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.flush()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self.db.scalar(
            select(Document).where(Document.id == document_id)
        )

    def get_active_by_id(self, document_id: int) -> Document | None:
        return self.db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )

    def get_active_by_id_for_update(self, document_id: int) -> Document | None:
        """Lock an active document while changing its processing lifecycle."""
        return self.db.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
            .with_for_update()
        )

    def list_active(self, *, offset: int, limit: int) -> list[Document]:
        return list(
            self.db.scalars(
                select(Document)
                .where(Document.deleted_at.is_(None))
                .order_by(Document.created_at.desc(), Document.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def count_active(self) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.deleted_at.is_(None))
        ) or 0

    def update(self) -> None:
        self.db.flush()
