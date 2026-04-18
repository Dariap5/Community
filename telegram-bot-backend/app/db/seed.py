import asyncio

from app.db.bootstrap_scenarios import seed_default_scenarios
from app.db.session import SessionLocal


async def _run() -> None:
    async with SessionLocal() as session:
        await seed_default_scenarios(session)


if __name__ == "__main__":
    asyncio.run(_run())
