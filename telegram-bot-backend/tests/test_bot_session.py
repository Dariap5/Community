from __future__ import annotations

import socket

from app.bot.main import IPv4OnlySession


async def test_ipv4_only_session_creates_client_session_with_ipv4() -> None:
    session = IPv4OnlySession(limit=100)
    client_session = await session.create_session()
    try:
        assert session._connector_init["family"] == socket.AF_INET
        assert "User-Agent" in client_session.headers
    finally:
        await session.close()