from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models import Track, User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionOpenTrack

logger = logging.getLogger(__name__)


async def handle_open_track(db, user: User, action: ButtonActionOpenTrack) -> ActionResult:
    try:
        track_id = UUID(action.value)
    except ValueError:
        logger.warning("Invalid track id in open_track action: %s", action.value)
        return ActionResult()

    result = await db.execute(select(Track).where(Track.id == track_id))
    track = result.scalar_one_or_none()
    if track is None:
        logger.warning("Track not found for open_track action: %s", action.value)
        return ActionResult()

    user.selected_track_id = track.id
    await db.commit()
    return ActionResult()
