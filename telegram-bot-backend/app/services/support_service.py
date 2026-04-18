from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SupportMessageLink


class SupportService:
    @staticmethod
    async def bind_support_message(
        session: AsyncSession,
        support_chat_id: int,
        support_message_id: int,
        user_id: int,
    ) -> None:
        session.add(
            SupportMessageLink(
                support_chat_id=support_chat_id,
                support_message_id=support_message_id,
                user_id=user_id,
            )
        )
        await session.commit()

    @staticmethod
    async def resolve_user_id(
        session: AsyncSession,
        support_chat_id: int,
        support_message_id: int,
    ) -> int | None:
        result = await session.execute(
            select(SupportMessageLink.user_id).where(
                SupportMessageLink.support_chat_id == support_chat_id,
                SupportMessageLink.support_message_id == support_message_id,
            )
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None
