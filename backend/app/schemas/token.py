from pydantic import BaseModel
from datetime import datetime
from app.security.constants import TOKEN_TYPE

class TokenResponse(BaseModel):

    access_token: str

    refresh_token: str

    token_type: str = TOKEN_TYPE


class TokenPayload(BaseModel):

    sub: int

    type: str

    exp: datetime