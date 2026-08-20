"""Resource-level document policy reused by APIs, retrieval, and chat."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_access_grant import DocumentAccessGrant
from app.models.document_access_grant import DocumentAccessLevel
from app.models.user import User
from app.repositories.permission_repository import PermissionRepository
from app.security.permissions import PermissionCode


@dataclass(frozen=True)
class AccessibleDocumentPage:
    """One paginated page whose rows have already passed resource policy."""

    items: list[Document]
    total: int


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

    def list_readable_documents(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
    ) -> AccessibleDocumentPage:
        """Page active documents without exposing inaccessible rows or totals."""
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 0
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 100
            or not self._is_active_user(user_id)
        ):
            return AccessibleDocumentPage(items=[], total=0)

        statement = self._accessible_documents_statement(
            user_id=user_id,
            grant_levels=(DocumentAccessLevel.READ, DocumentAccessLevel.WRITE),
        )
        total = self.db.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ) or 0
        return AccessibleDocumentPage(
            items=list(
                self.db.scalars(
                    statement.order_by(Document.created_at.desc(), Document.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ),
            total=total,
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

        statement = self._accessible_documents_statement(
            user_id=user_id,
            grant_levels=grant_levels,
        ).where(Document.id.in_(ids))
        return set(self.db.scalars(statement.with_only_columns(Document.id)))

    def _accessible_documents_statement(
        self,
        *,
        user_id: int,
        grant_levels: tuple[DocumentAccessLevel, ...],
    ):
        statement = select(Document).where(Document.deleted_at.is_(None))
        if self.permissions.user_has_permission(
            user_id,
            PermissionCode.DOCUMENTS_MANAGE.value,
        ):
            return statement
        return (
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

    def _is_active_user(self, user_id: int) -> bool:
        if not isinstance(user_id, int) or user_id <= 0:
            return False
        return self.db.scalar(
            select(User.is_active).where(User.id == user_id)
        ) is True
