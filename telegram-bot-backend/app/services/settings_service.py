import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotSetting


class SettingsService:
    @staticmethod
    async def get_text(session: AsyncSession, key: str, default: str = "") -> str:
        result = await session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None or setting.value_text is None:
            return default
        return setting.value_text

    @staticmethod
    async def get_json(session: AsyncSession, key: str, default: dict | list | None = None):
        result = await session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None or setting.value_text is None:
            return {} if default is None else default
        try:
            return json.loads(setting.value_text)
        except json.JSONDecodeError:
            return {} if default is None else default

    @staticmethod
    async def get_int(session: AsyncSession, key: str, default: int) -> int:
        raw = await SettingsService.get_text(session, key, str(default))
        try:
            return int(raw)
        except ValueError:
            return default
