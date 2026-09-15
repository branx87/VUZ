"""
Восстановление пароля через бота.

Поток:
1. Юзер вводит email в /portal/forgot.
2. Генерируем 6-значный код, сохраняем bcrypt-хеш в БД с TTL 15 мин.
3. Шлём код юзеру через TG и/или VK (по platform_id из БД).
4. Юзер вводит код + новый пароль в /portal/reset.
5. Проверяем хеш, ставим used=True, обновляем password_hash у юзера.
"""
import logging
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import bcrypt
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.models import PasswordResetCode, User
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 15


def _hash_code(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def _verify_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode(), code_hash.encode())
    except (ValueError, AttributeError):
        return False


def _now() -> datetime:
    return datetime.now(ZoneInfo(settings.scheduler_timezone))


async def request_reset(email: str) -> dict:
    """Создаёт код восстановления и отправляет его юзеру через бота.

    Returns:
        {"sent": bool, "tg": bool, "vk": bool, "email": str}
    """
    email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_email(email)

    result = {"email": email, "sent": False, "tg": False, "vk": False}
    if not user:
        # Не сообщаем, что email не найден (защита от перебора).
        return result

    # Генерируем 6-значный код.
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = _hash_code(code)
    expires_at = _now() + timedelta(minutes=CODE_TTL_MINUTES)

    async with AsyncSessionLocal() as session:
        session.add(PasswordResetCode(
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
        ))
        await session.commit()

    # Шлём в TG, если есть.
    if user.telegram_user_id:
        try:
            from app.integrations.telegram.router import bot
            await bot.send_message(
                int(user.telegram_user_id),
                f"🔐 Код восстановления пароля для {email}: <b>{code}</b>\n\n"
                f"Введите его на странице восстановления в течение "
                f"{CODE_TTL_MINUTES} минут.\n\n"
                f"Если это были не вы — просто проигнорируйте.",
            )
            result["tg"] = True
        except Exception as exc:
            logger.error("reset code (tg) failed: %s", exc)

    # Шлём в VK, если есть.
    if user.vk_user_id:
        try:
            from app.integrations.vk.api import vk_api
            await vk_api.send_message(
                int(user.vk_user_id),
                f"🔐 Код восстановления пароля для {email}: {code}\n\n"
                f"Введите его на странице восстановления в течение "
                f"{CODE_TTL_MINUTES} минут.\n\n"
                f"Если это были не вы — просто проигнорируйте.",
            )
            result["vk"] = True
        except Exception as exc:
            logger.error("reset code (vk) failed: %s", exc)

    result["sent"] = result["tg"] or result["vk"]
    logger.info("reset code for %s: tg=%s vk=%s", email, result["tg"], result["vk"])
    return result


async def confirm_reset(email: str, code: str, new_password: str) -> tuple[bool, str]:
    """Подтверждает код и устанавливает новый пароль.

    Returns:
        (success, error_message_or_empty)
    """
    email = email.strip().lower()
    if len(new_password) < 6:
        return False, "Пароль минимум 6 символов"

    async with AsyncSessionLocal() as session:
        # Ищем самый свежий неиспользованный код для этого email.
        result = await session.execute(
            select(PasswordResetCode)
            .where(
                PasswordResetCode.email == email,
                PasswordResetCode.used == False,  # noqa: E712
            )
            .order_by(PasswordResetCode.created_at.desc())
        )
        candidates = list(result.scalars().all())

        now = _now()
        valid = None
        for c in candidates:
            if c.expires_at > now and _verify_code(code, c.code_hash):
                valid = c
                break

        if valid is None:
            return False, "Код неверный или истёк"

        # Помечаем использованным.
        valid.used = True
        # Обновляем пароль.
        user = await UserRepository(session).get_by_email(email)
        if not user:
            return False, "Пользователь не найден"
        user.password_hash = _hash_code(new_password)  # используем ту же bcrypt-функцию
        user.is_web_active = True  # на всякий случай разблокируем
        await session.commit()
        logger.info("password reset for %s", email)
        return True, ""
