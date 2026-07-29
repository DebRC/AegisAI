import unittest
from urllib.parse import parse_qs
from urllib.parse import urlparse

import httpx
from jose import JWTError
from unittest.mock import patch

from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoProviderError
from app.integrations.sso import GitHubOAuthProvider
from app.integrations.sso import GoogleOidcProvider
from app.integrations.sso import ProviderName
from app.integrations.sso import ProviderTokens
from app.integrations.sso import MicrosoftEntraOidcProvider


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class SsoProviderTests(unittest.TestCase):
    def test_authorization_urls_include_state_and_pkce(self) -> None:
        google = GoogleOidcProvider(
            "google-id", "google-secret", "https://api.example.com/", make_client(lambda _: None)
        )
        github = GitHubOAuthProvider(
            "github-id", "github-secret", "https://api.example.com", make_client(lambda _: None)
        )
        microsoft = MicrosoftEntraOidcProvider(
            "microsoft-id",
            "microsoft-secret",
            "https://api.example.com",
            "tenant-id",
            make_client(lambda _: None),
        )

        for provider in (google, github, microsoft):
            query = parse_qs(
                urlparse(provider.build_authorization_url("state", "challenge", "nonce")).query
            )
            self.assertEqual(query["state"], ["state"])
            self.assertEqual(query["code_challenge"], ["challenge"])
            self.assertEqual(query["code_challenge_method"], ["S256"])
            self.assertEqual(query["redirect_uri"], [provider.redirect_uri])

        self.assertEqual(
            parse_qs(urlparse(google.build_authorization_url("state", "challenge", "nonce")).query)["nonce"],
            ["nonce"],
        )
        self.assertNotIn(
            "nonce",
            parse_qs(urlparse(github.build_authorization_url("state", "challenge", "nonce")).query),
        )
        self.assertEqual(microsoft.name, ProviderName.MICROSOFT)

    def test_incomplete_provider_configuration_is_rejected(self) -> None:
        provider = GitHubOAuthProvider("", "secret", "not-a-url", make_client(lambda _: None))
        with self.assertRaises(SsoProviderConfigurationError):
            provider.build_authorization_url("state", "challenge", "nonce")

    def test_code_exchange_requires_an_access_token(self) -> None:
        provider = GitHubOAuthProvider(
            "github-id",
            "github-secret",
            "https://api.example.com",
            make_client(lambda _: httpx.Response(200, json={"access_token": "token"})),
        )
        self.assertEqual(provider.exchange_code("code", "verifier").access_token, "token")

        invalid = GitHubOAuthProvider(
            "github-id",
            "github-secret",
            "https://api.example.com",
            make_client(lambda _: httpx.Response(200, json={})),
        )
        with self.assertRaises(SsoProviderError):
            invalid.exchange_code("code", "verifier")

    def test_github_identity_uses_stable_id_and_verified_primary_email(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url == "https://api.github.com/user":
                return httpx.Response(200, json={"id": 42, "name": "Ada Lovelace"})
            if request.url == "https://api.github.com/user/emails":
                return httpx.Response(
                    200,
                    json=[
                        {"email": "old@example.com", "primary": False, "verified": True},
                        {"email": "ada@example.com", "primary": True, "verified": True},
                    ],
                )
            return httpx.Response(404)

        identity = GitHubOAuthProvider(
            "github-id", "github-secret", "https://api.example.com", make_client(handler)
        ).get_identity(ProviderTokens(access_token="github-token"))

        self.assertEqual(identity.provider, ProviderName.GITHUB)
        self.assertEqual(identity.subject, "42")
        self.assertEqual(identity.email, "ada@example.com")
        self.assertTrue(identity.email_verified)
        self.assertEqual(identity.full_name, "Ada Lovelace")

    @patch("app.integrations.sso.providers.jwt.decode")
    @patch("app.integrations.sso.providers.jwt.get_unverified_header")
    def test_oidc_identity_validates_token_and_nonce(self, header, decode) -> None:
        header.return_value = {"alg": "RS256", "kid": "key-1"}
        decode.return_value = {
            "sub": "provider-subject",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "nonce": "expected-nonce",
            "iss": "https://accounts.google.com",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url == "https://accounts.google.com/.well-known/openid-configuration":
                return httpx.Response(
                    200,
                    json={
                        "issuer": "https://accounts.google.com",
                        "jwks_uri": "https://keys.example.com/jwks",
                    },
                )
            if request.url == "https://keys.example.com/jwks":
                return httpx.Response(200, json={"keys": [{"kid": "key-1"}]})
            return httpx.Response(404)

        provider = GoogleOidcProvider(
            "google-id", "google-secret", "https://api.example.com", make_client(handler)
        )
        identity = provider.get_identity(
            ProviderTokens(access_token="access", id_token="signed-token"),
            "expected-nonce",
        )

        self.assertEqual(identity.provider, ProviderName.GOOGLE)
        self.assertEqual(identity.subject, "provider-subject")
        self.assertTrue(identity.email_verified)
        decode.assert_called_once_with(
            "signed-token",
            {"kid": "key-1"},
            algorithms=["RS256"],
            audience="google-id",
            options={"verify_iss": False},
        )

        decode.side_effect = JWTError("invalid")
        with self.assertRaises(SsoProviderError):
            provider.get_identity(
                ProviderTokens(access_token="access", id_token="signed-token"),
                "expected-nonce",
            )

    @patch("app.integrations.sso.providers.jwt.decode")
    @patch("app.integrations.sso.providers.jwt.get_unverified_header")
    def test_entra_identity_requires_matching_tenant_and_unverified_email(
        self,
        header,
        decode,
    ) -> None:
        header.return_value = {"alg": "RS256", "kid": "key-1"}
        decode.return_value = {
            "sub": "entra-subject",
            "email": "user@example.com",
            "nonce": "expected-nonce",
            "tid": "tenant-id",
            "iss": "https://login.microsoftonline.com/tenant-id/v2.0",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url == (
                "https://login.microsoftonline.com/tenant-id/v2.0/"
                ".well-known/openid-configuration"
            ):
                return httpx.Response(
                    200,
                    json={
                        "issuer": "https://login.microsoftonline.com/tenant-id/v2.0",
                        "jwks_uri": "https://keys.example.com/jwks",
                    },
                )
            if request.url == "https://keys.example.com/jwks":
                return httpx.Response(200, json={"keys": [{"kid": "key-1"}]})
            return httpx.Response(404)

        provider = MicrosoftEntraOidcProvider(
            "microsoft-id",
            "microsoft-secret",
            "https://api.example.com",
            "tenant-id",
            make_client(handler),
        )
        identity = provider.get_identity(
            ProviderTokens(access_token="access", id_token="signed-token"),
            "expected-nonce",
        )
        self.assertEqual(identity.subject, "entra-subject")
        self.assertFalse(identity.email_verified)

        decode.return_value = {**decode.return_value, "tid": "other-tenant"}
        with self.assertRaises(SsoProviderError):
            provider.get_identity(
                ProviderTokens(access_token="access", id_token="signed-token"),
                "expected-nonce",
            )
