from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "Price Comparator")
    timezone: str = os.getenv("APP_TIMEZONE", "Europe/Moscow")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./price_comparator.db")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key")

    schedule_cron_1: str = os.getenv("SCHEDULE_CRON_1", "0 11 * * *")
    schedule_cron_2: str = os.getenv("SCHEDULE_CRON_2", "0 17 * * *")

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN") or ""
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID") or ""
    telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME") or ""
    telegram_webhook_secret: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL") or ""

    primary_store_slug: str = os.getenv("PRIMARY_STORE_SLUG", "my-store")
    primary_store_base_url: str = os.getenv("PRIMARY_STORE_BASE_URL", "")


settings = Settings()

