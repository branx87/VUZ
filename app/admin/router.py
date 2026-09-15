import hmac
import json
import logging
from datetime import date, time as dt_time, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import AsyncSessionLocal
from app.repositories.events import EventRepository
from app.repositories.materials import MaterialCategoryRepository, MaterialRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.subjects import SubjectRepository, TeacherRepository
from app.repositories.users import UserRepository
from app.services.schedule import DAY_NAMES

logger = logging.getLogger(__name__)
_TMPL_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TMPL_DIR))

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

COOKIE = "admin_token"


def _authed(request: Request) -> bool:
    cookie_token = request.cookies.get(COOKIE, "")
    expected = settings.admin_secret_token
    return bool(expected) and hmac.compare_digest(cookie_token, expected)


def _redirect_login(next_path: str = "/admin/schedule") -> RedirectResponse:
    return RedirectResponse(f"/admin/login?next={next_path}", status_code=302)


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
async def do_login(
    request: Request,
    token: Annotated[str, Form()],
    next: str = "/admin/schedule",
):
    expected = settings.admin_secret_token
    if expected and hmac.compare_digest(token, expected):
        resp = RedirectResponse(next, status_code=302)
        resp.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
            max_age=86400 * 30,
        )
        return resp
    return RedirectResponse("/admin/login?error=1", status_code=302)


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=302)
    resp.delete_cookie(COOKIE, secure=settings.cookie_secure)
    return resp


# ---------------------------------------------------------------------------
# Schedule — entries
# ---------------------------------------------------------------------------

def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_time(value: str) -> dt_time | None:
    try:
        return dt_time.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@router.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request, week: str = "", error: str = ""):
    if not _authed(request):
        return _redirect_login("/admin/schedule")

    today = date.today()
    try:
        sel = _monday(date.fromisoformat(week)) if week else _monday(today)
    except ValueError:
        sel = _monday(today)

    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        entries = await repo.get_entries_for_session_week(sel)
        session_weeks_raw = await repo.get_session_weeks()
        exceptions = await repo.get_exceptions_upcoming(today)
        week_exceptions = await repo.get_exceptions_for_week(sel)
        subjects = await SubjectRepository(session).get_all()
        teachers = await TeacherRepository(session).get_all()

    by_day: dict[int, list] = {i: [] for i in range(7)}
    for e in entries:
        by_day[e.day_of_week].append(e)

    cancelled_ids = {
        ex.original_entry_id
        for ex in week_exceptions
        if ex.exception_type == "cancel" and ex.original_entry_id is not None
    }

    session_weeks = [
        {
            "iso": sw.isoformat(),
            "label": f"{sw.strftime('%d.%m')}–{(sw + timedelta(days=5)).strftime('%d.%m')}",
            "active": sw == sel,
        }
        for sw in session_weeks_raw
    ]

    week_days = [
        {"dow": i, "name": DAY_NAMES[i], "date": (sel + timedelta(days=i)).strftime("%d.%m")}
        for i in range(6)
    ]

    return templates.TemplateResponse(request, "schedule.html", {
        "by_day": by_day,
        "day_names": DAY_NAMES,
        "week_days": week_days,
        "exceptions": exceptions,
        "all_entries": entries,
        "today": today.isoformat(),
        "subjects": subjects,
        "teachers": teachers,
        "session_week": sel,
        "session_week_iso": sel.isoformat(),
        "session_weeks": session_weeks,
        "cancelled_ids": cancelled_ids,
        "error": error,
    })


@router.post("/schedule/entry/add")
async def add_entry(
    request: Request,
    session_week: Annotated[str, Form()],
    day_of_week: Annotated[int, Form()],
    pair_number: Annotated[int, Form()],
    time_start: Annotated[str, Form()],
    time_end: Annotated[str, Form()],
    subject: Annotated[str, Form()],
    teacher: Annotated[str, Form()] = "",
    room: Annotated[str, Form()] = "",
    subgroup: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()

    parsed_sw = _parse_date(session_week)
    parsed_ts = _parse_time(time_start)
    parsed_te = _parse_time(time_end)
    if not (parsed_sw and parsed_ts and parsed_te):
        return RedirectResponse("/admin/schedule?error=bad_date", status_code=302)
    sw = _monday(parsed_sw)
    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        if await repo.entry_exists(sw, day_of_week, pair_number):
            logger.warning("Duplicate slot blocked: week=%s dow=%d pair=%d", sw, day_of_week, pair_number)
            return RedirectResponse(
                f"/admin/schedule?week={sw.isoformat()}&error=slot_taken", status_code=302
            )
        await repo.create_entry(
            session_week=sw,
            day_of_week=day_of_week,
            pair_number=pair_number,
            time_start=parsed_ts,
            time_end=parsed_te,
            subject=subject.strip(),
            teacher=teacher.strip() or None,
            room=room.strip() or None,
            subgroup=int(subgroup) if subgroup.strip() else None,
        )
    return RedirectResponse(f"/admin/schedule?week={sw.isoformat()}", status_code=302)


@router.get("/schedule/entry/{entry_id}/edit", response_class=HTMLResponse)
async def edit_entry_page(request: Request, entry_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        entry = await ScheduleRepository(session).get_entry_by_id(entry_id)
        subjects = await SubjectRepository(session).get_all()
        teachers = await TeacherRepository(session).get_all()
    if not entry:
        return RedirectResponse("/admin/schedule", status_code=302)
    return templates.TemplateResponse(request, "schedule_edit.html", {
        "entry": entry,
        "day_names": DAY_NAMES,
        "subjects": subjects,
        "teachers": teachers,
    })


@router.post("/schedule/entry/{entry_id}/edit")
async def edit_entry(
    request: Request,
    entry_id: int,
    session_week: Annotated[str, Form()],
    day_of_week: Annotated[int, Form()],
    pair_number: Annotated[int, Form()],
    time_start: Annotated[str, Form()],
    time_end: Annotated[str, Form()],
    subject: Annotated[str, Form()],
    teacher: Annotated[str, Form()] = "",
    room: Annotated[str, Form()] = "",
    subgroup: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    parsed_sw = _parse_date(session_week)
    parsed_ts = _parse_time(time_start)
    parsed_te = _parse_time(time_end)
    if not (parsed_sw and parsed_ts and parsed_te):
        return RedirectResponse("/admin/schedule?error=bad_date", status_code=302)
    sw = _monday(parsed_sw)
    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        entry = await repo.get_entry_by_id(entry_id)
        if entry:
            if await repo.entry_exists(sw, day_of_week, pair_number, exclude_id=entry_id):
                logger.warning("Duplicate slot blocked on edit: week=%s dow=%d pair=%d", sw, day_of_week, pair_number)
                return RedirectResponse(
                    f"/admin/schedule?week={sw.isoformat()}&error=slot_taken", status_code=302
                )
            await repo.update_entry(
                entry,
                session_week=sw,
                day_of_week=day_of_week,
                pair_number=pair_number,
                time_start=parsed_ts,
                time_end=parsed_te,
                subject=subject.strip(),
                teacher=teacher.strip() or None,
                room=room.strip() or None,
                subgroup=int(subgroup) if subgroup.strip() else None,
            )
    return RedirectResponse(f"/admin/schedule?week={sw.isoformat()}", status_code=302)


@router.post("/schedule/entry/{entry_id}/delete")
async def delete_entry(request: Request, entry_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        entry = await repo.get_entry_by_id(entry_id)
        if entry:
            sw_iso = entry.session_week.isoformat()
            await repo.soft_delete_entry(entry)
    return RedirectResponse(f"/admin/schedule?week={sw_iso}", status_code=302)


# ---------------------------------------------------------------------------
# Schedule — exceptions
# ---------------------------------------------------------------------------

@router.post("/schedule/entry/{entry_id}/cancel")
async def cancel_entry(
    request: Request,
    entry_id: int,
    session_week: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    parsed_sw = _parse_date(session_week)
    if not parsed_sw:
        return RedirectResponse("/admin/schedule?error=bad_date", status_code=302)
    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        entry = await repo.get_entry_by_id(entry_id)
        if entry:
            cancel_date = parsed_sw + timedelta(days=entry.day_of_week)
            await repo.create_exception(
                date=cancel_date,
                exception_type="cancel",
                original_entry_id=entry_id,
                reason=reason.strip() or None,
            )
            logger.info("[admin.schedule] cancelled entry id=%d on %s", entry_id, cancel_date)
    return RedirectResponse(f"/admin/schedule?week={session_week}", status_code=302)


@router.post("/schedule/exception/add")
async def add_exception(
    request: Request,
    exc_date: Annotated[str, Form()],
    exception_type: Annotated[str, Form()],
    original_entry_id: Annotated[str, Form()] = "",
    pair_number: Annotated[str, Form()] = "",
    time_start: Annotated[str, Form()] = "",
    time_end: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    teacher: Annotated[str, Form()] = "",
    room: Annotated[str, Form()] = "",
    reason: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    parsed_exc = _parse_date(exc_date)
    if not parsed_exc:
        return RedirectResponse("/admin/schedule?error=bad_date", status_code=302)
    async with AsyncSessionLocal() as session:
        await ScheduleRepository(session).create_exception(
            date=parsed_exc,
            exception_type=exception_type,
            original_entry_id=int(original_entry_id) if original_entry_id.strip() else None,
            pair_number=int(pair_number) if pair_number.strip() else None,
            time_start=_parse_time(time_start) if time_start.strip() else None,
            time_end=_parse_time(time_end) if time_end.strip() else None,
            subject=subject.strip() or None,
            teacher=teacher.strip() or None,
            room=room.strip() or None,
            reason=reason.strip() or None,
        )
    return RedirectResponse("/admin/schedule", status_code=302)


@router.post("/schedule/exception/{exc_id}/delete")
async def delete_exception(request: Request, exc_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = ScheduleRepository(session)
        exc = await repo.get_exception_by_id(exc_id)
        if exc:
            await repo.delete_exception(exc)
    return RedirectResponse("/admin/schedule", status_code=302)


# ---------------------------------------------------------------------------
# Web portal users
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    if not _authed(request):
        return _redirect_login("/admin/users")
    async with AsyncSessionLocal() as session:
        web_users = await UserRepository(session).get_all_web()
    return templates.TemplateResponse(request, "users.html", {
        "users": web_users,
    })


@router.post("/users/{user_id}/block")
async def block_user(request: Request, user_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.set_web_active(user, False)
            logger.info("[admin.users] blocked id=%d email=%s", user_id, user.email)
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/unblock")
async def unblock_user(request: Request, user_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.set_web_active(user, True)
            logger.info("[admin.users] unblocked id=%d email=%s", user_id, user.email)
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/delete")
async def delete_user(request: Request, user_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if user:
            await repo.delete(user)
            logger.info("[admin.users] deleted id=%d", user_id)
    return RedirectResponse("/admin/users", status_code=302)


# ---------------------------------------------------------------------------
# References — subjects & teachers
# ---------------------------------------------------------------------------

@router.get("/references", response_class=HTMLResponse)
async def references_page(request: Request):
    if not _authed(request):
        return _redirect_login("/admin/references")
    async with AsyncSessionLocal() as session:
        subjects = await SubjectRepository(session).get_all()
        teachers = await TeacherRepository(session).get_all()
    return templates.TemplateResponse(request, "references.html", {
        "subjects": subjects,
        "teachers": teachers,
    })


@router.post("/references/subject/add")
async def add_subject(
    request: Request,
    name: Annotated[str, Form()],
    short_name: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        await SubjectRepository(session).create(
            name=name.strip(),
            short_name=short_name.strip() or None,
        )
    logger.info("[admin.references] added subject %r", name)
    return RedirectResponse("/admin/references", status_code=302)


@router.post("/references/subject/{subject_id}/edit")
async def edit_subject(
    request: Request,
    subject_id: int,
    name: Annotated[str, Form()],
    short_name: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = SubjectRepository(session)
        obj = await repo.get_by_id(subject_id)
        if obj:
            await repo.update(obj, name=name.strip(), short_name=short_name.strip() or None)
    logger.info("[admin.references] updated subject id=%d", subject_id)
    return RedirectResponse("/admin/references", status_code=302)


@router.post("/references/subject/{subject_id}/delete")
async def delete_subject(request: Request, subject_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = SubjectRepository(session)
        obj = await repo.get_by_id(subject_id)
        if obj:
            await repo.delete(obj)
    logger.info("[admin.references] deleted subject id=%d", subject_id)
    return RedirectResponse("/admin/references", status_code=302)


@router.post("/references/teacher/add")
async def add_teacher(
    request: Request,
    full_name: Annotated[str, Form()],
    short_name: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        await TeacherRepository(session).create(
            full_name=full_name.strip(),
            short_name=short_name.strip() or None,
        )
    logger.info("[admin.references] added teacher %r", full_name)
    return RedirectResponse("/admin/references", status_code=302)


@router.post("/references/teacher/{teacher_id}/edit")
async def edit_teacher(
    request: Request,
    teacher_id: int,
    full_name: Annotated[str, Form()],
    short_name: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = TeacherRepository(session)
        obj = await repo.get_by_id(teacher_id)
        if obj:
            await repo.update(obj, full_name=full_name.strip(), short_name=short_name.strip() or None)
    logger.info("[admin.references] updated teacher id=%d", teacher_id)
    return RedirectResponse("/admin/references", status_code=302)


@router.post("/references/teacher/{teacher_id}/delete")
async def delete_teacher(request: Request, teacher_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = TeacherRepository(session)
        obj = await repo.get_by_id(teacher_id)
        if obj:
            await repo.delete(obj)
    logger.info("[admin.references] deleted teacher id=%d", teacher_id)
    return RedirectResponse("/admin/references", status_code=302)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

@router.get("/materials", response_class=HTMLResponse)
async def materials_page(request: Request):
    if not _authed(request):
        return _redirect_login("/admin/materials")
    async with AsyncSessionLocal() as session:
        categories = await MaterialCategoryRepository(session).get_all_with_materials()
    return templates.TemplateResponse(request, "materials.html", {"categories": categories})


@router.post("/materials/category/add")
async def add_category(
    request: Request,
    name: Annotated[str, Form()],
    emoji: Annotated[str, Form()] = "📁",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        await MaterialCategoryRepository(session).create(name=name.strip(), emoji=emoji.strip() or "📁")
    logger.info("[admin.materials] added category %r", name)
    return RedirectResponse("/admin/materials", status_code=302)


@router.post("/materials/category/{cat_id}/edit")
async def edit_category(
    request: Request,
    cat_id: int,
    name: Annotated[str, Form()],
    emoji: Annotated[str, Form()] = "📁",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = MaterialCategoryRepository(session)
        cat = await repo.get_by_id(cat_id)
        if cat:
            await repo.update(cat, name=name.strip(), emoji=emoji.strip() or "📁")
    logger.info("[admin.materials] updated category id=%d", cat_id)
    return RedirectResponse("/admin/materials", status_code=302)


@router.post("/materials/category/{cat_id}/delete")
async def delete_category(request: Request, cat_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = MaterialCategoryRepository(session)
        cat = await repo.get_by_id(cat_id)
        if cat:
            await repo.delete(cat)
    return RedirectResponse("/admin/materials", status_code=302)


@router.post("/materials/material/add")
async def add_material(
    request: Request,
    category_id: Annotated[int, Form()],
    title: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        await MaterialRepository(session).create(
            category_id=category_id,
            title=title.strip(),
            material_type="link",
            url=url.strip() or None,
            description=description.strip() or None,
        )
    logger.info("[admin.materials] added material %r", title)
    return RedirectResponse("/admin/materials", status_code=302)


@router.post("/materials/material/{mat_id}/edit")
async def edit_material(
    request: Request,
    mat_id: int,
    title: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    is_visible: Annotated[str, Form()] = "1",
    sort_order: Annotated[str, Form()] = "0",
):
    if not _authed(request):
        return _redirect_login()
    try:
        sort_int = int(sort_order)
    except ValueError:
        sort_int = 0
    async with AsyncSessionLocal() as session:
        repo = MaterialRepository(session)
        mat = await repo.get_by_id(mat_id)
        if mat:
            await repo.update(
                mat,
                title=title.strip(),
                url=url.strip() or None,
                description=description.strip() or None,
                is_visible=is_visible == "1",
                sort_order=sort_int,
            )
    logger.info("[admin.materials] updated material id=%d", mat_id)
    return RedirectResponse("/admin/materials", status_code=302)


@router.post("/materials/material/{mat_id}/delete")
async def delete_material(request: Request, mat_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = MaterialRepository(session)
        mat = await repo.get_by_id(mat_id)
        if mat:
            await repo.delete(mat)
    return RedirectResponse("/admin/materials", status_code=302)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    if not _authed(request):
        return _redirect_login("/admin/events")
    async with AsyncSessionLocal() as session:
        events = await EventRepository(session).get_all()
    return templates.TemplateResponse(request, "events.html", {
        "events": events,
        "today": date.today().isoformat(),
    })


@router.post("/events/add")
async def add_event(
    request: Request,
    title: Annotated[str, Form()],
    event_date: Annotated[str, Form()],
    event_time: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    notify_days: Annotated[str, Form()] = "3,1",
):
    if not _authed(request):
        return _redirect_login()

    try:
        days_list = [int(d.strip()) for d in notify_days.split(",") if d.strip().isdigit()]
    except Exception:
        days_list = [3, 1]

    parsed_event_date = _parse_date(event_date)
    if not parsed_event_date:
        return RedirectResponse("/admin/events?error=bad_date", status_code=302)
    async with AsyncSessionLocal() as session:
        await EventRepository(session).create(
            title=title.strip(),
            event_date=parsed_event_date,
            event_time=_parse_time(event_time) if event_time.strip() else None,
            description=description.strip() or None,
            notify_days_before=days_list,
        )
    logger.info("[admin.events] added event %r on %s", title, event_date)
    return RedirectResponse("/admin/events", status_code=302)


@router.post("/events/{event_id}/delete")
async def delete_event(request: Request, event_id: int):
    if not _authed(request):
        return _redirect_login()
    async with AsyncSessionLocal() as session:
        repo = EventRepository(session)
        event = await repo.get_by_id(event_id)
        if event:
            await repo.soft_delete(event)
    return RedirectResponse("/admin/events", status_code=302)
