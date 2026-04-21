from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.db.models import FunnelStatus, FunnelStep, User, UserFunnelState
from app.db.session import SessionLocal
from app.funnels.condition_checker import get_user_tags
from app.funnels.engine import FunnelEngine
from app.funnels.keyboard_builder import check_visibility
from app.schemas.step_config import ButtonGroup, StepConfig

router = Router(name="callbacks")


def _parse_callback_data(callback_data: str | None) -> tuple[str, str] | None:
    if not callback_data:
        return None
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "btn":
        return None
    return parts[1], parts[2]


async def _resolve_current_step(session, user_id: int, step_prefix: str) -> FunnelStep | None:
    states_result = await session.execute(
        select(UserFunnelState).where(UserFunnelState.user_id == user_id, UserFunnelState.status == FunnelStatus.active)
    )
    for state in states_result.scalars().all():
        if state.current_step_id is None:
            continue
        step = await session.get(FunnelStep, state.current_step_id)
        if step is not None and step.id.hex.startswith(step_prefix):
            return step
    return None


@router.callback_query(F.data.startswith("btn:"))
async def button_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    parsed = _parse_callback_data(callback.data)
    if parsed is None:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    step_prefix, button_prefix = parsed
    async with SessionLocal() as session:
        engine = FunnelEngine(bot=callback.message.bot if callback.message else None, db=session)
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await callback.answer("Сначала используйте /start", show_alert=True)
            return

        step = await _resolve_current_step(session, user.telegram_id, step_prefix)
        if step is None:
            await callback.answer("Кнопка устарела", show_alert=True)
            return

        config = StepConfig.model_validate(step.config or {})
        button_group = next((block for block in config.blocks if isinstance(block, ButtonGroup)), None)
        if button_group is None:
            await callback.answer("Кнопка недоступна", show_alert=True)
            return

        button = next((item for item in button_group.buttons if item.id.hex.startswith(button_prefix)), None)
        if button is None:
            await callback.answer("Кнопка устарела", show_alert=True)
            return

        user_tags = await get_user_tags(session, user.telegram_id)
        if not check_visibility(button.visible_if, user_tags):
            await callback.answer("Кнопка недоступна", show_alert=True)
            return

        await callback.answer()
        await engine.handle_button_click(user, step, button.id, callback.data)
