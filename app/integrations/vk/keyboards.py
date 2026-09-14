"""
VK keyboard builder helpers.
VK keyboard format: https://dev.vk.com/ru/api/bots/development/keyboard
"""


def _btn(label: str, color: str = "secondary") -> dict:
    return {"action": {"type": "text", "label": label}, "color": color}


def main_menu() -> dict:
    return {
        "one_time": False,
        "buttons": [
            [
                _btn("📅 Расписание", "primary"),
                _btn("📚 Материалы", "secondary"),
            ],
            [
                _btn("🔔 События", "secondary"),
            ],
        ],
    }


def schedule_menu() -> dict:
    return {
        "one_time": True,
        "buttons": [
            [
                _btn("Сегодня", "positive"),
                _btn("Завтра", "positive"),
            ],
            [_btn("На неделю", "secondary")],
            [_btn("◀️ Меню", "negative")],
        ],
    }
