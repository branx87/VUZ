from app.database import AsyncSessionLocal
from app.integrations.vk.api import vk_api
from app.integrations.vk.keyboards import main_menu
from app.repositories.materials import MaterialCategoryRepository


async def handle_materials(msg: dict) -> None:
    async with AsyncSessionLocal() as session:
        cats = await MaterialCategoryRepository(session).get_all_with_materials()

    if not cats:
        await vk_api.send_message(msg["from_id"], "Материалов пока нет 📭", keyboard=main_menu())
        return

    lines = ["📚 Материалы\n"]
    for cat in cats:
        visible = [m for m in cat.materials if m.is_visible]
        if not visible:
            continue
        lines.append(f"{cat.emoji} {cat.name}:")
        for m in visible:
            entry = f"  • {m.title}"
            if m.url:
                entry += f"\n    {m.url}"
            if m.description:
                entry += f"\n    {m.description}"
            lines.append(entry)
        lines.append("")

    text = "\n".join(lines).strip() or "Материалов пока нет 📭"
    await vk_api.send_message(msg["from_id"], text, keyboard=main_menu())


TEXT_HANDLERS = {
    "📚 материалы": handle_materials,
    "материалы": handle_materials,
}
