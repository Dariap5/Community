from __future__ import annotations

from app.db.models import User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionAddTag
from app.services.tag_service import TagService


async def handle_add_tag(db, user: User, action: ButtonActionAddTag) -> ActionResult:
    await TagService.add_tag(db, user.telegram_id, action.value)
    return ActionResult()
