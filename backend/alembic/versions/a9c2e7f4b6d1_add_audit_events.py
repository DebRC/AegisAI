"""add immutable audit events

Revision ID: a9c2e7f4b6d1
Revises: f6a9d2e4c8b1
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9c2e7f4b6d1"
down_revision: Union[str, None] = "f6a9d2e4c8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


audit_event_outcome = sa.Enum(
    "succeeded",
    "denied",
    "failed",
    name="audit_event_outcome",
)

audit_event_type = sa.Enum(
    "auth.login.succeeded",
    "auth.login.failed",
    "auth.sso.succeeded",
    "auth.sso.failed",
    "auth.refresh.succeeded",
    "auth.refresh.failed",
    "auth.logout.succeeded",
    "rbac.role.created",
    "rbac.role.deleted",
    "rbac.role_permission.granted",
    "rbac.role_permission.revoked",
    "rbac.user_role.assigned",
    "rbac.user_role.removed",
    "document.uploaded",
    "document.renamed",
    "document.deleted",
    "document.reprocess_queued",
    "document.access_grant.created",
    "document.access_grant.updated",
    "document.access_grant.revoked",
    "document.read",
    "retrieval.search",
    "chat.request",
    name="audit_event_type",
)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", audit_event_type, nullable=False),
        sa.Column("outcome", audit_event_outcome, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(target_type IS NULL) = (target_id IS NULL)",
            name="ck_audit_events_target_fields_paired",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index(
        "ix_audit_events_actor_user_id_occurred_at",
        "audit_events",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_target_type_target_id_occurred_at",
        "audit_events",
        ["target_type", "target_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_event_type_occurred_at",
        "audit_events",
        ["event_type", "occurred_at"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION prevent_audit_event_mutation()")
    op.drop_index("ix_audit_events_event_type_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_target_type_target_id_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
    audit_event_type.drop(op.get_bind(), checkfirst=False)
    audit_event_outcome.drop(op.get_bind(), checkfirst=False)
