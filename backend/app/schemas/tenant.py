from pydantic import BaseModel, Field


class TenantResponse(BaseModel):
    id: int
    slug: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)


class TenantMembershipResponse(BaseModel):
    tenant: TenantResponse
    is_active: bool

    model_config = {"from_attributes": True}


class TenantMembershipCreateRequest(BaseModel):
    user_id: int = Field(gt=0)
