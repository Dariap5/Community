import socket
# Форсируем IPv4 для aiohttp (внутри Docker IPv6 не маршрутизируется)
_orig_getaddrinfo = socket.getaddrinfo
def _force_ipv4(*args, **kwargs):
    responses = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = _force_ipv4

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.bot.router import build_router
from app.config import get_settings


async def run_bot() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(build_router())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
