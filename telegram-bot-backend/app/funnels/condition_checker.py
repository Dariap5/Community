from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserTag
from app.schemas.step_config import TriggerCondition


async def get_user_tags(db: AsyncSession, user_id: int) -> set[str]:
    result = await db.execute(select(UserTag.tag).where(UserTag.user_id == user_id))
    return {row[0] for row in result.all()}


def should_execute_step(trigger: TriggerCondition, user_tags: set[str]) -> bool:
    if trigger.type == "always":
        return True
    if trigger.type == "has_tags":
        return all(tag in user_tags for tag in trigger.tags)
    if trigger.type == "not_has_tags":
        return not any(tag in user_tags for tag in trigger.tags)
    return True
