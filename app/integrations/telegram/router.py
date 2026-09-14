import hmac
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

_session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None

bot = Bot(
    token=settings.telegram_bot_token or "0:placeholder",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=_session,
)
dp = Dispatcher(storage=MemoryStorage())


def setup_routers() -> None:
    from app.integrations.telegram.handlers.admin import router as admin_router
    from app.integrations.telegram.handlers.start import router as start_router
    from app.integrations.telegram.handlers.schedule import router as schedule_router
    from app.integrations.telegram.handlers.materials import router as materials_router
    from app.integrations.telegram.handlers.events import router as events_router
    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(schedule_router)
    dp.include_router(materials_router)
    dp.include_router(events_router)


router = APIRouter()


@router.post("")
async def tg_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if settings.telegram_webhook_secret and not hmac.compare_digest(
        secret.encode(), settings.telegram_webhook_secret.encode()
    ):
        logger.warning("TG webhook: invalid secret token from %s", request.client)
        return JSONResponse({"error": "forbidden"}, status_code=403)

    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return JSONResponse({"ok": True})
