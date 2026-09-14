"""schedule_session_week

Revision ID: d2e3f4a5b6c1
Revises: c1d2e3f4a5b6
Create Date: 2026-04-24 20:01:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2e3f4a5b6c1'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schedule_entries', sa.Column('session_week', sa.Date(), nullable=True))
    # Set existing rows to the Monday of the current week
    op.execute(
        "UPDATE schedule_entries SET session_week = date_trunc('week', CURRENT_DATE)::date"
    )
    op.alter_column('schedule_entries', 'session_week', nullable=False)
    op.drop_column('schedule_entries', 'week_type')


def downgrade() -> None:
    op.add_column('schedule_entries', sa.Column(
        'week_type', sa.String(length=10), nullable=False, server_default='all'
    ))
    op.drop_column('schedule_entries', 'session_week')
