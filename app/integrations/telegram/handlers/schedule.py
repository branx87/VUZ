from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database import AsyncSessionLocal
from app.repositories.schedule import ScheduleRepository
from app.services.formatters import format_day_html, format_week_html
from app.services.schedule import ScheduleService

router = Router()

_MENU_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня", callback_data="sched:today"),
            InlineKeyboardButton(text="Завтра", callback_data="sched:tomorrow"),
        ],
        [InlineKeyboardButton(text="На неделю", callback_data="sched:week")],
    ]
)

_BACK_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data="sched:menu")]]
)


async def _day_text(target_date: date) -> str:
    async with AsyncSessionLocal() as session:
        svc = ScheduleService(ScheduleRepository(session))
        lessons = await svc.get_for_date(target_date)
    return format_day_html(lessons, target_date)


async def _week_kb_or_text(week_start: date) -> tuple[str, InlineKeyboardMarkup]:
    async with AsyncSessionLocal() as session:
        svc = ScheduleService(ScheduleRepository(session))
        week_data = await svc.get_for_week(week_start)
    return format_week_html(week_data, week_start), _MENU_KB


@router.message(Command("schedule"))
@router.message(F.text.in_({"📅 Расписание", "/расписание"}))
async def cmd_schedule(message: Message) -> None:
    await message.answer("Выбери период:", reply_markup=_MENU_KB)


@router.callback_query(F.data == "sched:menu")
async def cb_menu(call: CallbackQuery) -> None:
    await call.message.edit_text("Выбери период:", reply_markup=_MENU_KB)
    await call.answer()


@router.callback_query(F.data == "sched:today")
async def cb_today(call: CallbackQuery) -> None:
    await call.message.edit_text(await _day_text(date.today()), reply_markup=_MENU_KB)
    await call.answer()


@router.callback_query(F.data == "sched:tomorrow")
async def cb_tomorrow(call: CallbackQuery) -> None:
    await call.message.edit_text(
        await _day_text(date.today() + timedelta(days=1)), reply_markup=_MENU_KB
    )
    await call.answer()


@router.callback_query(F.data == "sched:week")
async def cb_week(call: CallbackQuery) -> None:
    async with AsyncSessionLocal() as session:
        weeks = await ScheduleRepository(session).get_session_weeks()

    if not weeks:
        await call.message.edit_text("Расписание пока не добавлено.", reply_markup=_MENU_KB)
        await call.answer()
        return

    if len(weeks) == 1:
        text, kb = await _week_kb_or_text(weeks[0])
        await call.message.edit_text(text, reply_markup=kb)
        await call.answer()
        return

    buttons = []
    for w in weeks:
        end = w + timedelta(days=5)
        label = f"{w.strftime('%d.%m')}–{end.strftime('%d.%m')}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"sched:week:{w.isoformat()}")])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="sched:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text("Выбери неделю сессии:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("sched:week:"))
async def cb_week_selected(call: CallbackQuery) -> None:
    iso = call.data.removeprefix("sched:week:")
    week_start = date.fromisoformat(iso)
    text, kb = await _week_kb_or_text(week_start)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()
