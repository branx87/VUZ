"""SQLAlchemy ORM-модели для приложения."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Один пользователь = одна строка. Платформенные ID — отдельные колонки."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", name="uq_users_telegram"),
        UniqueConstraint("vk_user_id", name="uq_users_vk"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Идентификаторы на платформах (любая комбинация может быть заполнена).
    telegram_user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vk_user_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vk_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Отображаемое имя (заполняется по мере того, как человек становится известен).
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Web-портал.
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_web_active: Mapped[bool] = mapped_column(Boolean, default=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # {"schedule_change": true, "event_reminder": true, "news": true}
    notification_types: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"schedule_change": True, "event_reminder": True, "news": True},
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notification_logs: Mapped[list["NotificationLog"]] = relationship(back_populates="user")


class NotificationLog(Base):
    """Лог отправленных уведомлений — для дедупликации и отладки."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id"), nullable=True)
    notification_type: Mapped[str] = mapped_column(String(50))
    days_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # "sent" / "failed"
    error_msg: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="notification_logs")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    event_date: Mapped[datetime] = mapped_column(DateTime)
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    notify_days_before: Mapped[list] = mapped_column(
        JSON, default=lambda: [3, 1]
    )  # [3, 1] = за 3 и 1 день
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterialCategory(Base):
    __tablename__ = "material_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    emoji: Mapped[str] = mapped_column(String(10), default="📁")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    materials: Mapped[list["Material"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("material_categories.id", ondelete="CASCADE")
    )

    title: Mapped[str] = mapped_column(String(300))
    # "link" или "file"
    material_type: Mapped[str] = mapped_column(String(20), default="link")
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Для material_type="file":
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    vk_doc_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped["MaterialCategory"] = relationship(back_populates="materials")


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_week: Mapped[datetime] = mapped_column(DateTime)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0..6
    pair_number: Mapped[int] = mapped_column(Integer)  # 1..N
    time_start: Mapped[datetime] = mapped_column(DateTime)
    time_end: Mapped[datetime] = mapped_column(DateTime)

    subject: Mapped[str] = mapped_column(String(200))
    teacher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    room: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subgroup: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScheduleException(Base):
    """Замена / отмена пары в конкретную дату."""

    __tablename__ = "schedule_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime)
    exception_type: Mapped[str] = mapped_column(String(20))  # "replace" | "cancel"
    original_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_entries.id", ondelete="SET NULL"), nullable=True
    )

    # Поля для замены:
    pair_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    time_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    teacher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    room: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subgroup: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Cross-posting
# ---------------------------------------------------------------------------

class CrosspostMessage(Base):
    """
    Таблица дедупликации кросспостинга.
    Когда платформа B получает вебхук на сообщение, которое мы сами же туда отправили
    с платформы A, мы не должны снова его пересылать обратно на A.
    Проверяем по deduplication_key = sha256(нормализованный текст).
    """
    __tablename__ = "crosspost_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_platform: Mapped[str] = mapped_column(String(20))       # "telegram" | "vk"
    source_message_id: Mapped[str] = mapped_column(String(100))    # str(message_id)
    target_platform: Mapped[str] = mapped_column(String(20))
    target_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # SHA-256 от нормализованного текста — ключ дедупликации
    deduplication_key: Mapped[str] = mapped_column(String(64), index=True)
    content_preview: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Password reset codes
# ---------------------------------------------------------------------------

class PasswordResetCode(Base):
    """Одноразовый код восстановления пароля, отправляется через бота."""
    __tablename__ = "password_reset_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    # bcrypt-хеш кода; сам код в БД не хранится.
    code_hash: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
