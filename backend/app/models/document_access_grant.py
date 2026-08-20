"""Direct user-to-document access grants for Phase 12 resource authorization."""

from enum import Enum

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class DocumentAccessLevel(str, Enum):
    READ = "read"
    WRITE = "write"


class DocumentAccessGrant(Base):
    """One current direct grant for one user and one active document."""

    __tablename__ = "document_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_access_grants_document_id_user_id",
        ),
        Index(
            "ix_document_access_grants_user_id_document_id",
            "user_id",
            "document_id",
        ),
        Index(
            "ix_document_access_grants_granted_by_user_id",
            "granted_by_user_id",
        ),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    access_level: Mapped[DocumentAccessLevel] = mapped_column(
        SqlEnum(
            DocumentAccessLevel,
            name="document_access_level",
            values_callable=lambda levels: [level.value for level in levels],
        ),
        nullable=False,
    )

    granted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        back_populates="access_grants",
    )

    grantee: Mapped["User"] = relationship(
        back_populates="document_access_grants",
        foreign_keys=[user_id],
    )

    granted_by: Mapped["User"] = relationship(
        back_populates="granted_document_access_grants",
        foreign_keys=[granted_by_user_id],
    )
