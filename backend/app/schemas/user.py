from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import EmailStr


class UserResponse(BaseModel):

    id: int

    email: EmailStr

    full_name: str

    is_active: bool

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )