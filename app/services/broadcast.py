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
from app.integrations.vk.api import VKApi, vk_api as default_vk_api
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)


async def _send_with_retry(
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 3,
) -> bool:
    """Отправляет сообщение с ретраем на TelegramRetryAfter (3 попытки)."""
    for attempt in range(1, max_attempts + 1):
        try:
            await coro_factory()
            return True
        except TelegramRetryAfter as exc:
            wait = exc.retry_after + 1
            logger.warning("Telegram RetryAfter %s sec, waiting", wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            logger.warning("send failed (attempt %d/%d): %s", attempt, max_attempts, exc)
            if attempt == max_attempts:
                return False
            await asyncio.sleep(0.5)
    return False


async def broadcast_telegram(bot: Bot, text: str, *, concurrency: int = 25) -> tuple[int, int]:
    """Шлёт текст всем Telegram-подписчикам, уважая RetryAfter.

    Returns: (sent, failed)
    """
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_all_telegram()

    sem = asyncio.Semaphore(concurrency)

    async def _one(user) -> tuple[bool, str | None]:
        async with sem:
            ok = await _send_with_retry(
                lambda: bot.send_message(int(user.platform_user_id), text)
            )
            return ok, user.platform_user_id

    results = await asyncio.gather(*[_one(u) for u in users], return_exceptions=False)
    sent = sum(1 for ok, _ in results if ok)
    failed = len(results) - sent
    logger.info("TG broadcast done: sent=%d failed=%d (users=%d)", sent, failed, len(users))
    return sent, failed


async def broadcast_vk(
    text: str,
    *,
    vk_api: VKApi | None = None,
    concurrency: int = 3,
) -> tuple[int, int]:
    """Шлёт текст всем VK-подписчикам.

    VK Community API лимитирован ~3 msg/s на сообщество; используем Semaphore(3).
    """
    api = vk_api or default_vk_api
    async with AsyncSessionLocal() as session:
        users = await UserRepository(session).get_all_vk()

    sem = asyncio.Semaphore(concurrency)

    async def _one(user) -> tuple[bool, str | None]:
        async with sem:
            try:
                await api.send_message(int(user.platform_user_id), text)
                return True, user.platform_user_id
            except Exception as exc:
                logger.warning("VK broadcast failed for user %s: %s", user.platform_user_id, exc)
                return False, user.platform_user_id

    results = await asyncio.gather(*[_one(u) for u in users], return_exceptions=False)
    sent = sum(1 for ok, _ in results if ok)
    failed = len(results) - sent
    logger.info("VK broadcast done: sent=%d failed=%d (users=%d)", sent, failed, len(users))
    return sent, failed


async def broadcast_all(bot: Bot, text: str) -> dict[str, tuple[int, int]]:
    """Рассылает по всем платформам параллельно. Возвращает {platform: (sent, failed)}."""
    tg_task = broadcast_telegram(bot, text)
    vk_task = broadcast_vk(text)
    tg_result, vk_result = await asyncio.gather(tg_task, vk_task)
    return {"telegram": tg_result, "vk": vk_result}
