"""Resource-level document policy reused by APIs, retrieval, and chat."""

from collections.abc import Iterable

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_access_grant import DocumentAccessGrant
from app.models.document_access_grant import DocumentAccessLevel
from app.models.user import User
from app.repositories.permission_repository import PermissionRepository
from app.security.permissions import PermissionCode


class DocumentAccessPolicyService:
    """Answer document-resource access decisions without HTTP concerns."""

    def __init__(self, db: Session):
        self.db = db
        self.permissions = PermissionRepository(db)

    def can_read(self, *, user_id: int, document_id: int) -> bool:
        return document_id in self.readable_document_ids(
            user_id=user_id,
            document_ids=[document_id],
        )

    def can_write(self, *, user_id: int, document_id: int) -> bool:
        return document_id in self.writable_document_ids(
            user_id=user_id,
            document_ids=[document_id],
        )

    def readable_document_ids(
        self,
        *,
        user_id: int,
        document_ids: Iterable[int],
    ) -> set[int]:
        return self._accessible_document_ids(
            user_id=user_id,
            document_ids=document_ids,
            grant_levels=(DocumentAccessLevel.READ, DocumentAccessLevel.WRITE),
        )

    def writable_document_ids(
        self,
        *,
        user_id: int,
        document_ids: Iterable[int],
    ) -> set[int]:
        return self._accessible_document_ids(
            user_id=user_id,
            document_ids=document_ids,
            grant_levels=(DocumentAccessLevel.WRITE,),
        )

    def _accessible_document_ids(
        self,
        *,
        user_id: int,
        document_ids: Iterable[int],
        grant_levels: tuple[DocumentAccessLevel, ...],
    ) -> set[int]:
        ids = {
            document_id
            for document_id in document_ids
            if isinstance(document_id, int) and document_id > 0
        }
        if not ids or not self._is_active_user(user_id):
            return set()

        statement = select(Document.id).where(
            Document.id.in_(ids),
            Document.deleted_at.is_(None),
        )
        if not self.permissions.user_has_permission(
            user_id,
            PermissionCode.DOCUMENTS_MANAGE.value,
        ):
            statement = (
                statement.outerjoin(
                    DocumentAccessGrant,
                    and_(
                        DocumentAccessGrant.document_id == Document.id,
                        DocumentAccessGrant.user_id == user_id,
                    ),
                )
                .where(
                    or_(
                        Document.uploader_user_id == user_id,
                        DocumentAccessGrant.access_level.in_(grant_levels),
                    )
                )
            )

        return set(self.db.scalars(statement))

    def _is_active_user(self, user_id: int) -> bool:
        if not isinstance(user_id, int) or user_id <= 0:
            return False
        return self.db.scalar(
            select(User.is_active).where(User.id == user_id)
        ) is True
