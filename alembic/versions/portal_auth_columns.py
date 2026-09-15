"""portal auth columns

Revision ID: portal_auth_columns
Revises: d2e3f4a5b6c1
Create Date: 2026-09-15 05:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "portal_auth_columns"
down_revision: Union[str, None] = "d2e3f4a5b6c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("is_web_active", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "is_web_active")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
