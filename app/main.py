import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VUZ Bot starting (base_url=%s)", settings.app_base_url)

    # Telegram: регистрируем хендлеры. Webhook ставим только если URL не localhost.
    tg_bot = None
    if settings.telegram_bot_token and settings.telegram_bot_token != "0:placeholder":
        from app.integrations.telegram.router import bot, setup_routers
        setup_routers()
        tg_bot = bot
        is_local = any(h in settings.app_base_url for h in ("localhost", "127.0.0.1", "your-domain"))
        if not is_local:
            webhook_url = f"{settings.app_base_url.rstrip('/')}/webhook/tg"
            try:
                await bot.set_webhook(
                    url=webhook_url,
                    secret_token=settings.telegram_webhook_secret or None,
                    drop_pending_updates=True,
                )
                logger.info("TG webhook registered: %s", webhook_url)
            except Exception as e:
                logger.warning("TG webhook setup skipped: %s", e)
        else:
            logger.info("TG webhook skipped (local dev — set APP_BASE_URL to register webhook)")

    # VK: наш URL регистрируется вручную в настройках сообщества.
    # Здесь только подключаем хендлеры в диспетчер.
    if settings.vk_community_token and settings.vk_community_token != "placeholder":
        from app.integrations.vk.router import register_handlers
        register_handlers()
        logger.info("VK handlers registered")

    # Планировщик напоминаний о событиях
    if tg_bot is not None or settings.vk_community_token:
        try:
            start_scheduler(tg_bot)
        except Exception as e:
            logger.warning("Scheduler start skipped: %s", e)

    yield

    try:
        stop_scheduler()
    except Exception:
        pass

    is_local = any(h in settings.app_base_url for h in ("localhost", "127.0.0.1", "your-domain"))
    if tg_bot is not None and not is_local:
        try:
            await tg_bot.delete_webhook()
        except Exception as e:
            logger.warning("TG delete webhook skipped: %s", e)

    logger.info("VUZ Bot stopped")


app = FastAPI(title="VUZ Bot", version="0.2.0", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.integrations.telegram.router import router as tg_router
from app.integrations.vk.router import router as vk_router
from app.admin.router import router as admin_router
from app.miniapp.router import router as miniapp_router

app.include_router(tg_router, prefix="/webhook/tg", tags=["telegram"])
app.include_router(vk_router, prefix="/webhook/vk", tags=["vk"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(miniapp_router, prefix="/miniapp", tags=["miniapp"])


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/admin/schedule")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
