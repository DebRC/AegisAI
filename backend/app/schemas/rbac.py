from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PermissionResponse(BaseModel):
    id: int
    code: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolePermissionResponse(BaseModel):
    id: int
    role_id: int
    permission_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleResponse(BaseModel):
    id: int
    user_id: int
    role_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
