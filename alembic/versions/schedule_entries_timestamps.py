"""schedule_entries timestamps

Revision ID: schedule_entries_timestamps
Revises: password_reset_codes
Create Date: 2026-09-15 14:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "schedule_entries_timestamps"
down_revision: Union[str, None] = "password_reset_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedule_entries",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "schedule_entries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_entries", "updated_at")
    op.drop_column("schedule_entries", "created_at")
