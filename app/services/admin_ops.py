"""
Сервисный слой для админских операций (CRUD), общий для /admin/* и /miniapp/api/*.

Каждый метод — атомарная операция над БД. Роутеры делают только авторизацию,
парсинг входа и формирование ответа.
"""
from datetime import date, time as dt_time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.events import EventRepository
from app.repositories.materials import MaterialCategoryRepository, MaterialRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.subjects import SubjectRepository, TeacherRepository


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

async def create_event(
    session: AsyncSession,
    *,
    title: str,
    event_date: date,
    event_time: Optional[dt_time],
    description: Optional[str],
    notify_days_before: list[int],
):
    return await EventRepository(session).create(
        title=title.strip(),
        event_date=event_date,
        event_time=event_time,
        description=description.strip() if description else None,
        notify_days_before=notify_days_before,
    )


async def update_event(
    session: AsyncSession,
    event_id: int,
    *,
    title: str,
    event_date: date,
    event_time: Optional[dt_time],
    description: Optional[str],
    notify_days_before: list[int],
) -> bool:
    repo = EventRepository(session)
    event = await repo.get_by_id(event_id)
    if not event:
        return False
    await repo.update(
        event,
        title=title.strip(),
        event_date=event_date,
        event_time=event_time,
        description=description.strip() if description else None,
        notify_days_before=notify_days_before,
    )
    return True


async def delete_event(session: AsyncSession, event_id: int) -> bool:
    repo = EventRepository(session)
    event = await repo.get_by_id(event_id)
    if not event:
        return False
    await repo.soft_delete(event)
    return True


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def _monday(d: date) -> date:
    from datetime import timedelta
    return d - timedelta(days=d.weekday())


async def create_schedule_entry(
    session: AsyncSession,
    *,
    session_week: date,
    day_of_week: int,
    pair_number: int,
    time_start: dt_time,
    time_end: dt_time,
    subject: str,
    teacher: Optional[str],
    room: Optional[str],
    subgroup: Optional[int],
) -> tuple[bool, Optional[int]]:
    """Создаёт запись расписания. Возвращает (ok, id_or_error_code)."""
    repo = ScheduleRepository(session)
    sw = _monday(session_week)
    if await repo.entry_exists(sw, day_of_week, pair_number):
        return False, "slot_taken"
    entry = await repo.create_entry(
        session_week=sw,
        day_of_week=day_of_week,
        pair_number=pair_number,
        time_start=time_start,
        time_end=time_end,
        subject=subject.strip(),
        teacher=teacher.strip() if teacher else None,
        room=room.strip() if room else None,
        subgroup=subgroup,
    )
    return True, entry.id


async def update_schedule_entry(
    session: AsyncSession,
    entry_id: int,
    *,
    session_week: date,
    day_of_week: int,
    pair_number: int,
    time_start: dt_time,
    time_end: dt_time,
    subject: str,
    teacher: Optional[str],
    room: Optional[str],
    subgroup: Optional[int],
) -> bool:
    repo = ScheduleRepository(session)
    entry = await repo.get_entry_by_id(entry_id)
    if not entry:
        return False
    sw = _monday(session_week)
    if await repo.entry_exists(sw, day_of_week, pair_number, exclude_id=entry_id):
        return False
    await repo.update_entry(
        entry,
        session_week=sw,
        day_of_week=day_of_week,
        pair_number=pair_number,
        time_start=time_start,
        time_end=time_end,
        subject=subject.strip(),
        teacher=teacher.strip() if teacher else None,
        room=room.strip() if room else None,
        subgroup=subgroup,
    )
    return True


async def delete_schedule_entry(session: AsyncSession, entry_id: int) -> bool:
    repo = ScheduleRepository(session)
    entry = await repo.get_entry_by_id(entry_id)
    if not entry:
        return False
    await repo.soft_delete_entry(entry)
    return True


# ---------------------------------------------------------------------------
# Material categories
# ---------------------------------------------------------------------------

async def create_category(session: AsyncSession, *, name: str, emoji: str = "📁"):
    return await MaterialCategoryRepository(session).create(
        name=name.strip(), emoji=emoji.strip() or "📁"
    )


async def update_category(session: AsyncSession, cat_id: int, *, name: str, emoji: str) -> bool:
    repo = MaterialCategoryRepository(session)
    cat = await repo.get_by_id(cat_id)
    if not cat:
        return False
    await repo.update(cat, name=name.strip(), emoji=emoji.strip() or "📁")
    return True


async def delete_category(session: AsyncSession, cat_id: int) -> bool:
    repo = MaterialCategoryRepository(session)
    cat = await repo.get_by_id(cat_id)
    if not cat:
        return False
    await repo.delete(cat)
    return True


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

async def create_material(
    session: AsyncSession,
    *,
    category_id: int,
    title: str,
    url: Optional[str],
    description: Optional[str],
    material_type: str = "link",
):
    return await MaterialRepository(session).create(
        category_id=category_id,
        title=title.strip(),
        material_type=material_type,
        url=url.strip() if url else None,
        description=description.strip() if description else None,
    )


async def update_material(
    session: AsyncSession,
    mat_id: int,
    *,
    title: str,
    url: Optional[str],
    description: Optional[str],
    is_visible: bool = True,
    sort_order: int = 0,
) -> bool:
    repo = MaterialRepository(session)
    mat = await repo.get_by_id(mat_id)
    if not mat:
        return False
    await repo.update(
        mat,
        title=title.strip(),
        url=url.strip() if url else None,
        description=description.strip() if description else None,
        is_visible=is_visible,
        sort_order=sort_order,
    )
    return True


async def delete_material(session: AsyncSession, mat_id: int) -> bool:
    repo = MaterialRepository(session)
    mat = await repo.get_by_id(mat_id)
    if not mat:
        return False
    await repo.delete(mat)
    return True


# ---------------------------------------------------------------------------
# References (subjects & teachers)
# ---------------------------------------------------------------------------

async def create_subject(session: AsyncSession, *, name: str, short_name: Optional[str] = None):
    return await SubjectRepository(session).create(
        name=name.strip(), short_name=short_name.strip() if short_name else None
    )


async def update_subject(session: AsyncSession, subject_id: int, *, name: str, short_name: Optional[str]) -> bool:
    repo = SubjectRepository(session)
    obj = await repo.get_by_id(subject_id)
    if not obj:
        return False
    await repo.update(obj, name=name.strip(), short_name=short_name.strip() if short_name else None)
    return True


async def delete_subject(session: AsyncSession, subject_id: int) -> bool:
    repo = SubjectRepository(session)
    obj = await repo.get_by_id(subject_id)
    if not obj:
        return False
    await repo.delete(obj)
    return True


async def create_teacher(session: AsyncSession, *, full_name: str, short_name: Optional[str] = None):
    return await TeacherRepository(session).create(
        full_name=full_name.strip(), short_name=short_name.strip() if short_name else None
    )


async def update_teacher(session: AsyncSession, teacher_id: int, *, full_name: str, short_name: Optional[str]) -> bool:
    repo = TeacherRepository(session)
    obj = await repo.get_by_id(teacher_id)
    if not obj:
        return False
    await repo.update(obj, full_name=full_name.strip(), short_name=short_name.strip() if short_name else None)
    return True


async def delete_teacher(session: AsyncSession, teacher_id: int) -> bool:
    repo = TeacherRepository(session)
    obj = await repo.get_by_id(teacher_id)
    if not obj:
        return False
    await repo.delete(obj)
    return True
