import socket
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import TCPConnector, ClientSession

from app.bot.router import build_router
from app.config import get_settings


class IPv4OnlySession(AiohttpSession):
    """Aiogram сессия, которая использует только IPv4."""
    async def create_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            connector = TCPConnector(
                family=socket.AF_INET,  # Только IPv4
                limit=100,
                ttl_dns_cache=300,
            )
            self._session = ClientSession(
                connector=connector,
                headers=self._headers,
                json_serialize=self.json_loads,
            )
        return self._session


async def run_bot() -> None:
    settings = get_settings()
    session = IPv4OnlySession()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    dp = Dispatcher()
    dp.include_router(build_router())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
