from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ScheduleEntry, ScheduleException


class ScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_entries_for_day(self, day_of_week: int, session_week: date) -> list[ScheduleEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                and_(
                    ScheduleEntry.day_of_week == day_of_week,
                    ScheduleEntry.session_week == session_week,
                    ScheduleEntry.is_active == True,
                )
            )
            .order_by(ScheduleEntry.pair_number)
        )
        return list(result.scalars().all())

    async def get_entries_for_session_week(self, session_week: date) -> list[ScheduleEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                and_(
                    ScheduleEntry.session_week == session_week,
                    ScheduleEntry.is_active == True,
                )
            )
            .order_by(ScheduleEntry.day_of_week, ScheduleEntry.pair_number)
        )
        return list(result.scalars().all())

    async def get_session_weeks(self) -> list[date]:
        result = await self.session.execute(
            select(ScheduleEntry.session_week)
            .where(ScheduleEntry.is_active == True)
            .distinct()
            .order_by(ScheduleEntry.session_week)
        )
        return list(result.scalars().all())

    async def get_all_entries(self) -> list[ScheduleEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(ScheduleEntry.is_active == True)
            .order_by(ScheduleEntry.session_week, ScheduleEntry.day_of_week, ScheduleEntry.pair_number)
        )
        return list(result.scalars().all())

    async def get_entry_by_id(self, entry_id: int) -> ScheduleEntry | None:
        return await self.session.get(ScheduleEntry, entry_id)

    async def entry_exists(
        self,
        session_week: date,
        day_of_week: int,
        pair_number: int,
        exclude_id: int | None = None,
    ) -> bool:
        q = select(ScheduleEntry.id).where(
            and_(
                ScheduleEntry.session_week == session_week,
                ScheduleEntry.day_of_week == day_of_week,
                ScheduleEntry.pair_number == pair_number,
                ScheduleEntry.is_active == True,
            )
        )
        if exclude_id is not None:
            q = q.where(ScheduleEntry.id != exclude_id)
        result = await self.session.execute(q)
        return result.scalar() is not None

    async def get_exceptions_for_date(self, target_date: date) -> list[ScheduleException]:
        result = await self.session.execute(
            select(ScheduleException).where(ScheduleException.date == target_date)
        )
        return list(result.scalars().all())

    async def get_exceptions_for_week(self, session_week: date) -> list[ScheduleException]:
        week_end = session_week + timedelta(days=6)
        result = await self.session.execute(
            select(ScheduleException)
            .where(ScheduleException.date >= session_week)
            .where(ScheduleException.date <= week_end)
        )
        return list(result.scalars().all())

    async def get_exceptions_upcoming(self, from_date: date, limit: int = 30) -> list[ScheduleException]:
        result = await self.session.execute(
            select(ScheduleException)
            .where(ScheduleException.date >= from_date)
            .order_by(ScheduleException.date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_exception_by_id(self, exc_id: int) -> ScheduleException | None:
        return await self.session.get(ScheduleException, exc_id)

    async def create_entry(self, **kwargs) -> ScheduleEntry:
        entry = ScheduleEntry(**kwargs)
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def update_entry(self, entry: ScheduleEntry, **kwargs) -> ScheduleEntry:
        for k, v in kwargs.items():
            setattr(entry, k, v)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def soft_delete_entry(self, entry: ScheduleEntry) -> None:
        entry.is_active = False
        await self.session.commit()

    async def create_exception(self, **kwargs) -> ScheduleException:
        exc = ScheduleException(**kwargs)
        self.session.add(exc)
        await self.session.commit()
        await self.session.refresh(exc)
        return exc

    async def delete_exception(self, exc: ScheduleException) -> None:
        await self.session.delete(exc)
        await self.session.commit()
