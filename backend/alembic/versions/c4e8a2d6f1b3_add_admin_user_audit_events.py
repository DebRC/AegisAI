"""add administrator user audit events

Revision ID: c4e8a2d6f1b3
Revises: b7d3e1f9a4c2
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4e8a2d6f1b3"
down_revision: Union[str, None] = "b7d3e1f9a4c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'admin.user.activated'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'admin.user.deactivated'")


def downgrade() -> None:
    raise NotImplementedError(
        "Audit-event enum values cannot be removed without violating append-only history."
    )
