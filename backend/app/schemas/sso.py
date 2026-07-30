from pydantic import BaseModel

from app.integrations.sso.models import ProviderName


class SsoCallbackResponse(BaseModel):
    message: str
    provider: ProviderName
