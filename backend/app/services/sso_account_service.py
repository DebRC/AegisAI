import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import SsoAccountResolutionError
from app.core.exceptions import SsoEmailVerificationError
from app.integrations.sso.models import ProviderIdentity
from app.models.external_identity import ExternalIdentity
from app.models.user import User
from app.repositories.external_identity_repository import ExternalIdentityRepository
from app.repositories.user_repository import UserRepository
from app.security.hashing import hash_password


class SsoAccountService:
    """Resolve a verified provider identity to one local AegisAI user."""

    def __init__(self, db: Session):
        self.db = db
        self.external_identities = ExternalIdentityRepository(db)
        self.users = UserRepository(db)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def resolve_identity(self, provider_identity: ProviderIdentity) -> User:
        """Find, link, or safely provision the local account for an SSO identity."""
        try:
            external_identity = self.external_identities.get_by_provider_and_subject(
                provider_identity.provider.value,
                provider_identity.subject,
            )
            if external_identity is not None:
                external_identity.provider_email = provider_identity.email
                external_identity.email_verified = provider_identity.email_verified
                self.external_identities.update()
                self._commit()
                return external_identity.user

            email = self._verified_email(provider_identity)
            user = self.users.get_by_email(email)
            if user is None:
                user = self.users.create(
                    User(
                        email=email,
                        full_name=self._full_name(provider_identity, email),
                        password_hash=hash_password(secrets.token_urlsafe(48)),
                    )
                )

            self.external_identities.create(
                ExternalIdentity(
                    provider=provider_identity.provider.value,
                    provider_subject=provider_identity.subject,
                    provider_email=email,
                    email_verified=True,
                    user_id=user.id,
                )
            )
            self._commit()
            return user
        except IntegrityError as error:
            self.db.rollback()
            raise SsoAccountResolutionError() from error

    @staticmethod
    def _verified_email(provider_identity: ProviderIdentity) -> str:
        if not provider_identity.email_verified or not provider_identity.email:
            raise SsoEmailVerificationError()
        return provider_identity.email

    @staticmethod
    def _full_name(provider_identity: ProviderIdentity, email: str) -> str:
        full_name = (provider_identity.full_name or "").strip()
        return (full_name or email.partition("@")[0])[:255]
