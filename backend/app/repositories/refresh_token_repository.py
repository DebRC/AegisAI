from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, refresh_token: RefreshToken) -> RefreshToken:

        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)

        return refresh_token

    def get_by_token(
        self,
        token: str,
    ) -> RefreshToken | None:

        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token == token)
        )

        return self.db.scalar(stmt)

    def delete(
        self,
        refresh_token: RefreshToken,
    ) -> None:

        self.db.delete(refresh_token)
        self.db.commit()

    def delete_expired(
        self,
        now: datetime,
    ) -> int:

        expired = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.expires_at < now
            )
            .all()
        )

        count = len(expired)

        for token in expired:
            self.db.delete(token)

        self.db.commit()

        return count