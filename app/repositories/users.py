import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ----- Telegram -----

    async def upsert_telegram(
        self,
        telegram_user_id: str,
        username: str | None,
        full_name: str | None,
    ) -> User:
        """Найти юзера по telegram_user_id или создать. Обновляет имя пользователя в TG,
        и дозаполняет full_name, если он был пустой."""
        result = await self.session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                telegram_username=username,
                full_name=full_name,
            )
            self.session.add(user)
            logger.info("telegram user registered: id=%s", telegram_user_id)
        else:
            user.telegram_username = username
            if full_name and not user.full_name:
                user.full_name = full_name
            logger.debug("telegram user updated: id=%s", telegram_user_id)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    # ----- VK -----

    async def upsert_vk(
        self,
        vk_user_id: str,
        username: str | None,
        full_name: str | None,
    ) -> User:
        result = await self.session.execute(
            select(User).where(User.vk_user_id == vk_user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                vk_user_id=vk_user_id,
                vk_username=username,
                full_name=full_name,
            )
            self.session.add(user)
            logger.info("vk user registered: id=%s", vk_user_id)
        else:
            user.vk_username = username
            if full_name and not user.full_name:
                user.full_name = full_name
            logger.debug("vk user updated: id=%s", vk_user_id)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    # ----- Web portal -----

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_all_web(self) -> list[User]:
        """Только web-юзеры (у которых есть email)."""
        result = await self.session.execute(
            select(User).where(User.email.is_not(None)).order_by(User.is_web_active, User.id)
        )
        return list(result.scalars().all())

    async def get_all_users(self) -> list[User]:
        """Все юзеры — web, TG и VK. Сортировка: сначала активные web, потом остальные."""
        result = await self.session.execute(
            select(User).order_by(User.email.is_not(None).desc(), User.is_web_active, User.id)
        )
        return list(result.scalars().all())

    async def create_web_user(
        self,
        *,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
    ) -> User:
        """Создаёт web-юзера. Если человек уже есть в TG/VK — это будет новая строка;
        админ может потом объединить вручную (TODO: инструмент мёржа)."""
        full_name = f"{first_name.strip()} {last_name.strip()}".strip()
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            is_web_active=True,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        logger.info("web user registered: id=%d email=%s", user.id, email)
        return user

    async def set_web_active(self, user: User, active: bool) -> User:
        user.is_web_active = active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password_hash(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        await self.session.commit()
        await self.session.refresh(user)
        return user

    # ----- Рассылки -----

    async def get_all_telegram(self) -> list[User]:
        """Юзеры, к которым бот знает как обращаться в Telegram."""
        result = await self.session.execute(
            select(User).where(User.telegram_user_id.is_not(None))
        )
        return list(result.scalars().all())

    async def get_all_vk(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.vk_user_id.is_not(None))
        )
        return list(result.scalars().all())

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.commit()
