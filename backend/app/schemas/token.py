from pydantic import BaseModel
from datetime import datetime

class TokenResponse(BaseModel):

    access_token: str

    refresh_token: str

    token_type: str = "bearer"


class TokenPayload(BaseModel):

    sub: int

    type: str

    exp: datetime