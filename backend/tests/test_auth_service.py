import unittest
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from app.core.exceptions import AuthenticationError
from app.core.exceptions import UserAlreadyExistsError
from app.models import RefreshToken
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.auth import RegisterRequest
from app.security.jwt import decode_token
from app.security.jwt import refresh_token_expiry
from app.security.hashing import verify_password
from app.services.auth_service import AuthService
from tests.helpers import DatabaseTestCase


class AuthServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.service = AuthService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_register_hashes_password_and_rejects_duplicate_email(self) -> None:
        request = RegisterRequest(
            email="person@example.com",
            full_name="Test Person",
            password="strong-password",
        )

        user = self.service.register(request)

        self.assertTrue(verify_password("strong-password", user.password_hash))

        with self.assertRaises(UserAlreadyExistsError):
            self.service.register(request)

    def test_login_refresh_logout_and_cleanup(self) -> None:
        user = self.service.register(
            RegisterRequest(
                email="person@example.com",
                full_name="Test Person",
                password="strong-password",
            )
        )

        with self.assertRaises(AuthenticationError):
            self.service.login(user.email, "incorrect-password")

        login_response = self.service.login(user.email, "strong-password")
        original = login_response.refresh_token
        stored_original = RefreshTokenRepository(self.session).get_by_token(original)

        self.assertIsNotNone(user.last_login)
        self.assertEqual(decode_token(login_response.access_token).sub, user.id)
        self.assertIsNotNone(stored_original)

        refreshed = self.service.refresh(original)
        self.assertNotEqual(refreshed.refresh_token, original)
        self.assertIsNotNone(stored_original.revoked_at)

        with self.assertRaises(AuthenticationError):
            self.service.refresh(original)

        self.service.logout(refreshed.refresh_token)
        self.assertIsNotNone(
            RefreshTokenRepository(self.session)
            .get_by_token(refreshed.refresh_token)
            .revoked_at
        )

        expired = RefreshToken(
            token="expired-token",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            user_id=user.id,
        )
        self.session.add(expired)
        self.session.commit()

        self.assertEqual(self.service.cleanup_expired_tokens(), 1)
        self.assertIsNone(RefreshTokenRepository(self.session).get_by_token("expired-token"))

    def test_inactive_users_cannot_create_or_refresh_sessions(self) -> None:
        user = self.service.register(
            RegisterRequest(
                email="person@example.com",
                full_name="Test Person",
                password="strong-password",
            )
        )
        session = self.service.issue_session(user)
        user.is_active = False
        self.session.commit()

        with self.assertRaises(AuthenticationError):
            self.service.login(user.email, "strong-password")
        with self.assertRaises(AuthenticationError):
            self.service.issue_session(user)
        with self.assertRaises(AuthenticationError):
            self.service.refresh(session.refresh_token)

        stored = RefreshTokenRepository(self.session).get_by_token(session.refresh_token)
        self.assertIsNotNone(stored.revoked_at)
