from __future__ import annotations

from app.db.models import User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionGotoStep


async def handle_goto_step(db, user: User, action: ButtonActionGotoStep) -> ActionResult:
    return ActionResult(advance=True, next_step_key=action.value)
