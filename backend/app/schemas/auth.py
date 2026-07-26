from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field


class RegisterRequest(BaseModel):

    email: EmailStr

    full_name: str = Field(
        min_length=2,
        max_length=255,
    )

    password: str = Field(
        min_length=8,
        max_length=64,
    )


class LoginRequest(BaseModel):

    email: EmailStr

    password: str