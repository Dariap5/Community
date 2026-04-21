from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserTag


class TagService:
    @staticmethod
    async def add_tag(session: AsyncSession, user_id: int, tag: str) -> None:
        result = await session.execute(
            select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag)
        )
        if result.scalar_one_or_none() is None:
            session.add(UserTag(user_id=user_id, tag=tag))
            await session.commit()

    @staticmethod
    async def has_tag(session: AsyncSession, user_id: int, tag: str) -> bool:
        result = await session.execute(
            select(UserTag.tag).where(UserTag.user_id == user_id, UserTag.tag == tag)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def user_tags(session: AsyncSession, user_id: int) -> set[str]:
        result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user_id))
        return {row[0] for row in result.all()}
