from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import Material, MaterialCategory


class MaterialCategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_with_materials(self) -> list[MaterialCategory]:
        result = await self.session.execute(
            select(MaterialCategory)
            .options(selectinload(MaterialCategory.materials))
            .order_by(MaterialCategory.sort_order, MaterialCategory.name)
        )
        return list(result.scalars().all())

    async def get_all(self) -> list[MaterialCategory]:
        result = await self.session.execute(
            select(MaterialCategory).order_by(MaterialCategory.sort_order, MaterialCategory.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, cat_id: int) -> MaterialCategory | None:
        return await self.session.get(MaterialCategory, cat_id)

    async def create(self, name: str, emoji: str = "📁") -> MaterialCategory:
        cat = MaterialCategory(name=name, emoji=emoji)
        self.session.add(cat)
        await self.session.commit()
        await self.session.refresh(cat)
        return cat

    async def update(self, obj: MaterialCategory, name: str, emoji: str) -> MaterialCategory:
        obj.name = name
        obj.emoji = emoji
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: MaterialCategory) -> None:
        await self.session.delete(obj)
        await self.session.commit()


class MaterialRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, mat_id: int) -> Material | None:
        return await self.session.get(Material, mat_id)

    async def create(self, **kwargs) -> Material:
        mat = Material(**kwargs)
        self.session.add(mat)
        await self.session.commit()
        await self.session.refresh(mat)
        return mat

    async def update(
        self,
        obj: Material,
        title: str,
        url: str | None,
        description: str | None,
        is_visible: bool = True,
        sort_order: int = 0,
    ) -> Material:
        obj.title = title
        obj.url = url
        obj.description = description
        obj.is_visible = is_visible
        obj.sort_order = sort_order
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: Material) -> None:
        await self.session.delete(obj)
        await self.session.commit()
