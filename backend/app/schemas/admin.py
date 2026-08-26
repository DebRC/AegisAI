"""Safe response contracts for Phase 14 administration APIs."""

from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from app.models.document import DocumentStatus


class AdminUserRoleResponse(BaseModel):
    id: int
    name: str
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime
    roles: list[AdminUserRoleResponse]


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    offset: int
    limit: int
    total: int


class AdminUserStatusRequest(BaseModel):
    is_active: bool


class AdminRoleResponse(BaseModel):
    id: int
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]
    user_count: int


class AdminPermissionResponse(BaseModel):
    id: int
    code: str
    description: str
    role_count: int

class AdminDocumentResponse(BaseModel):
    id: int
    uploader_user_id: int
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    processing_error: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocumentResponse]
    offset: int
    limit: int
    total: int
