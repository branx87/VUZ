"""
Планировщик напоминаний о событиях.

Логика: для каждого активного события, до которого осталось N дней (N из event.notify_days_before),
ежедневно в 09:00 (по локали SCHEDULER_TIMEZONE) проверяем, пора ли слать напоминание
этому конкретному пользователю. Дедупликация — через NotificationLog.

Запускается в lifespan FastAPI.
"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.models import Event, Message, NotificationLog, User
from app.services.broadcast import broadcast_telegram, broadcast_vk
from sqlalchemy import select

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _now_in_tz() -> datetime:
    tz = ZoneInfo(settings.scheduler_timezone)
    return datetime.now(tz)


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.scheduler_timezone)


async def _has_log(
    session: AsyncSession, *, event_id: int, user_id: int, days_before: int
) -> bool:
    """Уже отправляли этому юзеру напоминание за `days_before` дней по этому событию?"""
    stmt = select(NotificationLog.id).where(
        NotificationLog.event_id == event_id,
        NotificationLog.user_id == user_id,
        NotificationLog.notification_type == "event_reminder",
        NotificationLog.days_before == days_before,
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _log(
    session: AsyncSession,
    *,
    event: Event,
    user: User,
    days_before: int,
    status: str,
    error_msg: str | None = None,
) -> None:
    """Старая запись для дедупа и истории доставок. Лента чата — отдельная запись в messages."""
    session.add(
        NotificationLog(
            event_id=event.id,
            user_id=user.id,
            notification_type="event_reminder",
            days_before=days_before,
            status=status,
            error_msg=error_msg,
        )
    )
    await session.commit()


async def _record_event_reminder(
    session: AsyncSession,
    *,
    event: Event,
    days_before: int,
    text: str,
    delivered_count: int,
) -> None:
    """Одна запись в `messages` для ленты чата."""
    session.add(
        Message(
            message_type="event_reminder",
            text_preview=text[:500],
            event_id=event.id,
            days_before=days_before,
            delivered_count=delivered_count,
        )
    )
    await session.commit()


def _format_reminder(event: Event, days_before: int) -> str:
    when = event.event_date.strftime("%d.%m.%Y")
    if event.event_time:
        when += f" в {event.event_time.strftime('%H:%M')}"
    head = "🔔 <b>Напоминание</b>\n\n"
    body = f"📌 <b>{event.title}</b>\n📅 {when}"
    if days_before == 0:
        return head + body + "\n\n<i>Сегодня!</i>"
    if days_before == 1:
        return head + body + "\n\n<i>Завтра</i>"
    return head + body + f"\n\n<i>Через {days_before} дн.</i>"


async def _send_event_reminders(bot: Bot | None) -> None:
    """Основная задача: разослать напоминания тем, кому они положены сегодня.

    Один юзер получает максимум одно напоминание о событии за N дней — независимо от
    того, на скольких платформах он есть. Если на нескольких — шлём во все.

    По итогам рассылки пишет ОДНУ запись в `messages` (для ленты чата).
    """
    today = _now_in_tz().date()
    async with AsyncSessionLocal() as session:
        events = (
            await session.execute(
                select(Event).where(Event.is_active == True, Event.event_date >= today)
            )
        ).scalars().all()

        if not events:
            return

        for ev in events:
            days_left = (ev.event_date - today).days
            if days_left not in (ev.notify_days_before or []):
                continue

            users = (
                await session.execute(
                    select(User).where(User.notifications_enabled == True)
                )
            ).scalars().all()

            text = _format_reminder(ev, days_left)
            delivered_count = 0

            for user in users:
                types = user.notification_types or {}
                if not types.get("event_reminder", True):
                    continue
                if await _has_log(
                    session, event_id=ev.id, user_id=user.id, days_before=days_left
                ):
                    continue
                sent_ok = False
                if user.telegram_user_id and bot:
                    try:
                        await bot.send_message(int(user.telegram_user_id), text)
                        sent_ok = True
                    except Exception as exc:
                        logger.warning(
                            "reminder (tg) failed: event=%d user=%s: %s",
                            ev.id, user.telegram_user_id, exc,
                        )
                if user.vk_user_id:
                    try:
                        from app.integrations.vk.api import vk_api
                        await vk_api.send_message(int(user.vk_user_id), text)
                        sent_ok = True
                    except Exception as exc:
                        logger.warning(
                            "reminder (vk) failed: event=%d user=%s: %s",
                            ev.id, user.vk_user_id, exc,
                        )
                if sent_ok:
                    await _log(
                        session, event=ev, user=user, days_before=days_left, status="sent"
                    )
                    delivered_count += 1

            if delivered_count > 0:
                await _record_event_reminder(
                    session,
                    event=ev,
                    days_before=days_left,
                    text=text,
                    delivered_count=delivered_count,
                )


def start_scheduler(bot: Bot | None) -> AsyncIOScheduler:
    """Поднимает AsyncIOScheduler и регистрирует ежедневную задачу.
    Возвращает запущенный scheduler (для остановки в lifespan)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    # Каждый день в 09:00 локального времени
    _scheduler.add_job(
        _send_event_reminders,
        CronTrigger(hour=9, minute=0),
        args=[bot],
        id="send_event_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler started (timezone=%s)", settings.scheduler_timezone)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


async def run_now(bot: Bot | None = None) -> int:
    """Утилита для отладки: прогнать задачу немедленно, вернуть число отправленных."""
    await _send_event_reminders(bot)
    return 0
