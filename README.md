# VUZ Bot

Telegram + VK бот для студенческой группы 231/232: расписание по неделям сессии,
материалы (ссылки и файлы), события с авто-напоминаниями, веб-админка и Telegram Mini App.

## Стек

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic
- **Боты**: aiogram 3 (Telegram), httpx (VK)
- **UI**: Jinja2 + Tailwind (CDN), Telegram WebApp SDK
- **Планировщик**: APScheduler (напоминания о событиях)
- **БД**: PostgreSQL 16

## Структура

```
app/
  config.py           # Pydantic Settings (.env)
  database.py         # AsyncSession, engine
  main.py             # FastAPI app + lifespan (запускает scheduler)
  domain/models.py    # SQLAlchemy ORM
  repositories/       # CRUD по сущностям
  services/
    schedule.py       # Бизнес-логика: применение exceptions к базовому расписанию
    formatters.py     # HTML/plain форматирование расписания для TG/VK
    broadcast.py      # Рассылка по обеим платформам с учётом лимитов
  scheduler/          # APScheduler — ежедневные напоминания о событиях
  integrations/
    telegram/         # aiogram-роутер + handlers (start, schedule, materials, events, admin)
    vk/               # VK Callback API + Long Poll + handlers
  admin/              # Веб-админка (Jinja2, токен-аутентификация)
  miniapp/            # Telegram Mini App (WebApp)
alembic/              # Миграции
run_bot_polling.py    # TG в режиме polling (для локальной отладки без публичного URL)
run_vk_polling.py     # VK в режиме Long Poll (для локальной отладки)
```

## Как запустить

### Через Docker (рекомендуется)

1. Скопировать `.env.example` → `.env`, заполнить переменные (см. ниже).
2. `docker compose up -d --build`.
3. `docker compose exec app alembic upgrade head`.
4. Открыть `http://localhost:8000/admin/login`, ввести `ADMIN_SECRET_TOKEN`.
5. В Telegram написать боту `/start`.

### Локально без Docker

1. Поднять PostgreSQL (например через Docker: `docker run -d -p 5432:5432 -e POSTGRES_USER=vuzbot -e POSTGRES_PASSWORD=secret -e POSTGRES_DB=vuzbot postgres:16-alpine`).
2. `.\.venv\Scripts\python.exe -m alembic upgrade head`.
3. Webhook-режим: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.
4. Polling-режим (без публичного URL): `.\.venv\Scripts\python.exe run_bot_polling.py`.

## Переменные окружения

| Переменная                  | Описание                                                |
| --------------------------- | ------------------------------------------------------- |
| `DATABASE_URL`              | `postgresql+asyncpg://user:pass@host:5432/dbname`       |
| `TELEGRAM_BOT_TOKEN`        | Токен от @BotFather                                     |
| `TELEGRAM_WEBHOOK_SECRET`   | Секрет заголовка `X-Telegram-Bot-Api-Secret-Token`      |
| `TELEGRAM_BROADCAST_CHAT_ID`| ID чата для рассылок (опц.)                             |
| `ADMIN_TG_ID`               | Telegram ID администратора (для `IsAdmin`-фильтра)      |
| `VK_COMMUNITY_TOKEN`        | Токен сообщества VK                                     |
| `VK_GROUP_ID`               | ID сообщества VK (без минуса)                           |
| `VK_CONFIRMATION_STRING`    | Строка подтверждения из настроек Callback API           |
| `VK_SECRET_KEY`             | Секрет для верификации webhook от VK                    |
| `APP_BASE_URL`              | Публичный URL приложения (для регистрации webhook)      |
| `ADMIN_SECRET_TOKEN`        | Токен входа в веб-админку (≥32 символа)                 |
| `COOKIE_SECURE`             | `true` для HTTPS, `false` для локального HTTP           |
| `FILES_DIR`                 | Каталог для загруженных файлов (по умолчанию `storage/files`) |
| `SCHEDULER_TIMEZONE`        | TZ для напоминаний (по умолчанию `Europe/Moscow`)       |
| `PROXY_URL`                 | SOCKS5-прокси для Telegram (если прямой доступ закрыт)  |

## Миграции БД

```
alembic revision --autogenerate -m "описание"
alembic upgrade head
alembic downgrade -1
```

## Безопасность

- Токены в `.env` (`.gitignore` исключает файл из Git).
- Сравнение токенов — `hmac.compare_digest` (защита от timing-атак).
- Секреты webhook'ов проверяются через `hmac.compare_digest`.
- Cookie логина — `httponly`, `secure` (на HTTPS).
- Path-traversal в скачивании файлов Mini App блокируется.

## Планировщик напоминаний

- Ежедневно в 09:00 локального времени.
- Для каждого активного `Event`, до которого осталось N дней (`N ∈ event.notify_days_before`),
  шлёт напоминание всем подписчикам, у которых `notifications_enabled=True` и
  `notification_types.event_reminder=True`.
- Дедупликация через `NotificationLog` — повторно не шлёт.
- Логирование в `notification_logs` (`sent` / `failed` + текст ошибки).

## Известные ограничения

- `passlib`/`python-jose` были в `requirements.txt`, но не использовались — удалены.
- Закомментированный `tg_bot` сервис в `docker-compose.yml` удалён; для polling-режима
  локально используйте `run_bot_polling.py`.
