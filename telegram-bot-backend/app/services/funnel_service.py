from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Funnel,
    FunnelStatus,
    ScheduledTask,
    ScheduledTaskStatus,
    User,
    UserFunnelState,
)


class FunnelService:
    DEEPLINK_TO_FUNNEL = {
        "guide": "guide",
        "product": "product",
    }

    @staticmethod
    def funnel_name_from_deeplink(deeplink: str | None) -> str:
        if deeplink is None:
            return "guide"
        return FunnelService.DEEPLINK_TO_FUNNEL.get(deeplink, deeplink)

    @staticmethod
    async def has_active_funnel(session: AsyncSession, user_id: int) -> bool:
        query = select(UserFunnelState).where(
            UserFunnelState.user_id == user_id,
            UserFunnelState.status == FunnelStatus.active,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def start_funnel(session: AsyncSession, user: User, funnel_name: str) -> UserFunnelState | None:
        funnel_result = await session.execute(
            select(Funnel).where(Funnel.name == funnel_name, Funnel.is_enabled.is_(True))
        )
        funnel = funnel_result.scalar_one_or_none()
        if funnel is None:
            return None

        state = UserFunnelState(user_id=user.id, funnel_id=funnel.id, status=FunnelStatus.active)
        session.add(state)
        await session.flush()

        session.add(
            ScheduledTask(
                user_id=user.id,
                task_type="funnel_step_dispatch",
                payload={"funnel_state_id": state.id, "step_order": 1},
                run_at=datetime.now(timezone.utc) + timedelta(seconds=1),
                status=ScheduledTaskStatus.pending,
            )
        )
        await session.commit()
        await session.refresh(state)
        return state

    @staticmethod
    async def schedule_funnel_start(
        session: AsyncSession,
        user_id: int,
        funnel_name: str,
        delay_seconds: int,
    ) -> None:
        session.add(
            ScheduledTask(
                user_id=user_id,
                task_type="start_funnel",
                payload={"funnel_name": funnel_name},
                run_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
                status=ScheduledTaskStatus.pending,
            )
        )
        await session.commit()
