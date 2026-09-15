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
from app.domain.models import Message
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


async def _record_broadcast_message(
    *,
    text: str,
    delivered_count: int,
    sender_id: int | None = None,
) -> int:
    """Одна запись в `messages` на рассылку. Возвращает id."""
    async with AsyncSessionLocal() as session:
        msg = Message(
            message_type=_BROADCAST_LOG_TYPE,
            text_preview=text[:500],
            delivered_count=delivered_count,
            sender_id=sender_id,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg.id


async def broadcast_telegram(
    bot: Bot, text: str, *, concurrency: int = 25
) -> dict[int, tuple[bool, str | None]]:
    """Шлёт текст всем Telegram-подписчикам, уважая RetryAfter.
    Возвращает {user_id: (ok, err)} — без записи в БД; её пишет broadcast_all.
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
    Возвращает {user_id: (ok, err)} — без записи в БД; её пишет broadcast_all.
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


async def broadcast_all(
    bot: Bot, text: str, *, sender_id: int | None = None
) -> dict[str, tuple[int, int]]:
    """Рассылает по всем платформам параллельно. Возвращает {platform: (sent, failed)}.

    Пишет ОДНУ запись в `messages` на рассылку — независимо от числа получателей.
    `delivered_count` — сколько юзеров получили хотя бы на одной платформе.
    """
    tg_task = broadcast_telegram(bot, text)
    vk_task = broadcast_vk(text)
    tg_results, vk_results = await asyncio.gather(tg_task, vk_task)

    # Считаем уникальных доставленных юзеров (по user_id).
    delivered_user_ids: set[int] = set()
    for uid, (ok, _) in tg_results.items():
        if ok:
            delivered_user_ids.add(uid)
    for uid, (ok, _) in vk_results.items():
        if ok:
            delivered_user_ids.add(uid)

    await _record_broadcast_message(
        text=text,
        delivered_count=len(delivered_user_ids),
        sender_id=sender_id,
    )

    tg_sent = sum(1 for ok, _ in tg_results.values() if ok)
    vk_sent = sum(1 for ok, _ in vk_results.values() if ok)
    return {
        "telegram": (tg_sent, len(tg_results) - tg_sent),
        "vk": (vk_sent, len(vk_results) - vk_sent),
    }
