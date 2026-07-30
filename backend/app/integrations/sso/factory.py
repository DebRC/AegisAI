import httpx

from app.core.config import Settings
from app.core.exceptions import SsoProviderConfigurationError
from app.integrations.sso.models import ProviderName
from app.integrations.sso.providers import BaseOAuthProvider
from app.integrations.sso.providers import GitHubOAuthProvider
from app.integrations.sso.providers import GoogleOidcProvider
from app.integrations.sso.providers import MicrosoftEntraOidcProvider


class SsoProviderFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(
        self,
        provider: ProviderName,
        http_client: httpx.Client,
    ) -> BaseOAuthProvider:
        if not self.settings.SSO_ENABLED:
            raise SsoProviderConfigurationError("SSO is disabled")

        if provider is ProviderName.GOOGLE:
            return GoogleOidcProvider(
                self.settings.GOOGLE_CLIENT_ID,
                self.settings.GOOGLE_CLIENT_SECRET,
                self.settings.SSO_CALLBACK_BASE_URL,
                http_client,
            )
        if provider is ProviderName.GITHUB:
            return GitHubOAuthProvider(
                self.settings.GITHUB_CLIENT_ID,
                self.settings.GITHUB_CLIENT_SECRET,
                self.settings.SSO_CALLBACK_BASE_URL,
                http_client,
            )
        if provider is ProviderName.MICROSOFT:
            return MicrosoftEntraOidcProvider(
                self.settings.MICROSOFT_ENTRA_CLIENT_ID,
                self.settings.MICROSOFT_ENTRA_CLIENT_SECRET,
                self.settings.SSO_CALLBACK_BASE_URL,
                self.settings.MICROSOFT_ENTRA_TENANT_ID,
                http_client,
            )
        raise SsoProviderConfigurationError("Unsupported SSO provider")
