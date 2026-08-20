"""Persistence operations for direct document-access grants."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_access_grant import DocumentAccessGrant


class DocumentAccessGrantRepository:
    """Database boundary without transaction ownership."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, grant: DocumentAccessGrant) -> DocumentAccessGrant:
        self.db.add(grant)
        self.db.flush()
        self.db.refresh(grant)
        return grant

    def get_by_document_and_user(
        self,
        *,
        document_id: int,
        user_id: int,
    ) -> DocumentAccessGrant | None:
        return self.db.scalar(
            select(DocumentAccessGrant).where(
                DocumentAccessGrant.document_id == document_id,
                DocumentAccessGrant.user_id == user_id,
            )
        )

    def list_by_document_id(self, document_id: int) -> list[DocumentAccessGrant]:
        return list(
            self.db.scalars(
                select(DocumentAccessGrant)
                .where(DocumentAccessGrant.document_id == document_id)
                .order_by(DocumentAccessGrant.user_id)
            )
        )

    def update(self) -> None:
        self.db.flush()

    def delete(self, grant: DocumentAccessGrant) -> None:
        self.db.delete(grant)
        self.db.flush()
