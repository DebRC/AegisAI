from app.integrations.sso.models import ProviderName
from app.schemas.token import LoginResponse


class SsoCallbackResponse(LoginResponse):
    provider: ProviderName
