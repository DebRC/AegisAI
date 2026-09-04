"""add enterprise governance

Revision ID: e7a2f9c4d6b1
Revises: d5e1f7a9b2c4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a2f9c4d6b1"
down_revision: Union[str, None] = "d5e1f7a9b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GOVERNANCE_PERMISSIONS = (
    ("api_keys:manage", "Create and revoke scoped machine credentials."),
    ("retention:manage", "Configure document retention and run retention cleanup."),
)


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=24), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_prefix"),
    )
    op.create_index("ix_api_keys_tenant_active", "api_keys", ["tenant_id", "revoked_at"])
    op.create_index("ix_api_keys_creator", "api_keys", ["created_by_user_id"])
    op.create_table(
        "retention_policies",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("document_retention_days", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document_retention_days IS NULL OR document_retention_days >= 1",
            name="ck_retention_policies_document_days_positive",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_retention_policies_tenant"),
    )

    permissions = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = sa.func.current_timestamp()
    for code, description in GOVERNANCE_PERMISSIONS:
        op.execute(
            permissions.insert().from_select(
                ["code", "description", "created_at", "updated_at"],
                sa.select(sa.literal(code), sa.literal(description), now, now).where(
                    ~sa.exists(sa.select(1).where(permissions.c.code == code))
                ),
            )
        )
    # Every tenant received an administrator clone during Phase 19. Seed the
    # new governance permissions into each protected administrator role.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at)
        SELECT roles.id, permissions.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM roles CROSS JOIN permissions
        WHERE roles.name = 'administrator'
          AND roles.is_system = true
          AND permissions.code IN ('api_keys:manage', 'retention:manage')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions
              WHERE role_permissions.role_id = roles.id
                AND role_permissions.permission_id = permissions.id
          )
        """
    )
    for value in (
        "governance.api_key.created",
        "governance.api_key.revoked",
        "governance.retention.updated",
        "governance.retention.purged",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    raise NotImplementedError(
        "Enterprise governance is forward-only because it adds immutable audit-event types."
    )
