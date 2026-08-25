"""add audit read permission

Revision ID: b7d3e1f9a4c2
Revises: a9c2e7f4b6d1
Create Date: 2026-08-26 00:00:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d3e1f9a4c2"
down_revision: Union[str, None] = "a9c2e7f4b6d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSION_CODE = "audit:read"
ADMINISTRATOR_ROLE = "administrator"


def upgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
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
        [{
            "code": PERMISSION_CODE,
            "description": "View the immutable security audit trail.",
            "created_at": now,
            "updated_at": now,
        }],
    )
    op.execute(
        role_permissions.insert().from_select(
            ["role_id", "permission_id", "created_at", "updated_at"],
            sa.select(roles.c.id, permissions.c.id, sa.literal(now), sa.literal(now))
            .select_from(roles.join(permissions, sa.true()))
            .where(roles.c.name == ADMINISTRATOR_ROLE, permissions.c.code == PERMISSION_CODE),
        )
    )


def downgrade() -> None:
    permissions = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String))
    role_permissions = sa.table(
        "role_permissions",
        sa.column("permission_id", sa.Integer),
    )
    permission_ids = sa.select(permissions.c.id).where(permissions.c.code == PERMISSION_CODE)
    op.execute(role_permissions.delete().where(role_permissions.c.permission_id.in_(permission_ids)))
    op.execute(permissions.delete().where(permissions.c.code == PERMISSION_CODE))
