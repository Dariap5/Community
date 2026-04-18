from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserService:
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        source_deeplink: str | None,
    ) -> User:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is not None:
            if source_deeplink and not user.source_deeplink:
                user.source_deeplink = source_deeplink
            user.username = username
            user.first_name = first_name
            await session.commit()
            await session.refresh(user)
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            registered_at=datetime.now(timezone.utc),
            source_deeplink=source_deeplink,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
