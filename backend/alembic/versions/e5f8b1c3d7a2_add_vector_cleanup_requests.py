"""add vector cleanup requests

Revision ID: e5f8b1c3d7a2
Revises: d4e7a9c2b6f1
Create Date: 2026-08-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f8b1c3d7a2"
down_revision: Union[str, None] = "d4e7a9c2b6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vector_cleanup_requests",
        sa.Column("processing_job_id", sa.Integer(), nullable=False),
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("point_ids", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "processing_job_id",
            name="uq_vector_cleanup_requests_processing_job_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("vector_cleanup_requests")
