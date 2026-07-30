import unittest

from app.core.exceptions import SsoEmailVerificationError
from app.integrations.sso.models import ProviderIdentity
from app.integrations.sso.models import ProviderName
from app.models import ExternalIdentity
from app.repositories.external_identity_repository import ExternalIdentityRepository
from app.repositories.user_repository import UserRepository
from app.security.hashing import verify_password
from app.services.sso_account_service import SsoAccountService
from tests.helpers import DatabaseTestCase


class SsoAccountServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.service = SsoAccountService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def identity(
        self,
        *,
        email: str | None = "person@example.com",
        email_verified: bool = True,
        subject: str = "provider-subject",
        full_name: str | None = "SSO Person",
    ) -> ProviderIdentity:
        return ProviderIdentity(
            provider=ProviderName.GOOGLE,
            subject=subject,
            email=email,
            email_verified=email_verified,
            full_name=full_name,
        )

    def test_existing_external_identity_returns_its_linked_user(self) -> None:
        user = self.create_user("linked@example.com")
        repository = ExternalIdentityRepository(self.session)
        repository.create(
            ExternalIdentity(
                provider="google",
                provider_subject="provider-subject",
                provider_email="old@example.com",
                email_verified=False,
                user_id=user.id,
            )
        )
        self.session.commit()

        resolved = self.service.resolve_identity(self.identity(email="linked@example.com"))

        stored = repository.get_by_provider_and_subject("google", "provider-subject")
        self.assertEqual(resolved.id, user.id)
        self.assertEqual(stored.provider_email, "linked@example.com")
        self.assertTrue(stored.email_verified)

    def test_verified_email_links_to_existing_local_user(self) -> None:
        user = self.create_user("person@example.com")

        resolved = self.service.resolve_identity(self.identity())

        stored = ExternalIdentityRepository(self.session).get_by_provider_and_subject(
            "google",
            "provider-subject",
        )
        self.assertEqual(resolved.id, user.id)
        self.assertEqual(stored.user_id, user.id)

    def test_verified_email_provisions_sso_only_user_and_identity(self) -> None:
        resolved = self.service.resolve_identity(
            self.identity(email="new@example.com", full_name=None)
        )

        stored_user = UserRepository(self.session).get_by_email("new@example.com")
        stored_identity = ExternalIdentityRepository(
            self.session
        ).get_by_provider_and_subject("google", "provider-subject")
        self.assertEqual(resolved.id, stored_user.id)
        self.assertEqual(stored_user.full_name, "new")
        self.assertFalse(verify_password("known-password", stored_user.password_hash))
        self.assertEqual(stored_identity.user_id, stored_user.id)
        self.assertTrue(stored_identity.email_verified)

    def test_unverified_or_missing_email_does_not_create_an_account(self) -> None:
        with self.assertRaises(SsoEmailVerificationError):
            self.service.resolve_identity(self.identity(email_verified=False))
        with self.assertRaises(SsoEmailVerificationError):
            self.service.resolve_identity(self.identity(email=None))

        self.assertIsNone(UserRepository(self.session).get_by_email("person@example.com"))
        self.assertIsNone(
            ExternalIdentityRepository(self.session).get_by_provider_and_subject(
                "google",
                "provider-subject",
            )
        )
