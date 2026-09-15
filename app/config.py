from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = "postgresql+asyncpg://vuzbot:secret@localhost:5432/vuzbot"

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_broadcast_chat_id: int = 0
    admin_tg_id: int = 0

    # VK
    vk_community_token: str = ""
    vk_group_id: int = 0
    vk_confirmation_string: str = ""
    vk_secret_key: str = ""

    # App
    app_base_url: str = "http://localhost:8000"
    admin_secret_token: str = "changeme"
    # Cookie Secure flag: True для HTTPS, False для локального HTTP-дев.
    cookie_secure: bool = False
    # Секрет для подписи cookie-сессий web-портала (отдельный от ADMIN_SECRET_TOKEN).
    session_secret: str = "change-me-too-32-chars-min-portal"

    # Files
    files_dir: str = "storage/files"

    # Scheduler
    scheduler_timezone: str = "Europe/Moscow"

    # Proxy (опционально, для Telegram при заблокированном прямом доступе)
    proxy_url: str = ""


settings = Settings()
