"""Tenant-owned document retention policy."""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_retention_policies_tenant"),
        CheckConstraint(
            "document_retention_days IS NULL OR document_retention_days >= 1",
            name="ck_retention_policies_document_days_positive",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # NULL deliberately means the organization has not enabled automatic
    # source-document expiry. It is not silently interpreted as a default.
    document_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tenant: Mapped["Tenant"] = relationship()
