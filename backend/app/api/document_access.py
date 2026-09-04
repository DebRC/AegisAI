"""FastAPI dependencies for document-resource authorization."""

from collections.abc import Callable

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from app.api.dependencies import get_document_access_policy_service
from app.models.user import User
from app.security.dependencies import require_permission
from app.security.dependencies import TenantContext
from app.security.dependencies import get_current_tenant_context
from app.security.permissions import PermissionCode
from app.services.document_access_policy_service import DocumentAccessPolicyService


def require_document_access(
    permission: PermissionCode,
    *,
    write: bool,
) -> Callable[..., User]:
    """Require global capability, then hide a denied document as not found."""

    def dependency(
        document_id: int,
        current_user: User = Depends(require_permission(permission)),
        policy: DocumentAccessPolicyService = Depends(get_document_access_policy_service),
        context: TenantContext | None = Depends(get_current_tenant_context),
    ) -> User:
        tenant_id = getattr(getattr(context, "tenant", None), "id", None)
        if tenant_id is None:
            allowed = policy.can_write(user_id=current_user.id, document_id=document_id) if write else policy.can_read(user_id=current_user.id, document_id=document_id)
        else:
            allowed = policy.can_write(user_id=current_user.id, document_id=document_id, tenant_id=tenant_id) if write else policy.can_read(user_id=current_user.id, document_id=document_id, tenant_id=tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return current_user

    return dependency


require_document_read_access = require_document_access(
    PermissionCode.DOCUMENTS_READ,
    write=False,
)
require_document_write_access = require_document_access(
    PermissionCode.DOCUMENTS_WRITE,
    write=True,
)
