"""Tenant-scoped, least-privilege machine credentials."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ApiKey(Base):
    """A hashed API credential; its plaintext value is never persisted."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_tenant_active", "tenant_id", "revoked_at"),
        Index("ix_api_keys_creator", "created_by_user_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # This non-secret lookup handle appears in audit data and helps an operator
    # identify a key without exposing enough material to authenticate.
    key_prefix: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped["Tenant"] = relationship()
    creator: Mapped["User"] = relationship(foreign_keys=[created_by_user_id])
