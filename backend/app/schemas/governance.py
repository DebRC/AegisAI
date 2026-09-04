from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=20)
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(ApiKeyResponse):
    # Displayed once. Callers must store it in their approved secret manager.
    api_key: str


class RetentionPolicyUpdateRequest(BaseModel):
    document_retention_days: int | None = Field(default=None, ge=1, le=36500)


class RetentionPolicyResponse(BaseModel):
    document_retention_days: int | None
    updated_at: datetime | None


class RetentionPurgeResponse(BaseModel):
    purged_count: int
