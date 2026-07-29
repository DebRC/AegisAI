from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.external_identity import ExternalIdentity


class ExternalIdentityRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, identity: ExternalIdentity) -> ExternalIdentity:
        self.db.add(identity)
        self.db.flush()
        self.db.refresh(identity)
        return identity

    def get_by_provider_and_subject(
        self,
        provider: str,
        provider_subject: str,
    ) -> ExternalIdentity | None:
        return self.db.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == provider,
                ExternalIdentity.provider_subject == provider_subject,
            )
        )

    def list_by_user_id(self, user_id: int) -> list[ExternalIdentity]:
        return list(
            self.db.scalars(
                select(ExternalIdentity)
                .where(ExternalIdentity.user_id == user_id)
                .order_by(ExternalIdentity.provider, ExternalIdentity.id)
            )
        )
