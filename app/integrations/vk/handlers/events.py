from datetime import date

from app.database import AsyncSessionLocal
from app.integrations.vk.api import vk_api
from app.integrations.vk.keyboards import main_menu
from app.repositories.events import EventRepository


async def handle_events(msg: dict) -> None:
    async with AsyncSessionLocal() as session:
        events = await EventRepository(session).get_upcoming(date.today())

    if not events:
        await vk_api.send_message(msg["from_id"], "Предстоящих событий нет 📭", keyboard=main_menu())
        return

    lines = ["🔔 Предстоящие события\n"]
    for e in events:
        dt = e.event_date.strftime("%d.%m.%Y")
        if e.event_time:
            dt += f" в {e.event_time.strftime('%H:%M')}"
        lines.append(f"📌 {e.title} — {dt}")
        if e.description:
            lines.append(f"   {e.description}")

    await vk_api.send_message(msg["from_id"], "\n".join(lines), keyboard=main_menu())


TEXT_HANDLERS = {
    "🔔 события": handle_events,
    "события": handle_events,
}
