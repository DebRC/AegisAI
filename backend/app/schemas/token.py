from pydantic import BaseModel
from datetime import datetime
from app.schemas.user import UserResponse
from app.security.constants import TOKEN_SCHEME
from app.security.constants import TokenType

class TokenResponse(BaseModel):

    access_token: str

    refresh_token: str

    token_type: str = TOKEN_SCHEME

    expires_in: int


class LoginResponse(TokenResponse):

    user: UserResponse


class TokenPayload(BaseModel):

    sub: int

    type: TokenType

    exp: datetime
