from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    postgres_dsn: str
    redis_dsn: str
    bot_token: str = Field(validation_alias=AliasChoices("SALES_BOT_TOKEN", "BOT_TOKEN"))
    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_session_secret: str = "change_me"
    settings_crypto_key: str = ""
    support_chat_id: int = 0
    payment_webhook_secret: str = ""
    scheduler_poll_seconds: int = 30
    short_delay_max_seconds: int = 300
    send_retry_seconds: int = 30

    payment_provider: Literal["robokassa", "yookassa"] = "robokassa"
    robokassa_login: Optional[str] = None
    robokassa_password1: Optional[str] = None
    robokassa_password2: Optional[str] = None
    yoo_kassa_shop_id: Optional[str] = None
    yoo_kassa_secret_key: Optional[str] = None

    @property
    def database_url(self) -> str:
        return self.postgres_dsn

    @property
    def redis_url(self) -> str:
        return self.redis_dsn


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
