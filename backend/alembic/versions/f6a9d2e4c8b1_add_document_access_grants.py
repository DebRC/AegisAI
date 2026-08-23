"""add document access grants

Revision ID: f6a9d2e4c8b1
Revises: e5f8b1c3d7a2
Create Date: 2026-08-20 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a9d2e4c8b1"
down_revision: Union[str, None] = "e5f8b1c3d7a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_access_level = sa.Enum(
    "read",
    "write",
    name="document_access_level",
)


def upgrade() -> None:
    op.create_table(
        "document_access_grants",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_level", document_access_level, nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_access_grants_document_id_user_id",
        ),
    )
    op.create_index(
        "ix_document_access_grants_user_id_document_id",
        "document_access_grants",
        ["user_id", "document_id"],
    )
    op.create_index(
        "ix_document_access_grants_granted_by_user_id",
        "document_access_grants",
        ["granted_by_user_id"],
    )

    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
        sa.column("permission_id", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)

    op.bulk_insert(
        permissions,
        [
            {
                "code": "documents:manage",
                "description": "Manage access to every document.",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.execute(
        role_permissions.insert().from_select(
            ["role_id", "permission_id", "created_at", "updated_at"],
            sa.select(
                roles.c.id,
                permissions.c.id,
                sa.literal(now),
                sa.literal(now),
            )
            .select_from(roles.join(permissions, sa.true()))
            .where(
                roles.c.name == "administrator",
                permissions.c.code == "documents:manage",
            ),
        )
    )


def downgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("permission_id", sa.Integer),
    )
    op.execute(
        role_permissions.delete().where(
            role_permissions.c.permission_id.in_(
                sa.select(permissions.c.id).where(
                    permissions.c.code == "documents:manage"
                )
            )
        )
    )
    op.execute(
        permissions.delete().where(permissions.c.code == "documents:manage")
    )
    op.drop_index(
        "ix_document_access_grants_granted_by_user_id",
        table_name="document_access_grants",
    )
    op.drop_index(
        "ix_document_access_grants_user_id_document_id",
        table_name="document_access_grants",
    )
    op.drop_table("document_access_grants")
    document_access_level.drop(op.get_bind(), checkfirst=False)
