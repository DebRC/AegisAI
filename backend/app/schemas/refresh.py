from pydantic import BaseModel
from pydantic import Field


class RefreshRequest(BaseModel):

    refresh_token: str = Field(min_length=1)
