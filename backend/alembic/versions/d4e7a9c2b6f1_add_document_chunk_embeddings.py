"""add document chunk embeddings

Revision ID: d4e7a9c2b6f1
Revises: c8f6a2d9e4b1
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e7a9c2b6f1"
down_revision: Union[str, Sequence[str], None] = "c8f6a2d9e4b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_chunk_embeddings",
        sa.Column("document_chunk_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("point_id", sa.String(length=36), nullable=False),
        sa.Column("vector_dimension", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "vector_dimension > 0",
            name="ck_document_chunk_embeddings_dimension_positive",
        ),
        sa.CheckConstraint(
            "length(point_id) = 36",
            name="ck_document_chunk_embeddings_point_id_uuid_length",
        ),
        sa.ForeignKeyConstraint(
            ["document_chunk_id"],
            ["document_chunks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_chunk_id",
            "provider",
            "model",
            "collection_name",
            name="uq_document_chunk_embeddings_chunk_provider_model_collection",
        ),
        sa.UniqueConstraint(
            "collection_name",
            "point_id",
            name="uq_document_chunk_embeddings_collection_point_id",
        ),
    )
    op.create_index(
        "ix_document_chunk_embeddings_chunk_id",
        "document_chunk_embeddings",
        ["document_chunk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunk_embeddings_chunk_id", table_name="document_chunk_embeddings")
    op.drop_table("document_chunk_embeddings")
