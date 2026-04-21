from __future__ import annotations

from app.db.models import User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionUrl


async def handle_url(db, user: User, action: ButtonActionUrl) -> ActionResult:
    return ActionResult()
