from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(validation_alias=AliasChoices("SALES_BOT_TOKEN", "BOT_TOKEN"))
    bot_admin_ids: list[int] = Field(default_factory=list, alias="BOT_ADMIN_IDS")
    bot_public_url: str = Field(default="", alias="BOT_PUBLIC_URL")
    support_chat_id: int = Field(default=0, alias="SUPPORT_CHAT_ID")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password_hash: str = Field(default="", alias="ADMIN_PASSWORD_HASH")
    admin_session_secret: str = Field(default="change_me", alias="ADMIN_SESSION_SECRET")
    settings_crypto_key: str = Field(default="", alias="SETTINGS_CRYPTO_KEY")

    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    redis_dsn: str = Field(alias="REDIS_DSN")

    payment_provider: str = Field(default="yookassa", alias="PAYMENT_PROVIDER")
    payment_webhook_secret: str = Field(alias="PAYMENT_WEBHOOK_SECRET")

    yookassa_shop_id: str = Field(default="", alias="YOO_KASSA_SHOP_ID")
    yookassa_secret_key: str = Field(default="", alias="YOO_KASSA_SECRET_KEY")
    robo_login: str = Field(default="", alias="ROBO_LOGIN")
    robo_password_1: str = Field(default="", alias="ROBO_PASSWORD_1")
    robo_password_2: str = Field(default="", alias="ROBO_PASSWORD_2")

    scheduler_poll_seconds: int = Field(default=30, alias="SCHEDULER_POLL_SECONDS")
    short_delay_max_seconds: int = Field(default=300, alias="SHORT_DELAY_MAX_SECONDS")
    send_retry_seconds: int = Field(default=30, alias="SEND_RETRY_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
