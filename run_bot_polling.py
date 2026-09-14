"""
Запуск Telegram-бота в режиме polling (только для локальной разработки).
Не требует публичного URL — бот сам опрашивает Telegram.

Запуск:
    .\.venv\Scripts\python.exe run_bot_polling.py
"""
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.integrations.telegram.router import dp, setup_routers


async def main():
    session_kwargs = {}
    if settings.proxy_url:
        logger.info("Telegram: используется прокси %s", settings.proxy_url.split("@")[-1])
        session_kwargs["proxy"] = settings.proxy_url

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=AiohttpSession(**session_kwargs),
    )

    setup_routers()
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logger.info("Бот @%s запущен в режиме polling. Ctrl+C для остановки.", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
