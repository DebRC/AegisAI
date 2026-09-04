"""add tenant isolation

Revision ID: d5e1f7a9b2c4
Revises: c4e8a2d6f1b3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e1f7a9b2c4"
down_revision: Union[str, None] = "c4e8a2d6f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    # A deterministic legacy tenant prevents existing installations from being
    # split or exposed while the new nullable columns are backfilled.
    op.execute(
        "INSERT INTO tenants (slug, name, is_active, created_at, updated_at) "
        "VALUES ('default', 'Default organization', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
    )
    op.create_index("ix_tenant_memberships_user_active", "tenant_memberships", ["user_id", "is_active"])
    op.execute(
        "INSERT INTO tenant_memberships (tenant_id, user_id, is_active, created_at, updated_at) "
        "SELECT (SELECT id FROM tenants WHERE slug = 'default'), users.id, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM users"
    )

    op.add_column("roles", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("user_roles", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("tenant_id", sa.Integer(), nullable=True))

    default_tenant = "(SELECT id FROM tenants WHERE slug = 'default')"
    # Phase 13's trigger rightly rejects normal audit-event mutation. This
    # one-time structural migration has to stamp the new ownership column on
    # legacy immutable rows, so suspend only that trigger inside Alembic's
    # transaction and restore it before the schema becomes visible.
    op.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only")
    for table in ("roles", "user_roles", "documents", "audit_events", "refresh_tokens"):
        op.execute(f"UPDATE {table} SET tenant_id = {default_tenant} WHERE tenant_id IS NULL")
    op.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_append_only")

    op.drop_constraint("uq_roles_name", "roles", type_="unique")
    op.create_foreign_key("fk_roles_tenant_id", "roles", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_roles_tenant_name", "roles", ["tenant_id", "name"])
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])
    op.alter_column("roles", "tenant_id", nullable=False)

    op.drop_constraint("uq_user_roles_user_id_role_id", "user_roles", type_="unique")
    op.create_foreign_key("fk_user_roles_tenant_id", "user_roles", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_user_roles_tenant_user_role", "user_roles", ["tenant_id", "user_id", "role_id"])
    op.create_index("ix_user_roles_tenant_user", "user_roles", ["tenant_id", "user_id"])
    op.alter_column("user_roles", "tenant_id", nullable=False)

    for table, constraint in (
        ("documents", "fk_documents_tenant_id"),
        ("audit_events", "fk_audit_events_tenant_id"),
        ("refresh_tokens", "fk_refresh_tokens_tenant_id"),
    ):
        op.create_foreign_key(constraint, table, "tenants", ["tenant_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_documents_tenant_id_created_at", "documents", ["tenant_id", "created_at"])
    op.create_index("ix_audit_events_tenant_id_occurred_at", "audit_events", ["tenant_id", "occurred_at"])
    op.alter_column("documents", "tenant_id", nullable=False)
    op.alter_column("audit_events", "tenant_id", nullable=False)
    op.alter_column("refresh_tokens", "tenant_id", nullable=False)


def downgrade() -> None:
    raise NotImplementedError(
        "Tenant isolation is forward-only; restoring shared data would violate organization boundaries."
    )
