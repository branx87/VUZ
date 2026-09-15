"""Регистрация TG-юзера по email.

Поток:
1. /start (или любое сообщение) → EnsureTelegramUserMiddleware регистрирует TG id.
2. Если у юзера ещё нет email — спрашиваем email.
3. Юзер пишет email → проверяем в БД:
   - есть с таким email → привязываем TG id к этой строке, заполняем имя
   - нет → создаём строку с этим email и TG id
4. После — пишем: чтобы зайти на сайт, зарегистрируйся там с этим email.
"""
import logging
import re
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

# Простая проверка формата email.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AwaitingEmail(StatesGroup):
    waiting_email = State()


class EnsureTelegramUserMiddleware(BaseMiddleware):
    """Регистрирует любого TG-юзера при первом контакте (только platform id)."""

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


async def _link_or_create_by_email(telegram_user_id: str, email: str, full_name: str | None) -> User:
    """Найти юзера по email и привязать к нему TG id, либо создать нового.

    Если этот TG id уже занят другим юзером — сначала очищаем его там,
    чтобы привязка прошла без конфликта уникального constraint.
    """
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email)
        target = existing

        if target is None:
            # Создаём нового юзера с email + TG id.
            user = User(
                email=email,
                telegram_user_id=telegram_user_id,
                telegram_username=None,
                full_name=full_name,
                is_web_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

        # Найден по email. Если этот TG id уже у другой строки — очищаем там.
        if target.telegram_user_id != telegram_user_id:
            await session.execute(
                update(User)
                .where(User.telegram_user_id == telegram_user_id)
                .values(telegram_user_id=None, telegram_username=None)
            )

        # Привязываем TG id к найденной строке.
        if target.telegram_user_id != telegram_user_id:
            target.telegram_user_id = telegram_user_id
            target.telegram_username = None
            await session.commit()
            await session.refresh(target)

        # Дозаполняем имя, если было пусто.
        if not target.full_name and full_name:
            target.full_name = full_name
            await session.commit()
            await session.refresh(target)
        return target


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return

    async with AsyncSessionLocal() as session:
        existing = await UserRepository(session).get_by_telegram_id(str(user.id))

    if existing and existing.email:
        await _show_menu(message, existing.full_name)
        await state.clear()
        return

    # Нет email — спрашиваем.
    await state.set_state(AwaitingEmail.waiting_email)
    await message.answer(
        "Привет! Я бот группы 231/232 👋\n\n"
        "Чтобы я тебя узнавал, напиши свой email — "
        "он же пригодится, чтобы зайти на сайт с расписанием.\n\n"
        "Например: <code>ivan@example.com</code>"
    )


async def _show_menu(message: Message, full_name: str | None) -> None:
    first = full_name.split()[0] if full_name else "друг"
    await message.answer(
        f"Привет, {first}! Я бот группы 231/232 👋\n\nВыбери раздел:",
        reply_markup=_MAIN_KB,
    )


@router.message(AwaitingEmail.waiting_email, F.text)
async def receive_email(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return

    email = (message.text or "").strip().lower()
    if not _EMAIL_RE.match(email):
        await message.answer(
            "❌ Это не похоже на email.\n"
            "Пример правильного формата: <code>ivan@example.com</code>"
        )
        return

    tg_user = await _link_or_create_by_email(
        telegram_user_id=str(user.id),
        email=email,
        full_name=user.full_name,
    )

    await state.clear()

    portal_url = f"{settings.app_base_url.rstrip('/')}/portal/register"
    await message.answer(
        f"✅ Email записан: <b>{email}</b>\n\n"
        f"Чтобы зайти на сайт с расписанием, открой:\n"
        f"<a href=\"{portal_url}\">{portal_url}</a>\n\n"
        f"Там зарегистрируйся с этим же email — пароль задашь только там.",
        reply_markup=_MAIN_KB,
    )
