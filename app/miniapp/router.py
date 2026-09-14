import hashlib
import hmac as _hmac
import json as _json
import logging
from datetime import date, time as dt_time, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.repositories.events import EventRepository
from app.repositories.materials import MaterialCategoryRepository, MaterialRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.subjects import SubjectRepository, TeacherRepository
from app.services import admin_ops

logger = logging.getLogger(__name__)
router = APIRouter()

_TEMPLATE = Path(__file__).parent / "templates" / "index.html"
_FILES_DIR = Path(settings.files_dir).resolve()


@lru_cache(maxsize=1)
def _load_index_html() -> str:
    """Грузит index.html один раз. Кэш сбрасывается при рестарте процесса."""
    return _TEMPLATE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _verify_admin(init_data: str) -> bool:
    if not init_data:
        logger.debug("[miniapp.admin] no initData")
        return False
    if not settings.telegram_bot_token or not settings.admin_tg_id:
        logger.warning("[miniapp.admin] bot token or admin_tg_id not configured")
        return False
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_ = params.pop("hash", None)
        if not hash_:
            logger.warning("[miniapp.admin] no hash in initData")
            return False
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret = _hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected = _hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(expected, hash_):
            logger.warning("[miniapp.admin] HMAC mismatch")
            return False
        user = _json.loads(params.get("user", "{}"))
        user_id = int(user.get("id", 0))
        ok = user_id == settings.admin_tg_id
        logger.info("[miniapp.admin] user_id=%d admin_tg_id=%d match=%s", user_id, settings.admin_tg_id, ok)
        return ok
    except Exception as e:
        logger.warning("[miniapp.admin] verification exception: %s", e)
        return False


def _admin_required(
    x_telegram_init_data: str = Header(default=""),
    x_admin_token: str = Header(default=""),
) -> None:
    if _verify_admin(x_telegram_init_data):
        return
    expected = settings.admin_secret_token
    if expected and x_admin_token and _hmac.compare_digest(x_admin_token, expected):
        return
    raise HTTPException(status_code=403, detail="Not authorized")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AdminTokenBody(BaseModel):
    token: str


class EventBody(BaseModel):
    title: str
    event_date: str
    event_time: str | None = None
    description: str | None = None
    notify_days_before: list[int] = [3, 1]


class ScheduleEntryBody(BaseModel):
    session_week: str
    day_of_week: int
    pair_number: int
    time_start: str
    time_end: str
    subject: str
    teacher: str | None = None
    room: str | None = None
    subgroup: int | None = None


class CategoryBody(BaseModel):
    name: str
    emoji: str = "📁"


class MaterialBody(BaseModel):
    category_id: int
    title: str
    url: str | None = None
    description: str | None = None
    is_visible: bool = True
    sort_order: int = 0


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def miniapp_index() -> HTMLResponse:
    return HTMLResponse(_load_index_html())


# ---------------------------------------------------------------------------
# Public read endpoints
# ---------------------------------------------------------------------------

@router.get("/api/is_admin")
async def miniapp_is_admin(
    x_telegram_init_data: str = Header(default=""),
    x_admin_token: str = Header(default=""),
):
    via_tg = _verify_admin(x_telegram_init_data)
    expected = settings.admin_secret_token
    via_token = bool(
        expected and x_admin_token and _hmac.compare_digest(x_admin_token, expected)
    )
    return {"is_admin": via_tg or via_token}


@router.post("/api/admin_login")
async def miniapp_admin_login(body: AdminTokenBody):
    expected = settings.admin_secret_token
    if not expected or not _hmac.compare_digest(body.token, expected):
        raise HTTPException(status_code=403, detail="wrong_token")
    logger.info("[miniapp.admin] admin logged in via token")
    return {"ok": True}


@router.get("/api/schedule")
async def miniapp_schedule(
    week: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if week:
        try:
            pivot = date.fromisoformat(week)
        except ValueError:
            return JSONResponse({"error": "invalid week format, use YYYY-MM-DD"}, status_code=400)
    else:
        pivot = date.today()
    session_week = pivot - timedelta(days=pivot.weekday())
    entries = await ScheduleRepository(session).get_entries_for_session_week(session_week)
    logger.debug("[miniapp] schedule: week=%s entries=%d", session_week, len(entries))
    return [
        {
            "id": e.id,
            "day_of_week": e.day_of_week,
            "pair_number": e.pair_number,
            "time_start": str(e.time_start) if e.time_start else None,
            "time_end": str(e.time_end) if e.time_end else None,
            "subject": e.subject,
            "teacher": e.teacher,
            "room": e.room,
            "subgroup": e.subgroup,
            "session_week": str(e.session_week),
        }
        for e in entries
    ]


@router.get("/api/schedule/weeks")
async def miniapp_schedule_weeks(session: AsyncSession = Depends(get_session)):
    weeks = await ScheduleRepository(session).get_session_weeks()
    return [str(w) for w in weeks]


@router.get("/api/events")
async def miniapp_events(session: AsyncSession = Depends(get_session)):
    events = await EventRepository(session).get_upcoming(from_date=date.today())
    logger.debug("[miniapp] events: count=%d", len(events))
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "event_date": str(e.event_date),
            "event_time": str(e.event_time) if e.event_time else None,
            "notify_days_before": e.notify_days_before,
        }
        for e in events
    ]


@router.get("/api/materials")
async def miniapp_materials(session: AsyncSession = Depends(get_session)):
    cats = await MaterialCategoryRepository(session).get_all_with_materials()
    logger.debug("[miniapp] materials: categories=%d", len(cats))
    return [
        {
            "id": c.id,
            "name": c.name,
            "emoji": c.emoji,
            "materials": [
                {
                    "id": m.id,
                    "title": m.title,
                    "description": m.description,
                    "material_type": m.material_type,
                    "url": m.url,
                    "download_url": (
                        f"/miniapp/api/materials/{m.id}/download" if m.material_type == "file" else None
                    ),
                    "file_name": m.file_name if m.material_type == "file" else None,
                    "file_size": m.file_size if m.material_type == "file" else None,
                }
                for m in c.materials
                if m.is_visible
            ],
        }
        for c in cats
    ]


@router.get("/api/materials/categories")
async def miniapp_material_categories(session: AsyncSession = Depends(get_session)):
    cats = await MaterialCategoryRepository(session).get_all()
    return [{"id": c.id, "name": c.name, "emoji": c.emoji} for c in cats]


@router.get("/api/subjects")
async def miniapp_subjects(session: AsyncSession = Depends(get_session)):
    subjects = await SubjectRepository(session).get_all()
    logger.debug("[miniapp] subjects: count=%d", len(subjects))
    return [{"name": s.name, "short_name": s.short_name} for s in subjects]


@router.get("/api/teachers")
async def miniapp_teachers(session: AsyncSession = Depends(get_session)):
    teachers = await TeacherRepository(session).get_all()
    logger.debug("[miniapp] teachers: count=%d", len(teachers))
    return [{"full_name": t.full_name, "short_name": t.short_name} for t in teachers]


# ---------------------------------------------------------------------------
# Admin — Events
# ---------------------------------------------------------------------------

@router.post("/api/events", dependencies=[Depends(_admin_required)])
async def miniapp_create_event(body: EventBody, session: AsyncSession = Depends(get_session)):
    event = await admin_ops.create_event(
        session,
        title=body.title,
        event_date=date.fromisoformat(body.event_date),
        event_time=dt_time.fromisoformat(body.event_time) if body.event_time else None,
        description=body.description,
        notify_days_before=body.notify_days_before,
    )
    logger.info("[miniapp.admin] created event id=%d %r", event.id, event.title)
    return {"id": event.id}


@router.put("/api/events/{event_id}", dependencies=[Depends(_admin_required)])
async def miniapp_update_event(
    event_id: int, body: EventBody, session: AsyncSession = Depends(get_session)
):
    ok = await admin_ops.update_event(
        session,
        event_id,
        title=body.title,
        event_date=date.fromisoformat(body.event_date),
        event_time=dt_time.fromisoformat(body.event_time) if body.event_time else None,
        description=body.description,
        notify_days_before=body.notify_days_before,
    )
    if not ok:
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] updated event id=%d", event_id)
    return {"ok": True}


@router.delete("/api/events/{event_id}", dependencies=[Depends(_admin_required)])
async def miniapp_delete_event(event_id: int, session: AsyncSession = Depends(get_session)):
    if not await admin_ops.delete_event(session, event_id):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] deleted event id=%d", event_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin — Schedule
# ---------------------------------------------------------------------------

@router.post("/api/schedule", dependencies=[Depends(_admin_required)])
async def miniapp_create_schedule_entry(
    body: ScheduleEntryBody, session: AsyncSession = Depends(get_session)
):
    ok, payload = await admin_ops.create_schedule_entry(
        session,
        session_week=date.fromisoformat(body.session_week),
        day_of_week=body.day_of_week,
        pair_number=body.pair_number,
        time_start=dt_time.fromisoformat(body.time_start),
        time_end=dt_time.fromisoformat(body.time_end),
        subject=body.subject,
        teacher=body.teacher,
        room=body.room,
        subgroup=body.subgroup,
    )
    if not ok:
        raise HTTPException(status_code=409, detail=payload or "slot_taken")
    logger.info("[miniapp.admin] created schedule entry id=%d", payload)
    return {"id": payload}


@router.put("/api/schedule/{entry_id}", dependencies=[Depends(_admin_required)])
async def miniapp_update_schedule_entry(
    entry_id: int, body: ScheduleEntryBody, session: AsyncSession = Depends(get_session)
):
    ok = await admin_ops.update_schedule_entry(
        session,
        entry_id,
        session_week=date.fromisoformat(body.session_week),
        day_of_week=body.day_of_week,
        pair_number=body.pair_number,
        time_start=dt_time.fromisoformat(body.time_start),
        time_end=dt_time.fromisoformat(body.time_end),
        subject=body.subject,
        teacher=body.teacher,
        room=body.room,
        subgroup=body.subgroup,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="slot_taken")
    logger.info("[miniapp.admin] updated schedule entry id=%d", entry_id)
    return {"ok": True}


@router.delete("/api/schedule/{entry_id}", dependencies=[Depends(_admin_required)])
async def miniapp_delete_schedule_entry(
    entry_id: int, session: AsyncSession = Depends(get_session)
):
    if not await admin_ops.delete_schedule_entry(session, entry_id):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] deleted schedule entry id=%d", entry_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public file download
# ---------------------------------------------------------------------------

@router.get("/api/materials/{mat_id}/download")
async def miniapp_download_material(mat_id: int, session: AsyncSession = Depends(get_session)):
    mat = await MaterialRepository(session).get_by_id(mat_id)
    if not mat or mat.material_type != "file" or not mat.file_path:
        raise HTTPException(status_code=404)
    # file_path хранится относительно FILES_DIR — собираем абсолютный путь
    file_path = (_FILES_DIR / mat.file_path).resolve()
    # Защита от path traversal: file_path должен оставаться внутри _FILES_DIR
    if _FILES_DIR not in file_path.parents and file_path != _FILES_DIR:
        logger.warning("Path traversal attempt: %s", file_path)
        raise HTTPException(status_code=400, detail="invalid path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file missing on disk")
    return FileResponse(
        path=str(file_path),
        filename=mat.file_name or file_path.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Admin — Materials
# ---------------------------------------------------------------------------

@router.post("/api/materials/category", dependencies=[Depends(_admin_required)])
async def miniapp_create_category(body: CategoryBody, session: AsyncSession = Depends(get_session)):
    cat = await admin_ops.create_category(session, name=body.name, emoji=body.emoji)
    logger.info("[miniapp.admin] created category id=%d %r", cat.id, cat.name)
    return {"id": cat.id}


@router.put("/api/materials/category/{cat_id}", dependencies=[Depends(_admin_required)])
async def miniapp_update_category(
    cat_id: int, body: CategoryBody, session: AsyncSession = Depends(get_session)
):
    if not await admin_ops.update_category(session, cat_id, name=body.name, emoji=body.emoji):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] updated category id=%d", cat_id)
    return {"ok": True}


@router.delete("/api/materials/category/{cat_id}", dependencies=[Depends(_admin_required)])
async def miniapp_delete_category(cat_id: int, session: AsyncSession = Depends(get_session)):
    if not await admin_ops.delete_category(session, cat_id):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] deleted category id=%d", cat_id)
    return {"ok": True}


@router.post("/api/materials", dependencies=[Depends(_admin_required)])
async def miniapp_create_material(body: MaterialBody, session: AsyncSession = Depends(get_session)):
    mat = await admin_ops.create_material(
        session,
        category_id=body.category_id,
        title=body.title,
        url=body.url,
        description=body.description,
    )
    logger.info("[miniapp.admin] created material id=%d %r", mat.id, mat.title)
    return {"id": mat.id}


@router.put("/api/materials/{mat_id}", dependencies=[Depends(_admin_required)])
async def miniapp_update_material(
    mat_id: int, body: MaterialBody, session: AsyncSession = Depends(get_session)
):
    if not await admin_ops.update_material(
        session,
        mat_id,
        title=body.title,
        url=body.url,
        description=body.description,
        is_visible=body.is_visible,
        sort_order=body.sort_order,
    ):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] updated material id=%d", mat_id)
    return {"ok": True}


@router.delete("/api/materials/{mat_id}", dependencies=[Depends(_admin_required)])
async def miniapp_delete_material(mat_id: int, session: AsyncSession = Depends(get_session)):
    if not await admin_ops.delete_material(session, mat_id):
        raise HTTPException(status_code=404)
    logger.info("[miniapp.admin] deleted material id=%d", mat_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())
