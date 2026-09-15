"""users unified: per-platform IDs, single row per person

Revision ID: users_unified
Revises: portal_auth_columns
Create Date: 2026-09-15 09:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "users_unified"
down_revision: Union[str, None] = "portal_auth_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Снимаем старый (platform, platform_user_id) уникальный констрейнт.
    op.drop_constraint("uq_user_platform", "users", type_="unique")

    # 2. Добавляем per-platform поля — по одному столбцу на каждую платформу.
    op.add_column("users", sa.Column("telegram_user_id", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("vk_user_id", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("vk_username", sa.String(length=100), nullable=True))

    # 3. Уникальные констрейнты на каждой платформе отдельно (NULL допустимы).
    op.create_unique_constraint("uq_users_telegram", "users", ["telegram_user_id"])
    op.create_unique_constraint("uq_users_vk", "users", ["vk_user_id"])

    # 4. Удаляем старые общие колонки platform / platform_user_id.
    op.drop_column("users", "platform")
    op.drop_column("users", "platform_user_id")


def downgrade() -> None:
    # Возвращаем платформенные поля и констрейнты в обратном порядке.
    op.add_column("users", sa.Column("platform", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("platform_user_id", sa.String(length=50), nullable=True))

    op.drop_constraint("uq_users_vk", "users", type_="unique")
    op.drop_constraint("uq_users_telegram", "users", type_="unique")

    op.drop_column("users", "vk_username")
    op.drop_column("users", "vk_user_id")
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "telegram_user_id")

    op.create_unique_constraint(
        "uq_user_platform", "users", ["platform", "platform_user_id"]
    )
