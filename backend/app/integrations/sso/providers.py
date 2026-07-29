from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError
from jose import jwt

from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoProviderError
from app.integrations.sso.models import ProviderIdentity
from app.integrations.sso.models import ProviderName
from app.integrations.sso.models import ProviderTokens


class BaseOAuthProvider:
    name: ProviderName
    authorization_endpoint: str
    token_endpoint: str
    scopes: tuple[str, ...]

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        callback_base_url: str,
        http_client: httpx.Client,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_base_url = callback_base_url.rstrip("/")
        self.http_client = http_client

    @property
    def redirect_uri(self) -> str:
        return f"{self.callback_base_url}/auth/sso/{self.name.value}/callback"

    def build_authorization_url(
        self,
        state: str,
        code_challenge: str,
        nonce: str,
    ) -> str:
        self._require_configuration()
        parameters = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        parameters.update(self._authorization_parameters(nonce))
        return f"{self.authorization_endpoint}?{urlencode(parameters)}"

    def exchange_code(
        self,
        code: str,
        code_verifier: str,
    ) -> ProviderTokens:
        self._require_configuration()
        response = self._request(
            "POST",
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        payload = self._json_object(response, "token exchange")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise SsoProviderError("Provider did not return an access token")

        id_token = payload.get("id_token")
        if id_token is not None and not isinstance(id_token, str):
            raise SsoProviderError("Provider returned an invalid ID token")

        return ProviderTokens(access_token=access_token, id_token=id_token)

    def _authorization_parameters(self, nonce: str) -> dict[str, str]:
        return {}

    def _require_configuration(self) -> None:
        if not self.client_id or not self.client_secret:
            raise SsoProviderConfigurationError(
                f"{self.name.value} SSO credentials are not configured"
            )
        if not self.callback_base_url.startswith(("http://", "https://")):
            raise SsoProviderConfigurationError(
                "SSO_CALLBACK_BASE_URL must be an absolute HTTP(S) URL"
            )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.http_client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            raise SsoProviderError(
                f"{self.name.value} provider request failed"
            ) from error

    @staticmethod
    def _json_object(response: httpx.Response, context: str) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise SsoProviderError(f"Provider returned invalid JSON during {context}") from error
        if not isinstance(payload, Mapping):
            raise SsoProviderError(f"Provider returned invalid JSON during {context}")
        return payload


class OidcProvider(BaseOAuthProvider):
    discovery_url: str
    issuer: str

    def _authorization_parameters(self, nonce: str) -> dict[str, str]:
        return {"nonce": nonce}

    def get_identity(
        self,
        tokens: ProviderTokens,
        expected_nonce: str,
    ) -> ProviderIdentity:
        if not tokens.id_token:
            raise SsoProviderError("Provider did not return an ID token")

        metadata = self._get_metadata()
        claims = self._decode_identity_token(tokens.id_token, metadata, expected_nonce)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise SsoProviderError("Provider ID token does not include a subject")

        email = claims.get("email")
        return ProviderIdentity(
            provider=self.name,
            subject=subject,
            email=email if isinstance(email, str) else None,
            email_verified=self._email_is_verified(claims),
            full_name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        )

    def _get_metadata(self) -> Mapping[str, Any]:
        response = self._request("GET", self.discovery_url)
        metadata = self._json_object(response, "OpenID Connect discovery")
        for field in ("issuer", "jwks_uri"):
            if not isinstance(metadata.get(field), str):
                raise SsoProviderError("Provider discovery document is incomplete")
        return metadata

    def _decode_identity_token(
        self,
        id_token: str,
        metadata: Mapping[str, Any],
        expected_nonce: str,
    ) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
            key_id = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(key_id, str):
                raise SsoProviderError("Provider ID token uses an unsupported signing key")

            jwks_response = self._request("GET", metadata["jwks_uri"])
            jwks = self._json_object(jwks_response, "OpenID Connect key retrieval")
            keys = jwks.get("keys")
            if not isinstance(keys, list):
                raise SsoProviderError("Provider key set is invalid")
            key = next(
                (candidate for candidate in keys if candidate.get("kid") == key_id),
                None,
            )
            if not isinstance(key, Mapping):
                raise SsoProviderError("Provider signing key was not found")

            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                options={"verify_iss": False},
            )
        except JWTError as error:
            raise SsoProviderError("Provider ID token validation failed") from error

        self._validate_issuer(claims, metadata)
        if claims.get("nonce") != expected_nonce:
            raise SsoProviderError("Provider ID token nonce validation failed")
        return claims

    def _validate_issuer(
        self,
        claims: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        if claims.get("iss") != metadata["issuer"]:
            raise SsoProviderError("Provider ID token issuer validation failed")

    def _email_is_verified(self, claims: Mapping[str, Any]) -> bool:
        return claims.get("email_verified") is True


class GoogleOidcProvider(OidcProvider):
    name = ProviderName.GOOGLE
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    discovery_url = "https://accounts.google.com/.well-known/openid-configuration"
    issuer = "https://accounts.google.com"
    scopes = ("openid", "email", "profile")

    def _validate_issuer(
        self,
        claims: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        if claims.get("iss") not in {
            "https://accounts.google.com",
            "accounts.google.com",
        }:
            raise SsoProviderError("Provider ID token issuer validation failed")


class MicrosoftEntraOidcProvider(OidcProvider):
    name = ProviderName.MICROSOFT
    scopes = ("openid", "email", "profile")

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        callback_base_url: str,
        tenant_id: str,
        http_client: httpx.Client,
    ) -> None:
        tenant = tenant_id.strip()
        if not tenant:
            raise SsoProviderConfigurationError("Microsoft Entra tenant ID is required")
        authority = f"https://login.microsoftonline.com/{tenant}/v2.0"
        self.tenant_id = tenant
        self.authorization_endpoint = f"{authority}/authorize"
        self.token_endpoint = f"{authority}/token"
        self.discovery_url = f"{authority}/.well-known/openid-configuration"
        self.issuer = authority
        super().__init__(client_id, client_secret, callback_base_url, http_client)

    def _email_is_verified(self, claims: Mapping[str, Any]) -> bool:
        # Entra does not provide a universal email_verified claim. A later
        # account-linking step must not treat preferred_username as proof.
        return False

    def _validate_issuer(
        self,
        claims: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        token_tenant = claims.get("tid")
        if not isinstance(token_tenant, str) or not token_tenant:
            raise SsoProviderError("Microsoft Entra ID token does not include a tenant")
        if self.tenant_id not in {"common", "organizations"} and token_tenant != self.tenant_id:
            raise SsoProviderError("Microsoft Entra ID token is from the wrong tenant")
        expected_issuer = f"https://login.microsoftonline.com/{token_tenant}/v2.0"
        if claims.get("iss") != expected_issuer:
            raise SsoProviderError("Provider ID token issuer validation failed")


class GitHubOAuthProvider(BaseOAuthProvider):
    name = ProviderName.GITHUB
    authorization_endpoint = "https://github.com/login/oauth/authorize"
    token_endpoint = "https://github.com/login/oauth/access_token"
    scopes = ("read:user", "user:email")
    profile_endpoint = "https://api.github.com/user"
    emails_endpoint = "https://api.github.com/user/emails"

    def get_identity(self, tokens: ProviderTokens) -> ProviderIdentity:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {tokens.access_token}",
        }
        profile = self._json_object(
            self._request("GET", self.profile_endpoint, headers=headers),
            "GitHub profile retrieval",
        )
        subject = profile.get("id")
        if not isinstance(subject, int):
            raise SsoProviderError("GitHub profile does not include an account ID")

        email, email_verified = self._get_primary_verified_email(headers)
        full_name = profile.get("name") or profile.get("login")
        return ProviderIdentity(
            provider=self.name,
            subject=str(subject),
            email=email,
            email_verified=email_verified,
            full_name=full_name if isinstance(full_name, str) else None,
        )

    def _get_primary_verified_email(
        self,
        headers: Mapping[str, str],
    ) -> tuple[str | None, bool]:
        response = self._request("GET", self.emails_endpoint, headers=headers)
        try:
            emails = response.json()
        except ValueError as error:
            raise SsoProviderError("GitHub returned invalid email data") from error
        if not isinstance(emails, list):
            raise SsoProviderError("GitHub returned invalid email data")

        for email in emails:
            if (
                isinstance(email, Mapping)
                and email.get("primary") is True
                and email.get("verified") is True
                and isinstance(email.get("email"), str)
            ):
                return email["email"], True
        return None, False
