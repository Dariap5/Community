import asyncio

from app.db.base import Base
from app.db.session import engine

# Import models to ensure metadata contains all tables.
from app.db import models  # noqa: F401


async def create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_schema())
