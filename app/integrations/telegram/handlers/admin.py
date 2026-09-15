import asyncio
import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.database import AsyncSessionLocal
from app.integrations.telegram.filters import IsAdmin
from app.repositories.events import EventRepository
from app.services.broadcast import broadcast_all, broadcast_telegram

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(IsAdmin())

_ADMIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="📅 Добавить событие")],
        [KeyboardButton(text="❌ Отмена")],
    ],
    resize_keyboard=True,
)

# Inline-кнопка отмены — показывается в состояниях FSM, где обычная клавиатура убрана.
_CANCEL_INLINE_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")]],
)


class BroadcastFSM(StatesGroup):
    text = State()


class AddEventFSM(StatesGroup):
    date = State()
    title = State()
    description = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Панель администратора:", reply_markup=_ADMIN_KB)


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=_ADMIN_KB)


@router.callback_query(F.data == "admin:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    """Inline-кнопка «Отмена» в FSM-состояниях, где обычная клавиатура убрана."""
    await state.clear()
    await call.message.answer("Отменено.", reply_markup=_ADMIN_KB)
    await call.answer()


# ── Broadcast ──────────────────────────────────────────────────────────────


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot, state: FSMContext) -> None:
    text = (message.text or "").removeprefix("/broadcast").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст сообщения>")
        return
    await _do_broadcast(message, bot, text)


@router.message(F.text == "📢 Рассылка")
async def btn_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(BroadcastFSM.text)
    await message.answer(
        "Введите текст рассылки:",
        reply_markup=_CANCEL_INLINE_KB,
    )


@router.message(BroadcastFSM.text)
async def fsm_broadcast_text(message: Message, bot: Bot, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.clear()
    await _do_broadcast(message, bot, text)


async def _do_broadcast(message: Message, bot: Bot, text: str) -> None:
    # Рассылаем сразу по обеим платформам, чтобы админу не приходилось дублировать.
    results = await broadcast_all(bot, text)
    tg_sent, tg_failed = results["telegram"]
    vk_sent, vk_failed = results["vk"]
    await message.answer(
        "✅ Рассылка завершена:\n"
        f"• Telegram: отправлено {tg_sent}, ошибок {tg_failed}\n"
        f"• VK: отправлено {vk_sent}, ошибок {vk_failed}",
        reply_markup=_ADMIN_KB,
    )


# ── Add event FSM ──────────────────────────────────────────────────────────


@router.message(Command("add_event"))
@router.message(F.text == "📅 Добавить событие")
async def cmd_add_event(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEventFSM.date)
    await message.answer(
        "Введите дату события (ГГГГ-ММ-ДД):",
        reply_markup=_CANCEL_INLINE_KB,
    )


@router.message(AddEventFSM.date)
async def fsm_date(message: Message, state: FSMContext) -> None:
    try:
        event_date = date.fromisoformat((message.text or "").strip())
    except ValueError:
        await message.answer(
            "Неверный формат. Введите дату в формате ГГГГ-ММ-ДД:",
            reply_markup=_CANCEL_INLINE_KB,
        )
        return
    await state.update_data(event_date=event_date.isoformat())
    await state.set_state(AddEventFSM.title)
    await message.answer(
        "Введите название события:",
        reply_markup=_CANCEL_INLINE_KB,
    )


@router.message(AddEventFSM.title)
async def fsm_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddEventFSM.description)
    await message.answer(
        "Введите описание (или /skip чтобы пропустить):",
        reply_markup=_CANCEL_INLINE_KB,
    )


@router.message(AddEventFSM.description)
async def fsm_description(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    description = None if raw == "/skip" else raw
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        event = await EventRepository(session).create(
            title=data["title"],
            description=description,
            event_date=date.fromisoformat(data["event_date"]),
            notify_days_before=[],
            is_active=True,
        )

    logger.info("add_event: created id=%d title=%s", event.id, event.title)
    await state.clear()
    await message.answer(
        f"✅ Событие добавлено:\n<b>{event.title}</b>\n📅 {event.event_date}",
        reply_markup=_ADMIN_KB,
    )
