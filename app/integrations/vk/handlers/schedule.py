"""Регистрация VK-юзера по email (как у TG).

Поток:
1. Любое сообщение → dispatch_message регистрирует vk id.
2. handle_start: если email уже есть → меню, иначе → спрашиваем email.
3. handle_awaiting_email: получаем email, ищем в БД, привязываем или создаём.
"""
import logging
import re

from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.domain.models import User
from app.integrations.vk.api import vk_api
from app.integrations.vk.keyboards import main_menu, schedule_menu
from app.repositories.schedule import ScheduleRepository
from app.repositories.users import UserRepository
from app.config import settings
from app.services.formatters import format_day_plain, format_week_plain
from app.services.schedule import ScheduleService
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Состояние «юзер сейчас ждёт ввода email».
_awaiting_email: dict[int, bool] = {}
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


async def _register_user(msg: dict) -> None:
    """Регистрирует VK-отправителя в users (только platform id)."""
    from_id = msg.get("from_id")
    if not from_id:
        return
    try:
        async with AsyncSessionLocal() as session:
            await UserRepository(session).upsert_vk(
                vk_user_id=str(from_id),
                username=None,
                full_name=None,
            )
    except Exception as exc:
        logger.warning("VK upsert failed: %s", exc)


async def _link_or_create_by_email(vk_user_id: str, email: str, full_name: str | None) -> User:
    """Найти юзера по email и привязать к нему VK id, либо создать нового.

    Если этот VK id уже занят другой строкой — сначала очищаем там,
    чтобы избежать конфликта unique constraint.
    """
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email)
        target = existing

        if target is None:
            user = User(
                email=email,
                vk_user_id=vk_user_id,
                vk_username=None,
                full_name=full_name,
                is_web_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

        # Найден по email. Если VK id занят другой строкой — очищаем там.
        if target.vk_user_id != vk_user_id:
            await session.execute(
                update(User)
                .where(User.vk_user_id == vk_user_id)
                .values(vk_user_id=None, vk_username=None)
            )

        if target.vk_user_id != vk_user_id:
            target.vk_user_id = vk_user_id
            target.vk_username = None
            await session.commit()
            await session.refresh(target)

        if not target.full_name and full_name:
            target.full_name = full_name
            await session.commit()
            await session.refresh(target)
        return target


async def handle_start(msg: dict) -> None:
    from_id = msg["from_id"]
    await _register_user(msg)
    async with AsyncSessionLocal() as session:
        existing = await UserRepository(session).get_by_vk_id(str(from_id))

    if existing and existing.email:
        await _show_menu(from_id, existing.full_name)
        return

    _awaiting_email[from_id] = True
    await vk_api.send_message(
        from_id,
        "Привет! Я бот группы 231/232 👋\n\n"
        "Чтобы я тебя узнавал, напиши свой email — "
        "он же пригодится, чтобы зайти на сайт с расписанием.\n\n"
        "Например: ivan@example.com",
    )


async def handle_awaiting_email(msg: dict) -> None:
    """Обрабатывает ввод email от юзера, который сейчас его ждёт."""
    from_id = msg["from_id"]
    text = (msg.get("text") or "").strip().lower()
    if not _EMAIL_RE.match(text):
        await vk_api.send_message(
            from_id,
            "❌ Это не похоже на email.\n"
            "Пример правильного формата: ivan@example.com",
        )
        return

    user = await _link_or_create_by_email(
        vk_user_id=str(from_id),
        email=text,
        full_name=None,
    )

    _awaiting_email.pop(from_id, None)
    portal_url = f"{settings.app_base_url.rstrip('/')}/portal/register"
    await vk_api.send_message(
        from_id,
        f"✅ Email записан: {text}\n\n"
        f"Чтобы зайти на сайт с расписанием, открой:\n"
        f"{portal_url}\n\n"
        f"Там зарегистрируйся с этим же email — пароль задашь только там.",
        keyboard=main_menu(),
    )


async def _show_menu(user_id: int, full_name: str | None) -> None:
    first = full_name.split()[0] if full_name else "друг"
    await vk_api.send_message(
        user_id,
        f"Привет, {first}! Я бот группы 231/232 👋\n\nВыбери раздел:",
        keyboard=main_menu(),
    )


# Остальные handlers — расписание и т.п.

async def _send_day(user_id: int, target_date: date) -> None:
    async with AsyncSessionLocal() as session:
        svc = ScheduleService(ScheduleRepository(session))
        lessons = await svc.get_for_date(target_date)
    await vk_api.send_message(user_id, format_day_plain(lessons, target_date), keyboard=main_menu())


async def handle_schedule_menu(msg: dict) -> None:
    await vk_api.send_message(msg["from_id"], "Выбери период:", keyboard=schedule_menu())


async def handle_today(msg: dict) -> None:
    await _send_day(msg["from_id"], date.today())


async def handle_tomorrow(msg: dict) -> None:
    await _send_day(msg["from_id"], date.today() + timedelta(days=1))


async def handle_week(msg: dict) -> None:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    async with AsyncSessionLocal() as session:
        svc = ScheduleService(ScheduleRepository(session))
        week_data = await svc.get_for_week(week_start)
    text = format_week_plain(week_data, week_start)
    await vk_api.send_message(msg["from_id"], text, keyboard=main_menu())


async def handle_back(msg: dict) -> None:
    await vk_api.send_message(msg["from_id"], "Главное меню:", keyboard=main_menu())


TEXT_HANDLERS: dict[str, object] = {
    "/start": handle_start,
    "начать": handle_start,
    "📅 расписание": handle_schedule_menu,
    "расписание": handle_schedule_menu,
    "сегодня": handle_today,
    "завтра": handle_tomorrow,
    "на неделю": handle_week,
    "◀️ меню": handle_back,
    "меню": handle_back,
}
