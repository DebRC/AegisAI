"""Transactional management of direct document-access grants."""

from sqlalchemy.orm import Session

from app.core.exceptions import DocumentAccessGranteeInactiveError
from app.core.exceptions import DocumentAccessGrantNotFoundError
from app.core.exceptions import DocumentAccessOwnerGrantError
from app.core.exceptions import DocumentNotFoundError
from app.core.exceptions import UserNotFoundError
from app.models.document_access_grant import DocumentAccessGrant
from app.models.document_access_grant import DocumentAccessLevel
from app.repositories.document_access_grant_repository import DocumentAccessGrantRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.document_access_policy_service import DocumentAccessPolicyService


class DocumentAccessGrantService:
    """Manage grants only after the caller has document-level write access."""

    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.grants = DocumentAccessGrantRepository(db)
        self.users = UserRepository(db)
        self.access_policy = DocumentAccessPolicyService(db)

    def list_grants(self, *, actor_user_id: int, document_id: int) -> list[DocumentAccessGrant]:
        self._require_manage_access(actor_user_id=actor_user_id, document_id=document_id)
        return self.grants.list_by_document_id(document_id)

    def upsert_grant(
        self,
        *,
        actor_user_id: int,
        document_id: int,
        grantee_user_id: int,
        access_level: DocumentAccessLevel,
    ) -> DocumentAccessGrant:
        document = self._locked_manageable_document(
            actor_user_id=actor_user_id,
            document_id=document_id,
        )
        grantee = self.users.get_by_id(grantee_user_id)
        if grantee is None:
            raise UserNotFoundError()
        if not grantee.is_active:
            raise DocumentAccessGranteeInactiveError()
        if grantee.id == document.uploader_user_id:
            raise DocumentAccessOwnerGrantError()

        grant = self.grants.get_by_document_and_user(
            document_id=document_id,
            user_id=grantee_user_id,
        )
        if grant is None:
            grant = self.grants.create(
                DocumentAccessGrant(
                    document_id=document_id,
                    user_id=grantee_user_id,
                    access_level=access_level,
                    granted_by_user_id=actor_user_id,
                )
            )
        else:
            grant.access_level = access_level
            grant.granted_by_user_id = actor_user_id
            self.grants.update()
        self._commit()
        return grant

    def revoke_grant(
        self,
        *,
        actor_user_id: int,
        document_id: int,
        grantee_user_id: int,
    ) -> None:
        self._locked_manageable_document(
            actor_user_id=actor_user_id,
            document_id=document_id,
        )
        grant = self.grants.get_by_document_and_user(
            document_id=document_id,
            user_id=grantee_user_id,
        )
        if grant is None:
            raise DocumentAccessGrantNotFoundError()
        self.grants.delete(grant)
        self._commit()

    def _require_manage_access(self, *, actor_user_id: int, document_id: int) -> None:
        if not self.access_policy.can_write(user_id=actor_user_id, document_id=document_id):
            raise DocumentNotFoundError()

    def _locked_manageable_document(self, *, actor_user_id: int, document_id: int):
        self._require_manage_access(actor_user_id=actor_user_id, document_id=document_id)
        document = self.documents.get_active_by_id_for_update(document_id)
        if document is None:
            raise DocumentNotFoundError()
        return document

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
