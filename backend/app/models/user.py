from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    external_identities: Mapped[list["ExternalIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    uploaded_documents: Mapped[list["Document"]] = relationship(
        back_populates="uploader",
    )

    role_assignments: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    document_access_grants: Mapped[list["DocumentAccessGrant"]] = relationship(
        back_populates="grantee",
        foreign_keys="DocumentAccessGrant.user_id",
    )

    granted_document_access_grants: Mapped[list["DocumentAccessGrant"]] = relationship(
        back_populates="granted_by",
        foreign_keys="DocumentAccessGrant.granted_by_user_id",
    )
