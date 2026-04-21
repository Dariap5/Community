from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Funnel, FunnelStatus, FunnelStep, ScheduledTask, ScheduledTaskStatus, User, UserFunnelState
from app.funnels.actions import ActionResult, handle_add_tag, handle_goto_step, handle_open_track, handle_pay_product, handle_signal, handle_url
from app.funnels.condition_checker import get_user_tags, should_execute_step
from app.funnels.cross_entry import CrossEntryResult, resolve_cross_entry
from app.funnels.keyboard_builder import build_keyboard_for_step, check_visibility
from app.funnels.message_sender import send_block
from app.schemas.step_config import Button, ButtonGroup, MessageContent, StepConfig
from app.services.tag_service import TagService

logger = logging.getLogger(__name__)

THRESHOLD_INLINE_DELAY_SECONDS = 60


@dataclass(slots=True)
class ExecutionContext:
    user: User
    funnel: Funnel
    step: FunnelStep
    execution_id: UUID
    is_test: bool = False
    emulated_tags: list[str] | None = None


class FunnelEngine:
    """Executes JSON-configured funnel steps for a user."""

    def __init__(self, bot: Bot | None = None, db: AsyncSession | None = None) -> None:
        self.bot = bot
        self.db = db
        self.settings = get_settings()

    def _require_db(self) -> AsyncSession:
        if self.db is None:
            raise RuntimeError("FunnelEngine requires an AsyncSession")
        return self.db

    def _require_bot(self) -> Bot:
        if self.bot is None:
            raise RuntimeError("FunnelEngine requires a Bot")
        return self.bot

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        source_deeplink: str | None = None,
    ) -> User:
        db = self._require_db()
        now = datetime.now()
        statement = pg_insert(User).values(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            source_deeplink=source_deeplink,
            last_activity_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "username": func.coalesce(statement.excluded.username, User.username),
                "first_name": func.coalesce(statement.excluded.first_name, User.first_name),
                "last_name": func.coalesce(statement.excluded.last_name, User.last_name),
                "source_deeplink": func.coalesce(statement.excluded.source_deeplink, User.source_deeplink),
                "last_activity_at": statement.excluded.last_activity_at,
            },
        )
        await db.execute(statement)
        await db.commit()

        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one()
        await db.refresh(user)
        return user

    async def _get_active_state(self, user_id: int, funnel_id: UUID) -> UserFunnelState | None:
        db = self._require_db()
        result = await db.execute(
            select(UserFunnelState)
            .where(
                UserFunnelState.user_id == user_id,
                UserFunnelState.funnel_id == funnel_id,
                UserFunnelState.status == FunnelStatus.active,
            )
            .order_by(UserFunnelState.started_at.desc())
        )
        return result.scalar_one_or_none()

    async def _get_active_states(self, user_id: int) -> list[UserFunnelState]:
        db = self._require_db()
        result = await db.execute(
            select(UserFunnelState)
            .where(UserFunnelState.user_id == user_id, UserFunnelState.status == FunnelStatus.active)
            .order_by(UserFunnelState.started_at.desc())
        )
        return list(result.scalars().all())

    async def _get_funnel_by_entry_key(self, entry_key: str) -> Funnel | None:
        db = self._require_db()
        result = await db.execute(
            select(Funnel).where(Funnel.entry_key == entry_key, Funnel.is_archived.is_(False))
        )
        return result.scalar_one_or_none()

    async def _get_funnel_by_name(self, name: str) -> Funnel | None:
        db = self._require_db()
        result = await db.execute(select(Funnel).where(Funnel.name == name, Funnel.is_archived.is_(False)))
        return result.scalar_one_or_none()

    async def _require_funnel(self, funnel_id: UUID) -> Funnel:
        db = self._require_db()
        result = await db.execute(select(Funnel).where(Funnel.id == funnel_id))
        funnel = result.scalar_one_or_none()
        if funnel is None:
            raise RuntimeError(f"Funnel {funnel_id} not found")
        return funnel

    async def _get_first_step(self, funnel_id: UUID) -> FunnelStep | None:
        db = self._require_db()
        result = await db.execute(
            select(FunnelStep)
            .where(FunnelStep.funnel_id == funnel_id)
            .order_by(FunnelStep.order.asc())
        )
        return result.scalars().first()

    async def _get_step_by_key(self, funnel_id: UUID, step_key: str) -> FunnelStep | None:
        db = self._require_db()
        result = await db.execute(
            select(FunnelStep).where(FunnelStep.funnel_id == funnel_id, FunnelStep.step_key == step_key)
        )
        return result.scalar_one_or_none()

    async def _get_step_by_prefix(self, funnel_id: UUID, step_prefix: str) -> FunnelStep | None:
        db = self._require_db()
        result = await db.execute(select(FunnelStep).where(FunnelStep.funnel_id == funnel_id))
        for step in result.scalars().all():
            if step.id.hex.startswith(step_prefix):
                return step
        return None

    async def _get_next_active_step_by_order(self, funnel_id: UUID, current_order: int) -> FunnelStep | None:
        db = self._require_db()
        result = await db.execute(
            select(FunnelStep)
            .where(FunnelStep.funnel_id == funnel_id, FunnelStep.order > current_order, FunnelStep.is_active.is_(True))
            .order_by(FunnelStep.order.asc())
        )
        return result.scalars().first()

    async def _get_current_step(self, user_id: int, funnel_id: UUID) -> FunnelStep | None:
        state = await self._get_active_state(user_id, funnel_id)
        if state is None or state.current_step_id is None:
            return None
        db = self._require_db()
        result = await db.execute(select(FunnelStep).where(FunnelStep.id == state.current_step_id))
        return result.scalar_one_or_none()

    async def _load_step_config(self, step: FunnelStep) -> StepConfig:
        return StepConfig.model_validate(step.config or {})

    async def _schedule_task(self, *, user_id: int, task_type: str, payload: dict, delay_seconds: int) -> ScheduledTask:
        db = self._require_db()
        task = ScheduledTask(
            user_id=user_id,
            task_type=task_type,
            payload=payload,
            execute_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
            status=ScheduledTaskStatus.pending,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def _mark_funnel_completed(self, user_id: int, funnel_id: UUID) -> None:
        db = self._require_db()
        state = await self._get_active_state(user_id, funnel_id)
        if state is None:
            return
        state.status = FunnelStatus.completed
        state.updated_at = datetime.now()
        await db.commit()

    async def _pause_funnel(self, user_id: int, funnel_id: UUID) -> None:
        db = self._require_db()
        state = await self._get_active_state(user_id, funnel_id)
        if state is None:
            return
        state.status = FunnelStatus.paused
        state.updated_at = datetime.now()
        await db.commit()

    async def _advance_to_next_step(self, ctx: ExecutionContext, config: StepConfig) -> None:
        if config.after_step.next_step == "end":
            await self._mark_funnel_completed(ctx.user.telegram_id, ctx.funnel.id)
            return

        next_step: FunnelStep | None
        if config.after_step.next_step == "auto":
            next_step = await self._get_next_active_step_by_order(ctx.funnel.id, ctx.step.order)
        else:
            next_step = await self._get_step_by_key(ctx.funnel.id, config.after_step.next_step)

        if next_step is None:
            await self._mark_funnel_completed(ctx.user.telegram_id, ctx.funnel.id)
            return

        state = await self._get_active_state(ctx.user.telegram_id, ctx.funnel.id)
        await self.execute_step_for_user(
            ctx.user,
            next_step,
            state=state,
            execution_id=uuid4(),
        )

    async def _build_keyboard(self, config: StepConfig, step_id: UUID, ctx: ExecutionContext):
        if ctx.is_test and ctx.emulated_tags is not None:
            user_tags = set(ctx.emulated_tags)
        elif ctx.is_test:
            user_tags = set()
        else:
            user_tags = await get_user_tags(self._require_db(), ctx.user.telegram_id)
        return build_keyboard_for_step(
            config,
            step_id,
            user_tags=user_tags,
            ignore_visibility=ctx.is_test and ctx.emulated_tags is None,
        )

    async def _send_message_block(
        self,
        ctx: ExecutionContext,
        message: MessageContent,
        reply_markup=None,
    ) -> bool:
        bot = self._require_bot()
        try:
            return await send_block(bot, ctx.user.telegram_id, message, reply_markup=reply_markup)
        except TelegramForbiddenError:
            if not ctx.is_test:
                await self._pause_funnel(ctx.user.telegram_id, ctx.funnel.id)
            raise

    async def _send_step_contents(
        self,
        ctx: ExecutionContext,
        config: StepConfig,
        *,
        start_block_index: int = 0,
        skip_test_delay_cap: bool = False,
    ) -> tuple[bool, int | None]:
        message_blocks = [block for block in config.blocks if isinstance(block, MessageContent)]
        button_groups = [block for block in config.blocks if isinstance(block, ButtonGroup)]
        keyboard = await self._build_keyboard(config, ctx.step.id, ctx)
        if len(button_groups) > 1:
            logger.warning("Step %s has multiple button groups; using the first one", ctx.step.id)

        if not message_blocks and button_groups and keyboard is not None:
            blank_message = MessageContent(type="text", content_text="\u200b")
            ok = await self._send_message_block(ctx, blank_message, reply_markup=keyboard)
            if not ok:
                logger.warning("Failed to send button-only step %s to user %s", ctx.step.id, ctx.user.telegram_id)
            return True, None

        content_index = -1
        for block in message_blocks:
            content_index += 1
            if content_index < start_block_index:
                continue

            reply_markup = keyboard if content_index == len(message_blocks) - 1 else None
            ok = await self._send_message_block(ctx, block, reply_markup=reply_markup)
            if not ok:
                logger.warning(
                    "Failed to send block %s for step %s to user %s",
                    block.id,
                    ctx.step.id,
                    ctx.user.telegram_id,
                )

            if ctx.is_test:
                if block.delay_after > 0:
                    await asyncio.sleep(min(block.delay_after, 2 if not skip_test_delay_cap else block.delay_after))
                continue

            delay_after_seconds = int(block.delay_after or 0)
            if delay_after_seconds >= THRESHOLD_INLINE_DELAY_SECONDS:
                await self._schedule_task(
                    user_id=ctx.user.telegram_id,
                    task_type="continue_step",
                    payload={
                        "state_id": str((await self._get_active_state(ctx.user.telegram_id, ctx.funnel.id)).id),
                        "step_id": str(ctx.step.id),
                        "execution_id": str(ctx.execution_id),
                        "start_block_index": content_index + 1,
                    },
                    delay_seconds=delay_after_seconds,
                )
                return False, content_index + 1

            if delay_after_seconds > 0:
                await asyncio.sleep(delay_after_seconds)

        return True, None

    async def start_funnel(self, user: User, funnel: Funnel) -> UserFunnelState | None:
        db = self._require_db()
        user = await self.upsert_user(
            user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source_deeplink=user.source_deeplink,
        )

        existing_same_state = await self._get_active_state(user.telegram_id, funnel.id)
        if existing_same_state is not None:
            return existing_same_state

        if not funnel.is_active or funnel.is_archived:
            return None

        cross_entry = await resolve_cross_entry(db, user.telegram_id, funnel)
        if cross_entry == CrossEntryResult.DENY:
            return None

        first_step = await self._get_first_step(funnel.id)
        state = UserFunnelState(
            user_id=user.telegram_id,
            funnel_id=funnel.id,
            current_step_id=first_step.id if first_step is not None else None,
            status=FunnelStatus.active,
        )
        db.add(state)
        await db.commit()
        await db.refresh(state)

        if first_step is None:
            return state

        await self.execute_step_for_user(user, first_step, state=state, execution_id=uuid4())
        return state

    async def execute_step_for_user(
        self,
        user: User,
        step: FunnelStep,
        *,
        state: UserFunnelState | None = None,
        execution_id: UUID | None = None,
        start_block_index: int = 0,
        is_test: bool = False,
        emulated_tags: list[str] | None = None,
        skip_trigger_check: bool = False,
        skip_delay_before: bool = False,
    ) -> None:
        db = self._require_db()
        user = await self.upsert_user(
            user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source_deeplink=user.source_deeplink,
        )

        funnel = await self._require_funnel(step.funnel_id)
        config = await self._load_step_config(step)
        execution_id = execution_id or uuid4()

        if not is_test and not skip_trigger_check:
            user_tags = await get_user_tags(db, user.telegram_id)
            if not should_execute_step(config.trigger_condition, user_tags):
                await self._advance_to_next_step(ExecutionContext(user, funnel, step, execution_id, is_test, emulated_tags), config)
                return

        if not is_test and state is None:
            state = await self._get_active_state(user.telegram_id, step.funnel_id)
            if state is None:
                state = UserFunnelState(
                    user_id=user.telegram_id,
                    funnel_id=step.funnel_id,
                    current_step_id=step.id,
                    status=FunnelStatus.active,
                )
                db.add(state)
                await db.commit()
                await db.refresh(state)

        if not is_test:
            state = state or await self._get_active_state(user.telegram_id, step.funnel_id)
            if state is None:
                logger.warning("No active state found for user %s and funnel %s", user.telegram_id, step.funnel_id)
                return

            state.current_step_id = step.id
            state.status = FunnelStatus.active
            state.updated_at = datetime.now()
            await db.commit()

        ctx = ExecutionContext(
            user=user,
            funnel=funnel,
            step=step,
            execution_id=execution_id,
            is_test=is_test,
            emulated_tags=emulated_tags,
        )

        if not is_test and not skip_delay_before:
            delay_before_seconds = self._delay_to_seconds(config.delay_before)
            if delay_before_seconds >= THRESHOLD_INLINE_DELAY_SECONDS:
                await self._schedule_task(
                    user_id=user.telegram_id,
                    task_type="execute_step",
                    payload={
                        "state_id": str(state.id),
                        "step_id": str(step.id),
                        "execution_id": str(execution_id),
                        "start_block_index": start_block_index,
                    },
                    delay_seconds=delay_before_seconds,
                )
                return

            if delay_before_seconds > 0:
                await asyncio.sleep(delay_before_seconds)

        finished_inline, scheduled_index = await self._send_step_contents(
            ctx,
            config,
            start_block_index=start_block_index,
        )
        if not finished_inline:
            return

        if not is_test:
            db = self._require_db()
            for tag in config.after_step.add_tags:
                await TagService.add_tag(db, user.telegram_id, tag)

            if config.after_step.dozhim_if_no_click_hours is not None:
                await self._schedule_task(
                    user_id=user.telegram_id,
                    task_type="trigger_dozhim",
                    payload={"state_id": str(state.id), "step_id": str(step.id)},
                    delay_seconds=int(config.after_step.dozhim_if_no_click_hours) * 3600,
                )

        if not is_test and config.wait_for_payment:
            return

        if not is_test:
            await self._advance_to_next_step(ctx, config)

    async def run_test_for_admin(
        self,
        admin_telegram_id: int,
        step: FunnelStep,
        emulated_tags: list[str] | None = None,
    ) -> None:
        user = User(telegram_id=admin_telegram_id)
        funnel = await self._require_funnel(step.funnel_id)
        await self.execute_step_for_user(
            user,
            step,
            state=None,
            execution_id=uuid4(),
            start_block_index=0,
            is_test=True,
            emulated_tags=emulated_tags,
            skip_trigger_check=True,
            skip_delay_before=True,
        )

    async def run_full_funnel_test_for_admin(self, admin_telegram_id: int, funnel: Funnel) -> None:
        db = self._require_db()
        result = await db.execute(select(FunnelStep).where(FunnelStep.funnel_id == funnel.id).order_by(FunnelStep.order.asc()))
        steps = list(result.scalars().all())
        for index, step in enumerate(steps):
            await self.run_test_for_admin(admin_telegram_id, step, emulated_tags=None)
            if index < len(steps) - 1:
                await asyncio.sleep(3)

    async def handle_button_click(
        self,
        user: User,
        step: FunnelStep,
        button_id: UUID,
        callback_data: str,
    ) -> None:
        db = self._require_db()
        user = await self.upsert_user(
            user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source_deeplink=user.source_deeplink,
        )

        config = await self._load_step_config(step)
        button_group = next((block for block in config.blocks if isinstance(block, ButtonGroup)), None)
        if button_group is None:
            logger.warning("Button click received for step %s without button group", step.id)
            return

        target_button: Button | None = None
        for button in button_group.buttons:
            if button.id == button_id:
                target_button = button
                break

        if target_button is None:
            logger.warning("Button %s not found in step %s", button_id, step.id)
            return

        user_tags = await get_user_tags(db, user.telegram_id)
        if not check_visibility(target_button.visible_if, user_tags):
            logger.warning("Button %s is hidden for user %s", button_id, user.telegram_id)
            return

        click_tag = f"funnel_step_clicked:{step.id}"
        if await TagService.has_tag(db, user.telegram_id, click_tag):
            return
        await TagService.add_tag(db, user.telegram_id, click_tag)

        action = target_button.action
        advance = False
        next_step_key: str | None = None

        if action.type == "url":
            await handle_url(db, user, action)
        elif action.type == "pay_product":
            await handle_pay_product(self._require_bot(), db, user, action)
        elif action.type == "goto_step":
            result = await handle_goto_step(db, user, action)
            advance = result.advance
            next_step_key = result.next_step_key
        elif action.type == "add_tag":
            await handle_add_tag(db, user, action)
        elif action.type == "open_track":
            await handle_open_track(db, user, action)
        elif action.type == "signal":
            await handle_signal(db, user, action)

        if advance and next_step_key:
            next_step = await self._get_step_by_key(step.funnel_id, next_step_key)
            if next_step is None:
                logger.warning("Target step %s not found in funnel %s", next_step_key, step.funnel_id)
                return
            state = await self._get_active_state(user.telegram_id, step.funnel_id)
            await self.execute_step_for_user(user, next_step, state=state, execution_id=uuid4())

    async def continue_after_payment(self, user: User, funnel: Funnel) -> None:
        db = self._require_db()
        user = await self.upsert_user(
            user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source_deeplink=user.source_deeplink,
        )

        state = await self._get_active_state(user.telegram_id, funnel.id)
        if state is None or state.current_step_id is None:
            return

        result = await db.execute(select(FunnelStep).where(FunnelStep.id == state.current_step_id))
        step = result.scalar_one_or_none()
        if step is None:
            return

        config = await self._load_step_config(step)
        if not config.wait_for_payment:
            return

        if config.after_step.next_step == "end":
            await self._mark_funnel_completed(user.telegram_id, funnel.id)
            return

        if config.after_step.next_step == "auto":
            next_step = await self._get_next_active_step_by_order(funnel.id, step.order)
        else:
            next_step = await self._get_step_by_key(funnel.id, config.after_step.next_step)

        if next_step is None:
            await self._mark_funnel_completed(user.telegram_id, funnel.id)
            return

        await self.execute_step_for_user(user, next_step, state=state, execution_id=uuid4())

    async def trigger_dozhim(self, user: User, step: FunnelStep) -> None:
        db = self._require_db()
        user = await self.upsert_user(
            user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            source_deeplink=user.source_deeplink,
        )

        state = await self._get_active_state(user.telegram_id, step.funnel_id)
        if state is None or state.current_step_id != step.id:
            return

        if await TagService.has_tag(db, user.telegram_id, f"funnel_step_clicked:{step.id}"):
            return

        dozhim_funnel = await self._get_funnel_by_entry_key("dozhim")
        if dozhim_funnel is None:
            dozhim_funnel = await self._get_funnel_by_name("Дожим")
        if dozhim_funnel is None:
            return

        await self.start_funnel(user, dozhim_funnel)

    @staticmethod
    def _delay_to_seconds(delay) -> int:
        unit_map = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
        return int(delay.value) * unit_map[delay.unit]
