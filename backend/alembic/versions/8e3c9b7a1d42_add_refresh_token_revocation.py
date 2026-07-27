"""add refresh token revocation

Revision ID: 8e3c9b7a1d42
Revises: 65019876fd83
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8e3c9b7a1d42"
down_revision: Union[str, Sequence[str], None] = "65019876fd83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "revoked_at")
