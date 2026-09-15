"""sync schema to models (idempotent, root migration)

Revision ID: sync_schema_to_models
Revises:
Create Date: 2026-09-15 15:00:00.000000

Единственная миграция в проекте. Приводит БД в соответствие с
актуальной моделью app/domain/models.py. Все операции идемпотентны
(IF NOT EXISTS), можно запускать много раз.

Для свежего деплоя: применить один раз — `alembic upgrade head`.
Для существующей БД: можно либо прогнать эту миграцию (дотянет до модели),
либо `alembic stamp head` (просто отметить, что БД уже в нужном состоянии).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "sync_schema_to_models"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # schedule_entries — мог не быть created_at, updated_at, session_week
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE schedule_entries "
        "ADD COLUMN IF NOT EXISTS session_week DATE"
    )
    # Если session_week был NULL после добавления — заполним понедельником текущей недели.
    op.execute(
        "UPDATE schedule_entries SET session_week = date_trunc('week', CURRENT_DATE)::date "
        "WHERE session_week IS NULL"
    )
    op.execute(
        "ALTER TABLE schedule_entries "
        "ALTER COLUMN session_week SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE schedule_entries "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE schedule_entries "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )

    # -------------------------------------------------------------------------
    # schedule_exceptions — может не быть subgroup
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE schedule_exceptions "
        "ADD COLUMN IF NOT EXISTS subgroup INTEGER"
    )

    # -------------------------------------------------------------------------
    # events — может не быть updated_at
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE events "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )

    # -------------------------------------------------------------------------
    # users — может не быть полного набора web-полей
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS telegram_user_id VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS vk_user_id VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS vk_username VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS full_name VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS email VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS password_hash VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS is_web_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    # Уникальные констрейнты (создаются только если их ещё нет).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram "
        "ON users(telegram_user_id) WHERE telegram_user_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_vk "
        "ON users(vk_user_id) WHERE vk_user_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
        "ON users(email) WHERE email IS NOT NULL"
    )

    # -------------------------------------------------------------------------
    # materials — может не быть file_size / sort_order / is_visible / file_path / file_name
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS file_path VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS file_name VARCHAR(300)"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS file_size INTEGER"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS telegram_file_id VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS vk_doc_id VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE materials "
        "ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT TRUE"
    )

    # -------------------------------------------------------------------------
    # material_categories — может не быть sort_order / emoji
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE material_categories "
        "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE material_categories "
        "ADD COLUMN IF NOT EXISTS emoji VARCHAR(10) NOT NULL DEFAULT '📁'"
    )

    # -------------------------------------------------------------------------
    # subjects — таблица может вообще не существовать
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            short_name VARCHAR(50),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Если таблица уже была без колонок — добавляем недостающие.
    op.execute(
        "ALTER TABLE subjects "
        "ADD COLUMN IF NOT EXISTS short_name VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE subjects "
        "ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE subjects "
        "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
    )

    # -------------------------------------------------------------------------
    # teachers — аналогично
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS teachers (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(200) NOT NULL,
            short_name VARCHAR(200),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "ALTER TABLE teachers "
        "ADD COLUMN IF NOT EXISTS short_name VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE teachers "
        "ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "ALTER TABLE teachers "
        "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
    )

    # -------------------------------------------------------------------------
    # notification_logs — может не быть error_msg / notification_type / status
    # -------------------------------------------------------------------------
    op.execute(
        "ALTER TABLE notification_logs "
        "ADD COLUMN IF NOT EXISTS notification_type VARCHAR(50) NOT NULL DEFAULT 'event_reminder'"
    )
    op.execute(
        "ALTER TABLE notification_logs "
        "ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'sent'"
    )
    op.execute(
        "ALTER TABLE notification_logs "
        "ADD COLUMN IF NOT EXISTS error_msg VARCHAR(500)"
    )

    # -------------------------------------------------------------------------
    # password_reset_codes — таблица может не существовать
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_codes (
            id SERIAL PRIMARY KEY,
            email VARCHAR(200) NOT NULL,
            code_hash VARCHAR(200) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_password_reset_codes_email "
        "ON password_reset_codes(email)"
    )


def downgrade() -> None:
    # Откатываем в обратном порядке.
    op.execute("DROP TABLE IF EXISTS password_reset_codes")
    op.execute("ALTER TABLE notification_logs DROP COLUMN IF EXISTS error_msg")
    op.execute("ALTER TABLE notification_logs DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE notification_logs DROP COLUMN IF EXISTS notification_type")
    op.execute("DROP TABLE IF EXISTS teachers")
    op.execute("DROP TABLE IF EXISTS subjects")
    op.execute("ALTER TABLE material_categories DROP COLUMN IF EXISTS emoji")
    op.execute("ALTER TABLE material_categories DROP COLUMN IF EXISTS sort_order")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS is_visible")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS sort_order")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS vk_doc_id")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS telegram_file_id")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS file_size")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS file_name")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS file_path")
    op.execute("DROP INDEX IF EXISTS uq_users_email")
    op.execute("DROP INDEX IF EXISTS uq_users_vk")
    op.execute("DROP INDEX IF EXISTS uq_users_telegram")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_web_active")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS full_name")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS vk_username")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS vk_user_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS telegram_username")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS telegram_user_id")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE schedule_exceptions DROP COLUMN IF EXISTS subgroup")
    op.execute("ALTER TABLE schedule_entries DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE schedule_entries DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE schedule_entries DROP COLUMN IF EXISTS session_week")
