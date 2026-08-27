import json
import unittest
from datetime import datetime
from datetime import timezone
from unittest.mock import Mock
from unittest.mock import patch

from starlette.requests import Request

from app.api import sso as sso_api
from app.core.exceptions import AuthenticationError
from app.core.exceptions import SsoEmailVerificationError
from app.integrations.sso.models import ProviderIdentity
from app.integrations.sso.models import ProviderName
from app.integrations.sso.models import ProviderTokens
from app.models import AuditEventType
from app.schemas.token import LoginResponse
from app.schemas.user import UserResponse
from app.security.sso_transactions import SsoTransactionManager


def request_with_cookie(name: str, value: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/sso/google/callback",
            "headers": [(b"cookie", f"{name}={value}".encode())],
        }
    )


class SsoRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = SsoTransactionManager("state-secret", 5, secure_cookie=False)
        self.provider = Mock()
        self.provider.build_authorization_url.return_value = "https://provider.example/authorize"
        self.provider.exchange_code.return_value = ProviderTokens(access_token="provider-token")
        self.provider.get_identity.return_value = ProviderIdentity(
            provider=ProviderName.GITHUB,
            subject="42",
            email="user@example.com",
            email_verified=True,
            full_name="Test User",
        )
        self.factory = Mock()
        self.factory.create.return_value = self.provider
        self.accounts = Mock()
        self.local_user = Mock()
        self.accounts.resolve_identity.return_value = self.local_user
        self.auth_service = Mock()
        self.auth_service.issue_session.return_value = LoginResponse(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=900,
            user=UserResponse(
                id=1,
                email="user@example.com",
                full_name="Test User",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
        )

    def test_begin_sso_redirects_and_sets_http_only_transaction_cookie(self) -> None:
        response = sso_api.begin_sso(
            ProviderName.GITHUB,
            self.factory,
            self.transactions,
        )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "https://provider.example/authorize")
        cookie = response.headers["set-cookie"]
        self.assertIn("sso_transaction_github=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Path=/auth/sso/github/callback", cookie)
        self.provider.build_authorization_url.assert_called_once()

    def test_code_challenge_uses_the_pkce_s256_transformation(self) -> None:
        self.assertEqual(
            sso_api._code_challenge(
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
            ),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        )

    def test_complete_sso_verifies_callback_and_clears_cookie(self) -> None:
        transaction = self.transactions.create(ProviderName.GITHUB)
        request = request_with_cookie(
            self.transactions.cookie_name(ProviderName.GITHUB),
            self.transactions.encode(transaction),
        )

        response = sso_api.complete_sso(
            ProviderName.GITHUB,
            request,
            transaction.state,
            "authorization-code",
            None,
            self.factory,
            self.transactions,
            self.accounts,
            self.auth_service,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.body),
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
                "expires_in": 900,
                "user": {
                    "id": 1,
                    "email": "user@example.com",
                    "full_name": "Test User",
                    "is_active": True,
                    "created_at": self.auth_service.issue_session.return_value.model_dump(
                        mode="json"
                    )["user"]["created_at"],
                },
                "provider": "github",
            },
        )
        self.provider.exchange_code.assert_called_once_with(
            "authorization-code",
            transaction.code_verifier,
        )
        self.provider.get_identity.assert_called_once_with(
            self.provider.exchange_code.return_value,
            transaction.nonce,
        )
        self.accounts.resolve_identity.assert_called_once_with(
            self.provider.get_identity.return_value,
        )
        self.auth_service.issue_session.assert_called_once_with(
            self.local_user,
            success_event_type=AuditEventType.AUTH_SSO_SUCCEEDED,
            failure_event_type=AuditEventType.AUTH_SSO_FAILED,
            metadata={"provider": "github"},
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_complete_sso_redirects_to_the_frontend_with_http_only_session_cookies(self) -> None:
        transaction = self.transactions.create(ProviderName.GITHUB)
        request = request_with_cookie(
            self.transactions.cookie_name(ProviderName.GITHUB),
            self.transactions.encode(transaction),
        )

        with patch.object(sso_api.settings, "SSO_FRONTEND_REDIRECT_URL", "http://localhost:3000"):
            response = sso_api.complete_sso(
                ProviderName.GITHUB,
                request,
                transaction.state,
                "authorization-code",
                None,
                self.factory,
                self.transactions,
                self.accounts,
                self.auth_service,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "http://localhost:3000/login?provider=github")
        cookies = "\n".join(
            value.decode()
            for key, value in response.raw_headers
            if key == b"set-cookie"
        )
        self.assertIn("aegis_access_token=access-token", cookies)
        self.assertIn("aegis_refresh_token=refresh-token", cookies)
        self.assertIn("HttpOnly", cookies)
        self.assertNotIn("access-token", response.headers["location"])

    def test_complete_sso_rejects_identity_without_a_verified_email(self) -> None:
        transaction = self.transactions.create(ProviderName.GITHUB)
        request = request_with_cookie(
            self.transactions.cookie_name(ProviderName.GITHUB),
            self.transactions.encode(transaction),
        )
        self.accounts.resolve_identity.side_effect = SsoEmailVerificationError()

        response = sso_api.complete_sso(
            ProviderName.GITHUB,
            request,
            transaction.state,
            "authorization-code",
            None,
            self.factory,
            self.transactions,
            self.accounts,
            self.auth_service,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_complete_sso_rejects_an_inactive_local_account(self) -> None:
        transaction = self.transactions.create(ProviderName.GITHUB)
        request = request_with_cookie(
            self.transactions.cookie_name(ProviderName.GITHUB),
            self.transactions.encode(transaction),
        )
        self.auth_service.issue_session.side_effect = AuthenticationError()

        response = sso_api.complete_sso(
            ProviderName.GITHUB,
            request,
            transaction.state,
            "authorization-code",
            None,
            self.factory,
            self.transactions,
            self.accounts,
            self.auth_service,
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_complete_sso_rejects_error_or_state_mismatch_and_clears_cookie(self) -> None:
        transaction = self.transactions.create(ProviderName.GOOGLE)
        request = request_with_cookie(
            self.transactions.cookie_name(ProviderName.GOOGLE),
            self.transactions.encode(transaction),
        )

        failed = sso_api.complete_sso(
            ProviderName.GOOGLE,
            request,
            transaction.state,
            None,
            "access_denied",
            self.factory,
            self.transactions,
            self.accounts,
            self.auth_service,
        )
        self.assertEqual(failed.status_code, 400)
        self.assertIn("Max-Age=0", failed.headers["set-cookie"])

        mismatch = sso_api.complete_sso(
            ProviderName.GOOGLE,
            request,
            "wrong-state",
            "authorization-code",
            None,
            self.factory,
            self.transactions,
            self.accounts,
            self.auth_service,
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("Max-Age=0", mismatch.headers["set-cookie"])
