"""
Запуск VK-бота в режиме Long Poll.
Не требует публичного URL — бот сам опрашивает VK.

Запуск:
    .venv/Scripts/python.exe run_vk_polling.py
"""
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

import httpx

from app.config import settings
from app.integrations.vk.router import dispatch_message, register_handlers

register_handlers()

_BASE = "https://api.vk.com/method"
_VER = "5.199"


async def _api(method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{_BASE}/{method}",
            data={"access_token": settings.vk_community_token, "v": _VER, **params},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"VK error [{method}]: {data['error'].get('error_msg')}")
    return data["response"]


async def _get_lp_server() -> tuple[str, str, str]:
    r = await _api("groups.getLongPollServer", group_id=settings.vk_group_id)
    logger.info("Long Poll server: ts=%s server=%s", r.get("ts"), r.get("server"))
    return r["server"], r["key"], str(r["ts"])


async def _poll(server: str, key: str, ts: str) -> tuple[list, str]:
    async with httpx.AsyncClient(timeout=35) as client:
        r = await client.get(
            server,
            params={"act": "a_check", "key": key, "ts": ts, "wait": 25},
        )
    data = r.json()
    if "failed" in data:
        failed = data["failed"]
        new_ts = str(data.get("ts", ts))
        logger.warning("Long Poll failed=%s, ts=%s→%s", failed, ts, new_ts)
        # failed=2 или 3 → нужен новый сервер, сигнализируем через None
        return (None if failed in (2, 3) else []), new_ts
    updates = data.get("updates", [])
    if updates:
        logger.info("Получено обновлений: %d", len(updates))
    return updates, str(data["ts"])


async def handle_event(event: dict) -> None:
    event_type = event.get("type")
    if event_type != "message_new":
        logger.debug("Пропускаем событие type=%s", event_type)
        return

    message = event.get("object", {}).get("message", {})
    text = (message.get("text") or "").strip()
    from_id = message.get("from_id")
    logger.info("Сообщение от vk_id=%s: %r", from_id, text)

    if not from_id:
        return

    await dispatch_message(message)


async def main() -> None:
    logger.info("VK Long Poll запускается...")
    server, key, ts = await _get_lp_server()

    while True:
        try:
            updates, ts = await _poll(server, key, ts)

            if updates is None:
                # failed=2 или 3 — берём новый сервер
                logger.info("Обновляем Long Poll сервер...")
                server, key, ts = await _get_lp_server()
                continue

            for event in updates:
                await handle_event(event)

        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            pass  # таймаут wait=25 — норма
        except Exception:
            logger.exception("Long Poll ошибка, переподключение через 5 сек")
            await asyncio.sleep(5)
            server, key, ts = await _get_lp_server()


if __name__ == "__main__":
    asyncio.run(main())
