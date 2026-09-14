import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Subject, Teacher

logger = logging.getLogger(__name__)


class SubjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Subject]:
        result = await self.session.execute(
            select(Subject).order_by(Subject.sort_order, Subject.name)
        )
        subjects = list(result.scalars().all())
        logger.debug("[SubjectRepo.get_all] fetched %d subjects", len(subjects))
        return subjects

    async def get_by_id(self, subject_id: int) -> Subject | None:
        return await self.session.get(Subject, subject_id)

    async def create(self, name: str, short_name: str | None = None) -> Subject:
        subject = Subject(name=name, short_name=short_name)
        self.session.add(subject)
        await self.session.commit()
        await self.session.refresh(subject)
        return subject

    async def update(self, obj: Subject, name: str, short_name: str | None) -> Subject:
        obj.name = name
        obj.short_name = short_name
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: Subject) -> None:
        await self.session.delete(obj)
        await self.session.commit()


class TeacherRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Teacher]:
        result = await self.session.execute(
            select(Teacher).order_by(Teacher.sort_order, Teacher.full_name)
        )
        teachers = list(result.scalars().all())
        logger.debug("[TeacherRepo.get_all] fetched %d teachers", len(teachers))
        return teachers

    async def get_by_id(self, teacher_id: int) -> Teacher | None:
        return await self.session.get(Teacher, teacher_id)

    async def create(self, full_name: str, short_name: str | None = None) -> Teacher:
        teacher = Teacher(full_name=full_name, short_name=short_name)
        self.session.add(teacher)
        await self.session.commit()
        await self.session.refresh(teacher)
        return teacher

    async def update(self, obj: Teacher, full_name: str, short_name: str | None) -> Teacher:
        obj.full_name = full_name
        obj.short_name = short_name
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: Teacher) -> None:
        await self.session.delete(obj)
        await self.session.commit()
