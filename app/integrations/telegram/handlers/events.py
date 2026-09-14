from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.database import AsyncSessionLocal
from app.repositories.events import EventRepository

router = Router()


@router.message(Command("events"))
@router.message(F.text.in_({"🔔 События", "/события"}))
async def cmd_events(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        events = await EventRepository(session).get_upcoming(date.today())

    if not events:
        await message.answer("Предстоящих событий нет 📭")
        return

    lines = ["🔔 <b>Предстоящие события</b>\n"]
    for e in events:
        dt = e.event_date.strftime("%d.%m.%Y")
        if e.event_time:
            dt += f" в {e.event_time.strftime('%H:%M')}"
        lines.append(f"📌 <b>{e.title}</b> — {dt}")
        if e.description:
            lines.append(f"   <i>{e.description}</i>")

    await message.answer("\n".join(lines))
