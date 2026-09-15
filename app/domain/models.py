"""
SQLAlchemy 2.0 ORM models. Pure data structures — no business logic here.
"""
import logging
from datetime import date, datetime, time
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# References (справочники предметов и преподавателей)
# ---------------------------------------------------------------------------

class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_user_platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))           # "telegram" | "vk"
    platform_user_id: Mapped[str] = mapped_column(String(50))   # str(chat_id) или str(vk_user_id)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # {"schedule_change": true, "event_reminder": true, "news": true}
    notification_types: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {"schedule_change": True, "event_reminder": True, "news": True},
    )

    # Web-portal auth (см. app/portal)
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_web_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # Проставляется когда админ одобрил регистрацию. До этого юзер не может войти.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notification_logs: Mapped[list["NotificationLog"]] = relationship(back_populates="user")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

class ScheduleEntry(Base):
    """Базовое еженедельное расписание."""
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 0=Пн, 1=Вт, ..., 5=Сб, 6=Вс
    day_of_week: Mapped[int] = mapped_column(Integer)
    # Номер пары (1-8)
    pair_number: Mapped[int] = mapped_column(Integer)
    time_start: Mapped[time] = mapped_column(Time)
    time_end: Mapped[time] = mapped_column(Time)

    subject: Mapped[str] = mapped_column(String(200))
    teacher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    room: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # None = все подгруппы, 1 или 2 = конкретная подгруппа
    subgroup: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Понедельник учебной недели (сессии), к которой относится запись
    session_week: Mapped[date] = mapped_column(Date)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    exceptions: Mapped[list["ScheduleException"]] = relationship(back_populates="original_entry")


class ScheduleException(Base):
    """Разовые изменения к конкретной дате: отмена, замена, добавление пары."""
    __tablename__ = "schedule_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)

    # "cancel" — пара отменена
    # "replace" — замена (другой предмет / преподаватель / аудитория)
    # "add"     — добавлена пара, которой нет в базовом расписании
    exception_type: Mapped[str] = mapped_column(String(20))

    # Для cancel/replace: ссылка на отменяемую/заменяемую запись
    original_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedule_entries.id", ondelete="SET NULL"), nullable=True
    )
    original_entry: Mapped[Optional["ScheduleEntry"]] = relationship(back_populates="exceptions")

    # Данные новой/заменяющей пары (заполняются для replace и add)
    pair_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    time_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    teacher: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    room: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Materials (files & links)
# ---------------------------------------------------------------------------

class MaterialCategory(Base):
    __tablename__ = "material_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    emoji: Mapped[str] = mapped_column(String(10), default="📁")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    materials: Mapped[list["Material"]] = relationship(
        back_populates="category", order_by="Material.sort_order"
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("material_categories.id"))
    category: Mapped["MaterialCategory"] = relationship(back_populates="materials")

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "file" | "link"
    material_type: Mapped[str] = mapped_column(String(10))

    # Для ссылок
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # Для файлов — путь на диске относительно FILES_DIR
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes

    # Кэш platform-специфичных ID, чтобы не перезагружать файл при каждой отправке
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    vk_doc_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Events & Notifications
# ---------------------------------------------------------------------------

class Event(Base):
    """Событие, о котором нужно уведомить студентов."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Список целых чисел: за сколько дней до события слать напоминание
    # Например [3, 1] — за 3 дня и за 1 день
    notify_days_before: Mapped[list] = mapped_column(JSON, default=lambda: [3, 1])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    notification_logs: Mapped[list["NotificationLog"]] = relationship(back_populates="event")


class NotificationLog(Base):
    """Аудит отправленных уведомлений — чтобы не слать дважды."""
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[Optional["Event"]] = relationship(back_populates="notification_logs")

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped["User"] = relationship(back_populates="notification_logs")

    # "event_reminder" | "schedule_change" | "news"
    notification_type: Mapped[str] = mapped_column(String(50))

    # Для event_reminder: за сколько дней было отправлено
    days_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # "sent" | "failed"
    status: Mapped[str] = mapped_column(String(20), default="sent")
    error_msg: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


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
