from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from secrets import compare_digest
from secrets import token_urlsafe

from jose import ExpiredSignatureError
from jose import JWTError
from jose import jwt

from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoTransactionError
from app.integrations.sso.models import ProviderName


@dataclass(frozen=True)
class SsoTransaction:
    provider: ProviderName
    state: str
    code_verifier: str
    nonce: str


class SsoTransactionManager:
    _algorithm = "HS256"

    def __init__(
        self,
        secret_key: str,
        expires_in_minutes: int,
        secure_cookie: bool,
    ) -> None:
        self.secret_key = secret_key
        self.expires_in_minutes = expires_in_minutes
        self.secure_cookie = secure_cookie

    def create(self, provider: ProviderName) -> SsoTransaction:
        self._validate_configuration()
        return SsoTransaction(
            provider=provider,
            state=token_urlsafe(32),
            code_verifier=token_urlsafe(64),
            nonce=token_urlsafe(32),
        )

    def encode(self, transaction: SsoTransaction) -> str:
        self._validate_configuration()
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "type": "sso_transaction",
                "provider": transaction.provider.value,
                "state": transaction.state,
                "code_verifier": transaction.code_verifier,
                "nonce": transaction.nonce,
                "iat": now,
                "exp": now + timedelta(minutes=self.expires_in_minutes),
            },
            self.secret_key,
            algorithm=self._algorithm,
        )

    def validate(
        self,
        cookie_value: str | None,
        provider: ProviderName,
        returned_state: str,
    ) -> SsoTransaction:
        self._validate_configuration()
        if not cookie_value:
            raise SsoTransactionError("SSO transaction cookie is missing")

        try:
            payload = jwt.decode(
                cookie_value,
                self.secret_key,
                algorithms=[self._algorithm],
            )
        except ExpiredSignatureError as error:
            raise SsoTransactionError("SSO transaction has expired") from error
        except JWTError as error:
            raise SsoTransactionError("SSO transaction is invalid") from error

        if (
            payload.get("type") != "sso_transaction"
            or payload.get("provider") != provider.value
            or not isinstance(payload.get("state"), str)
            or not isinstance(payload.get("code_verifier"), str)
            or not isinstance(payload.get("nonce"), str)
            or not compare_digest(payload["state"], returned_state)
        ):
            raise SsoTransactionError("SSO transaction does not match callback")

        return SsoTransaction(
            provider=provider,
            state=payload["state"],
            code_verifier=payload["code_verifier"],
            nonce=payload["nonce"],
        )

    def cookie_name(self, provider: ProviderName) -> str:
        return f"sso_transaction_{provider.value}"

    def callback_path(self, provider: ProviderName) -> str:
        return f"/auth/sso/{provider.value}/callback"

    def _validate_configuration(self) -> None:
        if not self.secret_key:
            raise SsoProviderConfigurationError("SSO state secret is not configured")
        if self.expires_in_minutes <= 0:
            raise SsoProviderConfigurationError(
                "SSO transaction expiry must be greater than zero"
            )
