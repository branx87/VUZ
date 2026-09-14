import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)
router = Router()

_MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Расписание"), KeyboardButton(text="📚 Материалы")],
        [
            KeyboardButton(text="🔔 События"),
            KeyboardButton(
                text="🌐 Mini App",
                web_app=WebAppInfo(url=f"{settings.app_base_url.rstrip('/')}/miniapp/"),
            ),
        ],
    ],
    resize_keyboard=True,
    persistent=True,
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user:
        try:
            async with AsyncSessionLocal() as session:
                await UserRepository(session).upsert(
                    platform="telegram",
                    platform_user_id=str(user.id),
                    username=user.username,
                    full_name=user.full_name,
                )
        except Exception as exc:
            logger.error("/start upsert failed for user %s: %s", user.id, exc)

    await message.answer(
        "Привет! Я бот группы 231/232 👋\n\nВыбери раздел:",
        reply_markup=_MAIN_KB,
    )
