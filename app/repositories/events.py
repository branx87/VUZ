from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Event


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Event]:
        result = await self.session.execute(
            select(Event).where(Event.is_active == True).order_by(Event.event_date)
        )
        return list(result.scalars().all())

    async def get_upcoming(self, from_date: date, limit: int = 50) -> list[Event]:
        result = await self.session.execute(
            select(Event)
            .where(Event.is_active == True, Event.event_date >= from_date)
            .order_by(Event.event_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, event_id: int) -> Event | None:
        return await self.session.get(Event, event_id)

    async def create(self, **kwargs) -> Event:
        event = Event(**kwargs)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def update(self, event: Event, **kwargs) -> Event:
        for k, v in kwargs.items():
            setattr(event, k, v)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def soft_delete(self, obj: Event) -> None:
        obj.is_active = False
        await self.session.commit()
