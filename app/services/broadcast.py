"""
Сервис рассылки сообщений подписчикам бота.

В Telegram-варианте используется aiogram.Bot, в VK — тонкая обёртка над httpx.
Лимиты Telegram (~30 msg/s) и VK (~3 msg/s) — отдельные; сервис берёт их
на себя через asyncio.Semaphore и обработку RetryAfter.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.models import NotificationLog
from app.integrations.vk.api import VKApi, vk_api as default_vk_api
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)

_BROADCAST_LOG_TYPE = "news"


async def _send_with_retry(
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 3,
) -> tuple[bool, str | None]:
    """Отправляет сообщение с ретраем на TelegramRetryAfter (3 попытки).
    Возвращает (success, error_text_or_None)."""
    last_err: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await coro_factory()
            return True, None
        except TelegramRetryAfter as exc:
            wait = exc.retry_after + 1
            logger.warning("Telegram RetryAfter %s sec, waiting", wait)
            last_err = f"retry_after: {wait}"
            await asyncio.sleep(wait)
        except Exception as exc:
            last_err = str(exc)[:500]
            logger.warning("send failed (attempt %d/%d): %s", attempt, max_attempts, exc)
            if attempt == max_attempts:
                return False, last_err
            await asyncio.sleep(0.5)
    return False, last_err


async def _log_combined_broadcast(
    *,
    by_user: dict[int, dict[str, tuple[bool, str | None]]],
    text_preview: str | None,
) -> None:
    """Одна запись на юзера: считаем доставленным если хотя бы на одной платформе ok.
    text_preview для всех одинаковый — берётся один раз из аргумента."""
    if not by_user:
        return
    preview = text_preview[:500] if text_preview else None
    async with AsyncSessionLocal() as session:
        for user_id, platforms in by_user.items():
            # Если хоть одна платформа доставила — статус "sent". Иначе "failed".
            sent_ok = any(ok for ok, _ in platforms.values())
            # Текст ошибки — от первой упавшей платформы (если есть).
            err: str | None = next(
                (e for ok, e in platforms.values() if not ok and e), None
            )
            session.add(
                NotificationLog(
                    user_id=user_id,
                    notification_type=_BROADCAST_LOG_TYPE,
                    status="sent" if sent_ok else "failed",
                    error_msg=err,
                    text_preview=preview,
                )
            )
        await session.commit()


async def broadcast_telegram(
    bot: Bot, text: str, *, concurrency: int = 25
) -> dict[int, tuple[bool, str | None]]:
    """Шлёт текст всем Telegram-подписчикам, уважая RetryAfter.
    Возвращает {user_id: (ok, err)} — без записи в NotificationLog; её пишет broadcast_all.
    """
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_all_telegram()

    sem = asyncio.Semaphore(concurrency)

    async def _one(user) -> tuple[int | None, bool, str | None]:
        async with sem:
            ok, err = await _send_with_retry(
                lambda: bot.send_message(int(user.telegram_user_id), text)
            )
            return user.id, ok, err

    raw = await asyncio.gather(*[_one(u) for u in users], return_exceptions=False)
    out: dict[int, tuple[bool, str | None]] = {
        uid: (ok, err) for uid, ok, err in raw if uid is not None
    }
    sent = sum(1 for ok, _ in out.values() if ok)
    failed = len(out) - sent
    logger.info("TG broadcast done: sent=%d failed=%d (users=%d)", sent, failed, len(users))
    return out


async def broadcast_vk(
    text: str,
    *,
    vk_api: VKApi | None = None,
    concurrency: int = 3,
) -> dict[int, tuple[bool, str | None]]:
    """Шлёт текст всем VK-подписчикам.
    Возвращает {user_id: (ok, err)} — без записи в NotificationLog; её пишет broadcast_all.
    """
    api = vk_api or default_vk_api
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_all_vk()

    sem = asyncio.Semaphore(concurrency)

    async def _one(user) -> tuple[int | None, bool, str | None]:
        async with sem:
            try:
                await api.send_message(int(user.vk_user_id), text)
                return user.id, True, None
            except Exception as exc:
                logger.warning("VK broadcast failed for user %s: %s", user.vk_user_id, exc)
                return user.id, False, str(exc)[:500]

    raw = await asyncio.gather(*[_one(u) for u in users], return_exceptions=False)
    out: dict[int, tuple[bool, str | None]] = {
        uid: (ok, err) for uid, ok, err in raw if uid is not None
    }
    sent = sum(1 for ok, _ in out.values() if ok)
    failed = len(out) - sent
    logger.info("VK broadcast done: sent=%d failed=%d (users=%d)", sent, failed, len(users))
    return out


async def broadcast_all(bot: Bot, text: str) -> dict[str, tuple[int, int]]:
    """Рассылает по всем платформам параллельно. Возвращает {platform: (sent, failed)}.

    Запись в NotificationLog — ровно одна на юзера (даже если у него и TG, и VK).
    Статус — "sent" если доставлено хотя бы на одной платформе.
    """
    tg_task = broadcast_telegram(bot, text)
    vk_task = broadcast_vk(text)
    tg_results, vk_results = await asyncio.gather(tg_task, vk_task)

    # Объединяем результаты по user_id.
    by_user: dict[int, dict[str, tuple[bool, str | None]]] = {}
    for uid, res in tg_results.items():
        by_user.setdefault(uid, {})["telegram"] = res
    for uid, res in vk_results.items():
        by_user.setdefault(uid, {})["vk"] = res

    await _log_combined_broadcast(by_user=by_user, text_preview=text)

    tg_sent = sum(1 for ok, _ in tg_results.values() if ok)
    vk_sent = sum(1 for ok, _ in vk_results.values() if ok)
    return {
        "telegram": (tg_sent, len(tg_results) - tg_sent),
        "vk": (vk_sent, len(vk_results) - vk_sent),
    }
