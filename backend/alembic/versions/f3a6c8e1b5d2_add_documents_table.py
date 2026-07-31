"""add documents table

Revision ID: f3a6c8e1b5d2
Revises: e2d5a9c8f7b4
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a6c8e1b5d2"
down_revision: Union[str, Sequence[str], None] = "e2d5a9c8f7b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_status = sa.Enum(
    "pending",
    "processing",
    "ready",
    "failed",
    name="document_status",
)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("uploader_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            document_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("processing_error", sa.String(length=1000), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index(
        "ix_documents_uploader_user_id",
        "documents",
        ["uploader_user_id"],
    )
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_documents_deleted_at_created_at",
        "documents",
        ["deleted_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at_created_at", table_name="documents")
    op.drop_index("ix_documents_status_created_at", table_name="documents")
    op.drop_index("ix_documents_uploader_user_id", table_name="documents")
    op.drop_table("documents")
    document_status.drop(op.get_bind(), checkfirst=False)
