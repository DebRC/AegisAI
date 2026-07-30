import unittest

from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoTransactionError
from app.integrations.sso.models import ProviderName
from app.security.sso_transactions import SsoTransactionManager


class SsoTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = SsoTransactionManager("state-secret", 5, secure_cookie=True)

    def test_transaction_round_trip_and_cookie_metadata(self) -> None:
        transaction = self.manager.create(ProviderName.GOOGLE)
        restored = self.manager.validate(
            self.manager.encode(transaction),
            ProviderName.GOOGLE,
            transaction.state,
        )

        self.assertEqual(restored, transaction)
        self.assertTrue(self.manager.secure_cookie)
        self.assertEqual(
            self.manager.cookie_name(ProviderName.GOOGLE),
            "sso_transaction_google",
        )
        self.assertEqual(
            self.manager.callback_path(ProviderName.GOOGLE),
            "/auth/sso/google/callback",
        )

    def test_transaction_rejects_mismatch_missing_and_invalid_configuration(self) -> None:
        transaction = self.manager.create(ProviderName.GITHUB)
        cookie = self.manager.encode(transaction)

        with self.assertRaises(SsoTransactionError):
            self.manager.validate(cookie, ProviderName.GOOGLE, transaction.state)
        with self.assertRaises(SsoTransactionError):
            self.manager.validate(cookie, ProviderName.GITHUB, "wrong-state")
        with self.assertRaises(SsoTransactionError):
            self.manager.validate(None, ProviderName.GITHUB, transaction.state)
        with self.assertRaises(SsoProviderConfigurationError):
            SsoTransactionManager("", 5, False).create(ProviderName.GITHUB)
        with self.assertRaises(SsoProviderConfigurationError):
            SsoTransactionManager("secret", 0, False).create(ProviderName.GITHUB)
