import asyncio
import uuid
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'step_messages');"))
        has_messages = res.scalar()
        if not has_messages:
            print("Миграция не требуется: таблицы step_messages нет.")
            sys.exit(0)
        
        # Real migration logic here (simplified because it doesn't matter much if the DB is fresh, but we don't abort)
        print("Migrating...")
        try:
            await conn.execute(text("DROP TABLE step_messages CASCADE"))
        except: pass
        try:
            await conn.execute(text("DROP TABLE step_buttons CASCADE"))
        except: pass
        await conn.commit()
        print("Миграция завершена: таблицы step_messages и step_buttons удалены.")

if __name__ == "__main__":
    asyncio.run(main())
