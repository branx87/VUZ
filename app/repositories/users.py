import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        platform: str,
        platform_user_id: str,
        username: str | None,
        full_name: str | None,
    ) -> User:
        result = await self.session.execute(
            select(User).where(
                User.platform == platform,
                User.platform_user_id == platform_user_id,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                platform=platform,
                platform_user_id=platform_user_id,
                username=username,
                full_name=full_name,
            )
            self.session.add(user)
            logger.info("user registered: platform=%s id=%s", platform, platform_user_id)
        else:
            user.username = username
            user.full_name = full_name
            logger.debug("user updated: platform=%s id=%s", platform, platform_user_id)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_all_telegram(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.platform == "telegram")
        )
        return list(result.scalars().all())

    async def get_all_vk(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.platform == "vk")
        )
        return list(result.scalars().all())

    # ----- Web portal -----

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_all_web(self) -> list[User]:
        """Все юзеры, у которых заполнен email (т.е. пытались регистрироваться)."""
        result = await self.session.execute(
            select(User).where(User.email.is_not(None)).order_by(User.is_web_active, User.id)
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
        """Создаёт активного web-юзера. Заблокировать можно через set_web_active(False)."""
        full_name = f"{first_name.strip()} {last_name.strip()}".strip()
        user = User(
            platform="web",
            platform_user_id=email,
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

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.commit()
