from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import AsyncSessionLocal
from app.repositories.materials import MaterialCategoryRepository

router = Router()

_BACK_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="← Назад к разделам", callback_data="mat:list")]]
)


async def _categories_kb() -> tuple[str, InlineKeyboardMarkup]:
    async with AsyncSessionLocal() as session:
        cats = await MaterialCategoryRepository(session).get_all_with_materials()
    if not cats:
        return "Материалов пока нет 📭", InlineKeyboardMarkup(inline_keyboard=[])
    buttons = [
        [InlineKeyboardButton(text=f"{c.emoji} {c.name}", callback_data=f"mat:{c.id}")]
        for c in cats
    ]
    return "📚 <b>Материалы</b>\n\nВыбери раздел:", InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("materials"))
@router.message(F.text.in_({"📚 Материалы", "/материалы"}))
async def cmd_materials(message: Message) -> None:
    text, kb = await _categories_kb()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "mat:list")
async def cb_materials_list(call: CallbackQuery) -> None:
    text, kb = await _categories_kb()
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("mat:") & ~F.data.in_({"mat:list"}))
async def cb_materials_category(call: CallbackQuery) -> None:
    try:
        cat_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer()
        return

    async with AsyncSessionLocal() as session:
        cats = await MaterialCategoryRepository(session).get_all_with_materials()

    cat = next((c for c in cats if c.id == cat_id), None)
    if not cat:
        await call.answer("Раздел не найден")
        return

    visible = [m for m in cat.materials if m.is_visible]
    if not visible:
        await call.message.edit_text(
            f"{cat.emoji} <b>{cat.name}</b>\n\nМатериалов пока нет 📭",
            reply_markup=_BACK_KB,
        )
        await call.answer()
        return

    lines = [f"{cat.emoji} <b>{cat.name}</b>\n"]
    for m in visible:
        if m.url:
            lines.append(f'• <a href="{m.url}">{m.title}</a>')
        else:
            lines.append(f"• {m.title}")
        if m.description:
            lines.append(f"  <i>{m.description}</i>")

    await call.message.edit_text("\n".join(lines), reply_markup=_BACK_KB)
    await call.answer()
