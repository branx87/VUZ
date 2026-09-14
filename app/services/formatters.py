"""
Text formatters for schedule display.
HTML format for Telegram (aiogram sends HTML by default).
Plain text for VK (VK doesn't support HTML in messages).
"""
from datetime import date, timedelta

from app.services.schedule import DAY_NAMES, DAY_NAMES_SHORT, EffectiveLesson


def _lesson_lines_html(lesson: EffectiveLesson) -> list[str]:
    t = f"{lesson.time_start.strftime('%H:%M')}–{lesson.time_end.strftime('%H:%M')}"
    marker = "🔄 " if lesson.exception_type == "replace" else "➕ " if lesson.exception_type == "add" else ""
    sub = f" <i>[{lesson.subgroup} п/г]</i>" if lesson.subgroup else ""
    lines = [f"{marker}<b>{lesson.pair_number}.</b> {t}  <b>{lesson.subject}</b>{sub}"]
    if lesson.teacher:
        lines.append(f"   👤 {lesson.teacher}")
    if lesson.room:
        lines.append(f"   🚪 ауд. {lesson.room}")
    if lesson.reason:
        lines.append(f"   ℹ️ <i>{lesson.reason}</i>")
    return lines


def _lesson_lines_plain(lesson: EffectiveLesson) -> list[str]:
    t = f"{lesson.time_start.strftime('%H:%M')}–{lesson.time_end.strftime('%H:%M')}"
    marker = "🔄 " if lesson.exception_type == "replace" else "➕ " if lesson.exception_type == "add" else ""
    sub = f" [{lesson.subgroup} п/г]" if lesson.subgroup else ""
    lines = [f"{marker}{lesson.pair_number}. {t}  {lesson.subject}{sub}"]
    if lesson.teacher:
        lines.append(f"   👤 {lesson.teacher}")
    if lesson.room:
        lines.append(f"   🚪 ауд. {lesson.room}")
    if lesson.reason:
        lines.append(f"   ℹ️ {lesson.reason}")
    return lines


def format_day_html(lessons: list[EffectiveLesson], target_date: date) -> str:
    header = f"📅 <b>{DAY_NAMES[target_date.weekday()]}, {target_date.strftime('%d.%m.%Y')}</b>"
    if not lessons:
        return f"{header}\n\nПар нет 🎉"
    lines = [header, ""]
    for lesson in lessons:
        lines.extend(_lesson_lines_html(lesson))
        lines.append("")
    return "\n".join(lines).rstrip()


def format_day_plain(lessons: list[EffectiveLesson], target_date: date) -> str:
    header = f"📅 {DAY_NAMES[target_date.weekday()]}, {target_date.strftime('%d.%m.%Y')}"
    if not lessons:
        return f"{header}\n\nПар нет 🎉"
    lines = [header, ""]
    for lesson in lessons:
        lines.extend(_lesson_lines_plain(lesson))
        lines.append("")
    return "\n".join(lines).rstrip()


def format_week_html(week_data: dict[int, list[EffectiveLesson]], week_start: date) -> str:
    end = week_start + timedelta(days=5)
    lines = [
        f"📆 <b>Расписание на неделю</b>  {week_start.strftime('%d.%m')}–{end.strftime('%d.%m')}\n"
    ]
    for dow, lessons in week_data.items():
        d = week_start + timedelta(days=dow)
        lines.append(f"<b>{DAY_NAMES_SHORT[dow]}, {d.strftime('%d.%m')}:</b>")
        if not lessons:
            lines.append("  Пар нет")
        else:
            for lesson in lessons:
                lines.extend("  " + l for l in _lesson_lines_html(lesson))
        lines.append("")
    return "\n".join(lines).rstrip()


def format_week_plain(week_data: dict[int, list[EffectiveLesson]], week_start: date) -> str:
    end = week_start + timedelta(days=5)
    lines = [
        f"📆 Расписание на неделю  {week_start.strftime('%d.%m')}–{end.strftime('%d.%m')}\n"
    ]
    for dow, lessons in week_data.items():
        d = week_start + timedelta(days=dow)
        lines.append(f"{DAY_NAMES_SHORT[dow]}, {d.strftime('%d.%m')}:")
        if not lessons:
            lines.append("  Пар нет")
        else:
            for lesson in lessons:
                lines.extend("  " + l for l in _lesson_lines_plain(lesson))
        lines.append("")
    return "\n".join(lines).rstrip()
