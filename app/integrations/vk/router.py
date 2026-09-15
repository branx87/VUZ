import hmac
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Единый словарь text → handler, собирается при старте через register_handlers()
_dispatch: dict[str, Callable[[dict], Awaitable[None]]] = {}


def register_handlers() -> None:
    from app.integrations.vk.handlers.schedule import TEXT_HANDLERS as schedule_handlers
    from app.integrations.vk.handlers.materials import TEXT_HANDLERS as material_handlers
    from app.integrations.vk.handlers.events import TEXT_HANDLERS as event_handlers
    _dispatch.update(schedule_handlers)
    _dispatch.update(material_handlers)
    _dispatch.update(event_handlers)


router = APIRouter()


async def dispatch_message(message: dict) -> None:
    """Единая точка маршрутизации сообщения. Используется FastAPI-роутом
    (Callback API) и run_vk_polling.py (Long Poll).

    Порядок:
    1. Регистрируем отправителя (иначе юзеры без /start "невидимые").
    2. Если юзер в режиме ожидания имени — обрабатываем ввод имени.
    3. Иначе — обычная диспетчеризация по тексту.
    """
    from_id = message.get("from_id")
    text = (message.get("text") or "").strip()

    if from_id:
        try:
            from app.database import AsyncSessionLocal
            from app.repositories.users import UserRepository
            async with AsyncSessionLocal() as session:
                await UserRepository(session).upsert_vk(
                    vk_user_id=str(from_id),
                    username=None,
                    full_name=None,
                )
        except Exception as exc:
            logger.warning("VK upsert on incoming failed: %s", exc)

    # Если юзер сейчас в режиме ожидания имени — перехватываем любое сообщение.
    if from_id:
        from app.integrations.vk.handlers.schedule import _awaiting_name, handle_awaiting_name
        if _awaiting_name.get(from_id):
            if text:
                await handle_awaiting_name(message)
            return  # Не диспетчеризируем дальше, пока юзер не ввёл имя.

    text_lower = text.lower()
    handler = _dispatch.get(text_lower)
    if handler:
        try:
            await handler(message)
        except Exception:
            logger.exception("VK handler error for text=%r", text_lower)


@router.post("/")
async def vk_webhook(request: Request) -> PlainTextResponse:
    data = await request.json()

    if settings.vk_secret_key:
        received = (data.get("secret") or "").encode()
        expected = settings.vk_secret_key.encode()
        if not hmac.compare_digest(received, expected):
            logger.warning("VK webhook: wrong secret")
            return PlainTextResponse("forbidden", status_code=403)

    if data.get("type") == "confirmation":
        return PlainTextResponse(settings.vk_confirmation_string)

    if int(data.get("group_id", 0)) != settings.vk_group_id:
        return PlainTextResponse("ok")

    event_type = data.get("type")
    if event_type == "message_new":
        await dispatch_message(data["object"]["message"])

    return PlainTextResponse("ok")
