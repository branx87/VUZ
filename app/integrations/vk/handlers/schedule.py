from datetime import date, timedelta

import logging

from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.domain.models import User
from app.integrations.vk.api import vk_api
from app.integrations.vk.keyboards import main_menu, schedule_menu
from app.repositories.schedule import ScheduleRepository
from app.repositories.users import UserRepository
from app.services.formatters import format_day_plain, format_week_plain
from app.services.schedule import ScheduleService

logger = logging.getLogger(__name__)

# In-memory: какие VK-юзеры сейчас ждут ввода имени-фамилии.
# Ключ — from_id (int). Очищается после первого успешного ввода.
# NOTE: работает только в рамках одного процесса (webhook или polling).
_awaiting_name: dict[int, bool] = {}


async def _register_user(msg: dict) -> None:
    """Регистрирует VK-отправителя в users."""
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
        logger.warning("VK /start upsert failed for user %s: %s", from_id, exc)


async def handle_start(msg: dict) -> None:
    from_id = msg["from_id"]
    await _register_user(msg)
    async with AsyncSessionLocal() as session:
        existing = await UserRepository(session).get_by_vk_id(str(from_id))

    # Если у юзера уже есть имя — сразу меню.
    if existing and existing.full_name and existing.full_name.strip():
        first = existing.full_name.split()[0]
        await vk_api.send_message(
            from_id,
            f"Привет, {first}! Я бот группы 231/232 👋\n\nВыбери раздел:",
            keyboard=main_menu(),
        )
        return

    # Иначе — спрашиваем имя-фамилию.
    _awaiting_name[from_id] = True
    await vk_api.send_message(
        from_id,
        "Привет! Я бот группы 231/232 👋\n\n"
        "Напиши, пожалуйста, имя и фамилию — например:\n"
        "Иванов Иван",
    )


async def handle_awaiting_name(msg: dict) -> None:
    """Обрабатывает ввод имени от юзера, который сейчас ждёт его."""
    from_id = msg["from_id"]
    text = (msg.get("text") or "").strip()
    parts = text.split()
    if len(parts) < 2:
        await vk_api.send_message(
            from_id,
            "❌ Нужны минимум имя и фамилия (два слова).\n"
            "Пример: Иванов Иван",
        )
        return

    full_name = " ".join(parts).strip()
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.vk_user_id == str(from_id))
            .values(full_name=full_name)
        )
        await session.commit()

    _awaiting_name.pop(from_id, None)
    first = full_name.split()[0]
    await vk_api.send_message(
        from_id,
        f"✅ Записал: {full_name}\n\nПривет, {first}! Выбери раздел:",
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
