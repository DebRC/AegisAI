"""Organization governance controls unavailable to machine credentials."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_api_key_service, get_retention_service
from app.core.exceptions import ApiKeyValidationError, RetentionPolicyValidationError
from app.models.user import User
from app.schemas.governance import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
    RetentionPurgeResponse,
)
from app.security.dependencies import TenantContext, get_current_tenant_context, require_permission
from app.security.permissions import PermissionCode
from app.services.api_key_service import ApiKeyService
from app.services.retention_service import RetentionService


router = APIRouter(prefix="/governance", tags=["Enterprise governance"])


def _human_context(context: TenantContext) -> TenantContext:
    if context.api_key is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API keys cannot administer organization governance",
        )
    return context


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    _: User = Depends(require_permission(PermissionCode.API_KEYS_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyResponse]:
    context = _human_context(context)
    return service.list_for_tenant(context.tenant.id)


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: ApiKeyCreateRequest,
    current_user: User = Depends(require_permission(PermissionCode.API_KEYS_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyCreateResponse:
    context = _human_context(context)
    try:
        created = service.create(
            tenant_id=context.tenant.id,
            creator_user_id=current_user.id,
            name=request.name,
            scopes=request.scopes,
            expires_at=request.expires_at,
        )
    except ApiKeyValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid API key request") from error
    response = ApiKeyResponse.model_validate(created.api_key, from_attributes=True)
    return ApiKeyCreateResponse(**response.model_dump(), api_key=created.plaintext)


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    api_key_id: int,
    current_user: User = Depends(require_permission(PermissionCode.API_KEYS_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: ApiKeyService = Depends(get_api_key_service),
) -> Response:
    context = _human_context(context)
    try:
        service.revoke(tenant_id=context.tenant.id, api_key_id=api_key_id, actor_user_id=current_user.id)
    except ApiKeyValidationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/retention", response_model=RetentionPolicyResponse)
def get_retention_policy(
    _: User = Depends(require_permission(PermissionCode.RETENTION_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: RetentionService = Depends(get_retention_service),
) -> RetentionPolicyResponse:
    context = _human_context(context)
    policy = service.get_policy(context.tenant.id)
    return RetentionPolicyResponse(
        document_retention_days=policy.document_retention_days,
        updated_at=policy.updated_at,
    )


@router.put("/retention", response_model=RetentionPolicyResponse)
def update_retention_policy(
    request: RetentionPolicyUpdateRequest,
    current_user: User = Depends(require_permission(PermissionCode.RETENTION_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: RetentionService = Depends(get_retention_service),
) -> RetentionPolicyResponse:
    context = _human_context(context)
    try:
        return service.update_policy(
            tenant_id=context.tenant.id,
            actor_user_id=current_user.id,
            document_retention_days=request.document_retention_days,
        )
    except RetentionPolicyValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid retention policy") from error


@router.post("/retention/purge", response_model=RetentionPurgeResponse)
def run_retention_purge(
    current_user: User = Depends(require_permission(PermissionCode.RETENTION_MANAGE)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: RetentionService = Depends(get_retention_service),
) -> RetentionPurgeResponse:
    context = _human_context(context)
    return RetentionPurgeResponse(
        purged_count=service.purge_expired_documents(
            tenant_id=context.tenant.id,
            actor_user_id=current_user.id,
        )
    )
