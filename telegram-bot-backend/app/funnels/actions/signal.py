from __future__ import annotations

from app.db.models import User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionSignal
from app.services.tag_service import TagService


async def handle_signal(db, user: User, action: ButtonActionSignal) -> ActionResult:
    await TagService.add_tag(db, user.telegram_id, f"signal:{action.value}")
    return ActionResult()
