from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_user_roles_tenant_user_role"),
        Index("ix_user_roles_role_id", "role_id"),
        Index("ix_user_roles_tenant_user", "tenant_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The migration backfills every legacy assignment before making this
    # non-null in PostgreSQL. Nullable test fixtures retain prior unit coverage.
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )

    user: Mapped["User"] = relationship(
        back_populates="role_assignments",
    )

    role: Mapped["Role"] = relationship(
        back_populates="user_assignments",
    )

    tenant: Mapped["Tenant | None"] = relationship()
