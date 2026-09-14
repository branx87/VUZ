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
