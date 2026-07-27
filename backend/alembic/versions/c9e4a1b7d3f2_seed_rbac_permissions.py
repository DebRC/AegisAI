"""seed RBAC permissions

Revision ID: c9e4a1b7d3f2
Revises: b4f7c2d9e6a1
Create Date: 2026-07-27
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e4a1b7d3f2"
down_revision: Union[str, Sequence[str], None] = "b4f7c2d9e6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = (
    ("documents:read", "Read documents and their metadata."),
    ("documents:write", "Create, update, and delete documents."),
    ("users:read", "View users for administration."),
    ("users:manage", "Manage user accounts."),
    ("roles:read", "View roles and their permissions."),
    ("roles:manage", "Create, update, and delete roles."),
    ("roles:assign", "Assign and remove user roles."),
)
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
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
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
                "code": code,
                "description": description,
                "created_at": now,
                "updated_at": now,
            }
            for code, description in PERMISSIONS
        ],
    )
    op.bulk_insert(
        roles,
        [
            {
                "name": ADMINISTRATOR_ROLE,
                "description": "Full access to all AegisAI permissions.",
                "is_system": True,
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
                roles.c.name == ADMINISTRATOR_ROLE,
                permissions.c.code.in_([code for code, _ in PERMISSIONS]),
            ),
        )
    )


def downgrade() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer),
    )
    op.execute(
        role_permissions.delete().where(
            role_permissions.c.role_id.in_(
                sa.select(roles.c.id).where(roles.c.name == ADMINISTRATOR_ROLE)
            )
        )
    )
    op.execute(
        roles.delete().where(roles.c.name == ADMINISTRATOR_ROLE)
    )
    op.execute(
        permissions.delete().where(
            permissions.c.code.in_([code for code, _ in PERMISSIONS])
        )
    )
