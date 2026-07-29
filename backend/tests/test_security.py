import unittest
from datetime import timedelta

from app.core.exceptions import AuthenticationError
from app.security.constants import TokenType
from app.security.hashing import hash_password
from app.security.hashing import verify_password
from app.security.jwt import create_access_token
from app.security.jwt import create_refresh_token
from app.security.jwt import create_token
from app.security.jwt import decode_token
from app.security.jwt import refresh_token_expiry
from app.security.permissions import PermissionCode


class SecurityTests(unittest.TestCase):
    def test_password_hash_verification(self) -> None:
        password_hash = hash_password("correct-password")

        self.assertTrue(verify_password("correct-password", password_hash))
        self.assertFalse(verify_password("incorrect-password", password_hash))

    def test_access_and_refresh_tokens_have_expected_subject_and_type(self) -> None:
        access_payload = decode_token(create_access_token(17))
        refresh_payload = decode_token(create_refresh_token(17))

        self.assertEqual(access_payload.sub, 17)
        self.assertEqual(access_payload.type, TokenType.ACCESS)
        self.assertEqual(refresh_payload.sub, 17)
        self.assertEqual(refresh_payload.type, TokenType.REFRESH)

    def test_expired_and_invalid_tokens_are_rejected(self) -> None:
        expired = create_token(
            17,
            TokenType.ACCESS,
            timedelta(seconds=-1),
        )

        with self.assertRaises(AuthenticationError):
            decode_token(expired)

        with self.assertRaises(AuthenticationError):
            decode_token("not-a-jwt")

    def test_refresh_expiry_is_in_the_future(self) -> None:
        self.assertGreater(refresh_token_expiry().timestamp(), 0)

    def test_permission_codes_are_unique_and_stable(self) -> None:
        values = PermissionCode.values()

        self.assertEqual(len(values), len(set(values)))
        self.assertIn("roles:manage", values)
