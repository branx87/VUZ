"""
Thin async wrapper around VK API.
We call the API directly via httpx instead of using vkbottle's high-level layer
so the integration stays simple and doesn't fight with FastAPI's event loop.
"""
import json
import logging
import random
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.vk.com/method"
_VER = "5.199"


class VKApi:
    def __init__(self, token: str, group_id: int):
        self.token = token
        self.group_id = group_id

    async def _call(self, method: str, **params: Any) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_BASE}/{method}",
                data={"access_token": self.token, "v": _VER, **params},
            )
        data = resp.json()
        if "error" in data:
            logger.error("VK API %s error: %s", method, data["error"])
            raise RuntimeError(f"VK API error [{method}]: {data['error'].get('error_msg')}")
        return data.get("response")

    async def send_message(
        self,
        user_id: int,
        text: str,
        keyboard: Optional[dict] = None,
    ) -> int:
        params: dict[str, Any] = {
            "user_id": user_id,
            "message": text,
            "random_id": random.randint(1, 2**31),
        }
        if keyboard:
            params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
        return await self._call("messages.send", **params)

    async def post_to_wall(self, text: str) -> int:
        result = await self._call(
            "wall.post",
            owner_id=f"-{self.group_id}",
            message=text,
            from_group=1,
        )
        return result["post_id"]


# Singleton used across handlers
vk_api = VKApi(
    token=settings.vk_community_token or "placeholder",
    group_id=settings.vk_group_id,
)
