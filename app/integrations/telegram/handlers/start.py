"""Регистрация TG-юзера по образцу lunch_bot (без проверки списка сотрудников).

Поток:
1. /start (или любое сообщение) → EnsureTelegramUserMiddleware регистрирует юзера.
2. Если full_name пустое — спрашиваем имя+фамилию, ждём ввода.
3. Юзер пишет «Иванов Иван» → сохраняем в БД, показываем главное меню.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from sqlalchemy import update

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.models import User
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


class AwaitingName(StatesGroup):
    waiting_name = State()


class EnsureTelegramUserMiddleware(BaseMiddleware):
    """Регистрирует любого TG-юзера при первом контакте."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user:
            try:
                async with AsyncSessionLocal() as session:
                    await UserRepository(session).upsert_telegram(
                        telegram_user_id=str(user.id),
                        username=user.username,
                        full_name=user.full_name,
                    )
            except Exception as exc:
                logger.error("ensure_telegram_user failed: %s", exc)
        return await handler(event, data)


router.message.middleware(EnsureTelegramUserMiddleware())


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return

    async with AsyncSessionLocal() as session:
        existing = await UserRepository(session).get_by_telegram_id(str(user.id))

    # Если у юзера уже есть имя (из Telegram-профиля или от прошлого ввода) — сразу в меню.
    if existing and existing.full_name and existing.full_name.strip():
        first = existing.full_name.split()[0]
        await message.answer(
            f"Привет, {first}! Я бот группы 231/232 👋\n\nВыбери раздел:",
            reply_markup=_MAIN_KB,
        )
        await state.clear()
        return

    # Иначе — спрашиваем имя-фамилию.
    await state.set_state(AwaitingName.waiting_name)
    await message.answer(
        "Привет! Я бот группы 231/232 👋\n\n"
        "Напиши, пожалуйста, имя и фамилию — например:\n"
        "<code>Иванов Иван</code>",
    )


@router.message(AwaitingName.waiting_name, F.text)
async def receive_name(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer(
            "❌ Нужны минимум имя и фамилия (два слова).\n"
            "Пример: <code>Иванов Иван</code>"
        )
        return

    full_name = " ".join(parts).strip()
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.telegram_user_id == str(user.id))
            .values(full_name=full_name)
        )
        await session.commit()

    await state.clear()
    first = full_name.split()[0]
    await message.answer(
        f"✅ Записал: <b>{full_name}</b>\n\nПривет, {first}! Выбери раздел:",
        reply_markup=_MAIN_KB,
    )
