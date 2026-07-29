from dataclasses import dataclass
from enum import StrEnum


class ProviderName(StrEnum):
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"


@dataclass(frozen=True)
class ProviderTokens:
    access_token: str
    id_token: str | None = None


@dataclass(frozen=True)
class ProviderIdentity:
    provider: ProviderName
    subject: str
    email: str | None
    email_verified: bool
    full_name: str | None
