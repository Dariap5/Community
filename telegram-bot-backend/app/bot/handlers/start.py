from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.db.models import Funnel, FunnelStatus, User, UserFunnelState
from app.db.session import SessionLocal
from app.funnels.engine import FunnelEngine

router = Router(name="start")


async def _resolve_target_funnel(session, deeplink: str | None) -> Funnel | None:
    if deeplink:
        result = await session.execute(
            select(Funnel).where(Funnel.entry_key == deeplink, Funnel.is_archived.is_(False))
        )
        funnel = result.scalar_one_or_none()
        if funnel is not None:
            return funnel

    result = await session.execute(
        select(Funnel)
        .where(Funnel.entry_key == "guide", Funnel.is_archived.is_(False), Funnel.is_active.is_(True))
    )
    funnel = result.scalar_one_or_none()
    if funnel is not None:
        return funnel

    result = await session.execute(
        select(Funnel).where(Funnel.is_archived.is_(False), Funnel.is_active.is_(True)).order_by(Funnel.created_at.asc())
    )
    return result.scalar_one_or_none()


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return

    deeplink = command.args if command and command.args else None
    async with SessionLocal() as session:
        engine = FunnelEngine(bot=message.bot, db=session)
        user = await engine.upsert_user(
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            source_deeplink=deeplink,
        )

        target_funnel = await _resolve_target_funnel(session, deeplink)
        if target_funnel is None:
            await message.answer("Сценарий временно недоступен.")
            return

        state = await engine.start_funnel(user, target_funnel)
        if state is None:
            active_states = await session.execute(
                select(UserFunnelState).where(
                    UserFunnelState.user_id == user.telegram_id,
                    UserFunnelState.status == FunnelStatus.active,
                )
            )
            if list(active_states.scalars().all()):
                await message.answer("Вы уже в нашей программе 🙌")
            else:
                await message.answer("Сценарий временно недоступен.")
