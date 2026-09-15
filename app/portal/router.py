"""
Web-портал для тех, у кого нет Telegram/VK.

Поток:
  1. Регистрация: имя + фамилия + email + пароль → создаётся User(is_web_active=False).
  2. Админ в /admin/users одобряет → is_web_active=True.
  3. Юзер логинится в /portal/login и получает доступ к /portal/.
  4. В /portal/ — расписание, материалы, последние уведомления.

Сессии: Starlette SessionMiddleware (cookie `portal_session`).
"""
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import bcrypt
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.models import NotificationLog, User
from app.repositories.events import EventRepository
from app.repositories.materials import MaterialCategoryRepository, MaterialRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.users import UserRepository
from app.services.schedule import DAY_NAMES
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()

_TEMPLATES = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES))
_FILES_DIR = Path(settings.files_dir).resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except (ValueError, AttributeError):
        return False


def _current_user(request: Request) -> dict | None:
    """Извлекает данные web-юзера из сессии (или None)."""
    return request.session.get("portal_user")


def _login_required(request: Request) -> RedirectResponse | None:
    if _current_user(request) is None:
        return RedirectResponse("/portal/login", status_code=302)
    return None


# ---------------------------------------------------------------------------
# Регистрация / вход / выход
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def portal_home(request: Request):
    """Корень портала: редирект на /login, /register или /dashboard."""
    if _current_user(request) is None:
        return RedirectResponse("/portal/login", status_code=302)
    return RedirectResponse("/portal/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    if _current_user(request) is not None:
        return RedirectResponse("/portal/dashboard", status_code=302)
    return templates.TemplateResponse(request, "register.html", {"error": error})


@router.post("/register")
async def do_register(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    if _current_user(request) is not None:
        return RedirectResponse("/portal/dashboard", status_code=302)

    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip().lower()

    if not first_name or not last_name:
        return RedirectResponse("/portal/register?error=Введите+имя+и+фамилию", status_code=302)
    if "@" not in email or "." not in email:
        return RedirectResponse("/portal/register?error=Некорректный+email", status_code=302)
    if len(password) < 6:
        return RedirectResponse("/portal/register?error=Пароль+минимум+6+символов", status_code=302)
    if password != password2:
        return RedirectResponse("/portal/register?error=Пароли+не+совпадают", status_code=302)

    from app.domain.models import User
    from sqlalchemy import update

    full_name = f"{first_name} {last_name}".strip()
    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email)

        if existing is None:
            # Совсем новый юзер.
            await repo.create_web_user(
                email=email,
                password_hash=_hash_password(password),
                first_name=first_name,
                last_name=last_name,
            )
        elif not existing.password_hash:
            # Юзер уже зарегался через бота, но без пароля — устанавливаем пароль.
            await session.execute(
                update(User)
                .where(User.id == existing.id)
                .values(password_hash=_hash_password(password), full_name=full_name)
            )
            await session.commit()
        else:
            # Email уже с паролем — конфликт.
            return RedirectResponse(
                "/portal/register?error=Этот+email+уже+зарегистрирован",
                status_code=302,
            )

    # Автоматически логиним после успешной регистрации.
    request.session["portal_user"] = {
        "id": existing.id if existing else None,
        "email": email,
        "full_name": full_name,
    }
    # Перечитать id юзера, если создавали нового
    if existing is None:
        async with AsyncSessionLocal() as session:
            new_user = await UserRepository(session).get_by_email(email)
        request.session["portal_user"] = {
            "id": new_user.id,
            "email": email,
            "full_name": full_name,
        }

    return RedirectResponse("/portal/dashboard", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if _current_user(request) is not None:
        return RedirectResponse("/portal/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login")
async def do_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_email(email)
    if not user or not user.password_hash or not _check_password(password, user.password_hash):
        return RedirectResponse("/portal/login?error=Неверный+email+или+пароль", status_code=302)
    if not user.is_web_active:
        return RedirectResponse(
            "/portal/login?error=Аккаунт+заблокирован+администратором",
            status_code=302,
        )
    request.session["portal_user"] = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
    }
    return RedirectResponse("/portal/dashboard", status_code=302)


# ---------------------------------------------------------------------------
# Восстановление пароля
# ---------------------------------------------------------------------------

@router.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request, sent: str = "", error: str = ""):
    return templates.TemplateResponse(request, "forgot.html", {
        "sent": sent,
        "error": error,
    })


@router.post("/forgot")
async def do_forgot(request: Request, email: str = Form(...)):
    from app.services.password_reset import request_reset
    result = await request_reset(email)
    # Всегда показываем одинаковое сообщение — не светим, есть ли такой email.
    if result["sent"]:
        return RedirectResponse("/portal/forgot?sent=1", status_code=302)
    else:
        return RedirectResponse("/portal/forgot?sent=1", status_code=302)


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "reset.html", {"error": error})


@router.post("/reset")
async def do_reset(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    from app.services.password_reset import confirm_reset
    if password != password2:
        return RedirectResponse("/portal/reset?error=Пароли+не+совпадают", status_code=302)
    ok, err = await confirm_reset(email, code, password)
    if ok:
        return RedirectResponse("/portal/login?reset=1", status_code=302)
    return RedirectResponse(f"/portal/reset?error={err}", status_code=302)


@router.post("/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/portal/login", status_code=302)


# ---------------------------------------------------------------------------
# Главная страница портала (требует логина)
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def portal_dashboard(request: Request):
    guard = _login_required(request)
    if guard:
        return guard

    me = _current_user(request)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    async with AsyncSessionLocal() as session:
        schedule_repo = ScheduleRepository(session)
        entries = await schedule_repo.get_entries_for_session_week(week_start)
        exceptions = await schedule_repo.get_exceptions_upcoming(today)
        events = await EventRepository(session).get_upcoming(today, limit=5)
        categories = await MaterialCategoryRepository(session).get_all_with_materials()
        user = await UserRepository(session).get_by_id(me["id"])
        recent_logs = (
            await session.execute(
                select(NotificationLog)
                .where(NotificationLog.user_id == me["id"])
                .order_by(NotificationLog.sent_at.desc())
                .limit(100)
            )
        ).scalars().all()

    by_day: dict[int, list] = {i: [] for i in range(7)}
    for e in entries:
        by_day[e.day_of_week].append(e)

    cancelled_ids = {
        ex.original_entry_id
        for ex in exceptions
        if ex.exception_type == "cancel" and ex.original_entry_id is not None
    }

    visible_materials = [
        {"category": c, "items": [m for m in c.materials if m.is_visible]}
        for c in categories
    ]

    week_days = [
        {"dow": i, "name": DAY_NAMES[i], "date": (week_start + timedelta(days=i)).strftime("%d.%m")}
        for i in range(6)
    ]

    return templates.TemplateResponse(request, "index.html", {
        "me": me,
        "today": today,
        "week_start": week_start,
        "week_days": week_days,
        "by_day": by_day,
        "day_names": DAY_NAMES,
        "cancelled_ids": cancelled_ids,
        "events": events,
        "material_groups": visible_materials,
        "recent_logs": recent_logs,
    })


# ---------------------------------------------------------------------------
# Скачивание файлов материалов (требует логина)
# ---------------------------------------------------------------------------

@router.get("/api/materials/{mat_id}/download")
async def portal_download_material(mat_id: int, request: Request):
    if _current_user(request) is None:
        raise HTTPException(status_code=401, detail="login required")
    async with AsyncSessionLocal() as session:
        mat = await MaterialRepository(session).get_by_id(mat_id)
    if not mat or mat.material_type != "file" or not mat.file_path:
        raise HTTPException(status_code=404)
    file_path = (_FILES_DIR / mat.file_path).resolve()
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
