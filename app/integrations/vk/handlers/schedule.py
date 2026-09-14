from datetime import date, timedelta

import logging

from app.database import AsyncSessionLocal
from app.integrations.vk.api import vk_api
from app.integrations.vk.keyboards import main_menu, schedule_menu
from app.repositories.schedule import ScheduleRepository
from app.repositories.users import UserRepository
from app.services.formatters import format_day_plain, format_week_plain
from app.services.schedule import ScheduleService

logger = logging.getLogger(__name__)


async def _register_user(msg: dict) -> None:
    """Регистрирует VK-отправителя в users."""
    from_id = msg.get("from_id")
    if not from_id:
        return
    try:
        async with AsyncSessionLocal() as session:
            await UserRepository(session).upsert(
                platform="vk",
                platform_user_id=str(from_id),
                username=None,
                full_name=None,
            )
    except Exception as exc:
        logger.warning("VK /start upsert failed for user %s: %s", from_id, exc)


async def handle_start(msg: dict) -> None:
    await _register_user(msg)
    await vk_api.send_message(
        msg["from_id"],
        "Привет! Я бот группы 231/232 👋\n\nВыбери раздел:",
        keyboard=main_menu(),
    )


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


# Регистрируем все тексты в нижнем регистре — диспетчер VK приводит текст к lower()
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
