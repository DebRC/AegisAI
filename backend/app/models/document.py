from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger
from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.db.base import Base


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        Index("ix_documents_uploader_user_id", "uploader_user_id"),
        Index("ix_documents_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_documents_status_created_at", "status", "created_at"),
        Index("ix_documents_deleted_at_created_at", "deleted_at", "created_at"),
    )

    uploader_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[DocumentStatus] = mapped_column(
        SqlEnum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
        nullable=False,
    )

    processing_error: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    uploader: Mapped["User"] = relationship(
        back_populates="uploaded_documents",
    )

    tenant: Mapped["Tenant | None"] = relationship()

    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="document",
    )

    extraction: Mapped["DocumentExtraction | None"] = relationship(
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )

    access_grants: Mapped[list["DocumentAccessGrant"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
