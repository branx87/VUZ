from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app.repositories.schedule import ScheduleRepository

DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass
class EffectiveLesson:
    pair_number: int
    time_start: object  # datetime.time
    time_end: object
    subject: str
    teacher: Optional[str]
    room: Optional[str]
    subgroup: Optional[int]
    is_modified: bool = field(default=False)
    exception_type: Optional[str] = field(default=None)  # "replace" | "add"
    reason: Optional[str] = field(default=None)


class ScheduleService:
    def __init__(self, repo: ScheduleRepository):
        self.repo = repo

    async def get_for_date(self, target_date: date) -> list[EffectiveLesson]:
        dow = target_date.weekday()
        session_week = target_date - timedelta(days=dow)

        entries = await self.repo.get_entries_for_day(dow, session_week)

        exceptions = await self.repo.get_exceptions_for_date(target_date)
        cancel_ids = {e.original_entry_id for e in exceptions if e.exception_type == "cancel"}
        replace_map = {e.original_entry_id: e for e in exceptions if e.exception_type == "replace"}
        additions = [e for e in exceptions if e.exception_type == "add"]

        result: list[EffectiveLesson] = []
        for entry in entries:
            if entry.id in cancel_ids:
                continue
            if entry.id in replace_map:
                exc = replace_map[entry.id]
                result.append(EffectiveLesson(
                    pair_number=exc.pair_number or entry.pair_number,
                    time_start=exc.time_start or entry.time_start,
                    time_end=exc.time_end or entry.time_end,
                    subject=exc.subject or entry.subject,
                    teacher=exc.teacher if exc.teacher is not None else entry.teacher,
                    room=exc.room if exc.room is not None else entry.room,
                    subgroup=entry.subgroup,
                    is_modified=True,
                    exception_type="replace",
                    reason=exc.reason,
                ))
            else:
                result.append(EffectiveLesson(
                    pair_number=entry.pair_number,
                    time_start=entry.time_start,
                    time_end=entry.time_end,
                    subject=entry.subject,
                    teacher=entry.teacher,
                    room=entry.room,
                    subgroup=entry.subgroup,
                ))

        for exc in additions:
            result.append(EffectiveLesson(
                pair_number=exc.pair_number or 99,
                time_start=exc.time_start,
                time_end=exc.time_end,
                subject=exc.subject,
                teacher=exc.teacher,
                room=exc.room,
                subgroup=None,
                is_modified=True,
                exception_type="add",
                reason=exc.reason,
            ))

        result.sort(key=lambda x: x.pair_number)
        return result

    async def get_for_week(self, week_start: date) -> dict[int, list[EffectiveLesson]]:
        return {
            i: await self.get_for_date(week_start + timedelta(days=i))
            for i in range(6)  # Пн–Сб
        }

    @staticmethod
    def week_start_for(d: date) -> date:
        return d - timedelta(days=d.weekday())
