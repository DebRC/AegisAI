from types import SimpleNamespace
import unittest

import httpx

from app.core.exceptions import SsoProviderConfigurationError
from app.integrations.sso.factory import SsoProviderFactory
from app.integrations.sso.models import ProviderName
from app.integrations.sso.providers import GitHubOAuthProvider
from app.integrations.sso.providers import GoogleOidcProvider
from app.integrations.sso.providers import MicrosoftEntraOidcProvider


class SsoProviderFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            SSO_ENABLED=True,
            SSO_CALLBACK_BASE_URL="https://api.example.com",
            GOOGLE_CLIENT_ID="google-id",
            GOOGLE_CLIENT_SECRET="google-secret",
            GITHUB_CLIENT_ID="github-id",
            GITHUB_CLIENT_SECRET="github-secret",
            MICROSOFT_ENTRA_CLIENT_ID="microsoft-id",
            MICROSOFT_ENTRA_CLIENT_SECRET="microsoft-secret",
            MICROSOFT_ENTRA_TENANT_ID="tenant-id",
        )

    def test_factory_creates_the_requested_provider(self) -> None:
        factory = SsoProviderFactory(self.settings)
        with httpx.Client() as client:
            self.assertIsInstance(
                factory.create(ProviderName.GOOGLE, client),
                GoogleOidcProvider,
            )
            self.assertIsInstance(
                factory.create(ProviderName.GITHUB, client),
                GitHubOAuthProvider,
            )
            self.assertIsInstance(
                factory.create(ProviderName.MICROSOFT, client),
                MicrosoftEntraOidcProvider,
            )

    def test_factory_rejects_disabled_sso(self) -> None:
        self.settings.SSO_ENABLED = False
        with httpx.Client() as client:
            with self.assertRaises(SsoProviderConfigurationError):
                SsoProviderFactory(self.settings).create(ProviderName.GOOGLE, client)
