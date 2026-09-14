from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(
            settings.admin_tg_id
            and message.from_user
            and message.from_user.id == settings.admin_tg_id
        )
