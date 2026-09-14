"""add_is_active_subjects_teachers

Revision ID: c1d2e3f4a5b6
Revises: 8dd30d3ee1fa
Create Date: 2026-04-24 20:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = '8dd30d3ee1fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subjects', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('teachers', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('teachers', 'is_active')
    op.drop_column('subjects', 'is_active')
