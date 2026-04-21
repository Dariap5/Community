from __future__ import annotations

import logging
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.schemas.step_config import Button, ButtonGroup, StepConfig, VisibilityCondition

logger = logging.getLogger(__name__)


def check_visibility(condition: VisibilityCondition, user_tags: set[str]) -> bool:
    if condition.has_tags and not all(tag in user_tags for tag in condition.has_tags):
        return False
    if condition.not_has_tags and any(tag in user_tags for tag in condition.not_has_tags):
        return False
    return True


def build_callback_data(button: Button, step_id: UUID) -> str:
    return f"btn:{step_id.hex[:8]}:{button.id.hex[:8]}"


def build_keyboard_for_step(
    config: StepConfig,
    step_id: UUID,
    user_tags: set[str] | None = None,
    ignore_visibility: bool = False,
) -> InlineKeyboardMarkup | None:
    button_group = None
    for block in config.blocks:
        if isinstance(block, ButtonGroup):
            button_group = block
            break

    if button_group is None or not button_group.buttons:
        return None

    user_tags = user_tags or set()
    rows: list[list[InlineKeyboardButton]] = []
    for button in button_group.buttons:
        if not ignore_visibility and not check_visibility(button.visible_if, user_tags):
            continue

        if button.action.type == "url":
            rows.append([InlineKeyboardButton(text=button.text, url=button.action.value)])
        else:
            rows.append([InlineKeyboardButton(text=button.text, callback_data=build_callback_data(button, step_id))])

    if not rows:
        return None

    if len([block for block in config.blocks if isinstance(block, ButtonGroup)]) > 1:
        logger.warning("Multiple button groups found for step %s; using the first one", step_id)

    return InlineKeyboardMarkup(inline_keyboard=rows)
