from __future__ import annotations

from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Funnel, FunnelCrossEntryBehavior, FunnelStatus, UserFunnelState


class CrossEntryResult(Enum):
    ALLOW = "allow"
    DENY = "deny"


async def resolve_cross_entry(db: AsyncSession, user_id: int, new_funnel: Funnel) -> CrossEntryResult:
    active_result = await db.execute(
        select(UserFunnelState.id).where(
            UserFunnelState.user_id == user_id,
            UserFunnelState.status == FunnelStatus.active,
        )
    )
    has_active = active_result.scalar_one_or_none() is not None
    if not has_active:
        return CrossEntryResult.ALLOW

    behavior = getattr(new_funnel.cross_entry_behavior, "value", new_funnel.cross_entry_behavior)
    if behavior == FunnelCrossEntryBehavior.allow.value:
        return CrossEntryResult.ALLOW
    return CrossEntryResult.DENY
