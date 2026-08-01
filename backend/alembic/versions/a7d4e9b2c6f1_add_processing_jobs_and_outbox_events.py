"""add processing jobs and outbox events

Revision ID: a7d4e9b2c6f1
Revises: f3a6c8e1b5d2
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d4e9b2c6f1"
down_revision: Union[str, Sequence[str], None] = "f3a6c8e1b5d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


processing_job_status = sa.Enum(
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    name="processing_job_status",
)

processing_outbox_event_status = sa.Enum(
    "pending",
    "publishing",
    "published",
    "cancelled",
    name="processing_outbox_event_status",
)


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "job_type",
            sa.String(length=64),
            server_default="source_integrity",
            nullable=False,
        ),
        sa.Column(
            "status",
            processing_job_status,
            server_default="queued",
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("broker_task_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_jobs_document_id_created_at",
        "processing_jobs",
        ["document_id", "created_at"],
    )
    op.create_index(
        "ix_processing_jobs_status_queued_at",
        "processing_jobs",
        ["status", "queued_at"],
    )
    op.create_index(
        "ix_processing_jobs_broker_task_id",
        "processing_jobs",
        ["broker_task_id"],
    )

    op.create_table(
        "processing_outbox_events",
        sa.Column("processing_job_id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.String(length=100),
            server_default="processing_job.queued",
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            processing_outbox_event_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "publish_attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("broker_task_id", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_processing_outbox_events_status_available_at",
        "processing_outbox_events",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_processing_outbox_events_processing_job_id",
        "processing_outbox_events",
        ["processing_job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_outbox_events_processing_job_id",
        table_name="processing_outbox_events",
    )
    op.drop_index(
        "ix_processing_outbox_events_status_available_at",
        table_name="processing_outbox_events",
    )
    op.drop_table("processing_outbox_events")
    processing_outbox_event_status.drop(op.get_bind(), checkfirst=False)

    op.drop_index(
        "ix_processing_jobs_broker_task_id",
        table_name="processing_jobs",
    )
    op.drop_index(
        "ix_processing_jobs_status_queued_at",
        table_name="processing_jobs",
    )
    op.drop_index(
        "ix_processing_jobs_document_id_created_at",
        table_name="processing_jobs",
    )
    op.drop_table("processing_jobs")
    processing_job_status.drop(op.get_bind(), checkfirst=False)
