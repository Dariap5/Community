import asyncio
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.router import build_router
from app.config import get_settings


class IPv4OnlySession(AiohttpSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET
        self._connector_init["ttl_dns_cache"] = 300


async def run_bot() -> None:
    settings = get_settings()
    session = IPv4OnlySession(limit=100)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    dp = Dispatcher()
    dp.include_router(build_router())
    try:
        await dp.start_polling(bot)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(run_bot())