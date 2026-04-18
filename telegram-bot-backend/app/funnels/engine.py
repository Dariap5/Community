import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import (
    CommunityTrack,
    ButtonType,
    Funnel,
    FunnelStep,
    PaymentStatus,
    Purchase,
    ScheduledTask,
    ScheduledTaskStatus,
    StepMessage,
    StepMessageType,
    User,
    UserActionLog,
    UserFunnelState,
)
from app.services.tag_service import TagService

logger = logging.getLogger(__name__)


class FunnelEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def dispatch_step(self, session: AsyncSession, funnel_state_id: int, step_order: int) -> None:
        state_result = await session.execute(
            select(UserFunnelState).where(UserFunnelState.id == funnel_state_id)
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            return

        user_result = await session.execute(select(User).where(User.id == state.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        step_result = await session.execute(
            select(FunnelStep)
            .options(selectinload(FunnelStep.messages), selectinload(FunnelStep.buttons))
            .where(FunnelStep.funnel_id == state.funnel_id, FunnelStep.step_order == step_order)
        )
        step = step_result.scalar_one_or_none()
        if step is None:
            return

        if step.trigger_conditions.get("enabled", True) is False:
            await self._schedule_next_step(session, user.id, state.id, step)
            return

        state.current_step_id = step.id
        state.last_step_at = datetime.now(timezone.utc)
        await session.commit()

        await self._send_step_messages(
            session=session,
            user=user,
            state=state,
            step=step,
            start_message_order=1,
        )

    async def continue_step_messages(
        self,
        session: AsyncSession,
        funnel_state_id: int,
        step_order: int,
        start_message_order: int,
    ) -> None:
        state_result = await session.execute(
            select(UserFunnelState).where(UserFunnelState.id == funnel_state_id)
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            return

        user_result = await session.execute(select(User).where(User.id == state.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        step_result = await session.execute(
            select(FunnelStep)
            .options(selectinload(FunnelStep.messages), selectinload(FunnelStep.buttons))
            .where(FunnelStep.funnel_id == state.funnel_id, FunnelStep.step_order == step_order)
        )
        step = step_result.scalar_one_or_none()
        if step is None:
            return

        await self._send_step_messages(
            session=session,
            user=user,
            state=state,
            step=step,
            start_message_order=start_message_order,
        )

    async def _send_step_messages(
        self,
        session: AsyncSession,
        user: User,
        state: UserFunnelState,
        step: FunnelStep,
        start_message_order: int,
    ) -> None:
        bot = Bot(token=self.settings.bot_token)
        tags = await TagService.user_tags(session, user.id)
        keyboard = self._build_step_keyboard(step.buttons, tags)

        try:
            messages = sorted(step.messages, key=lambda item: item.message_order)
            for message in messages:
                if message.message_order < start_message_order:
                    continue

                await self._send_submessage_with_retry(bot, user.telegram_id, message, keyboard)
                if message.delay_after_seconds <= 0:
                    continue

                if message.delay_after_seconds <= self.settings.short_delay_max_seconds:
                    await asyncio.sleep(message.delay_after_seconds)
                    continue

                await self._schedule_task(
                    session=session,
                    user_id=user.id,
                    task_type="continue_step_messages",
                    payload={
                        "funnel_state_id": state.id,
                        "step_order": step.step_order,
                        "start_message_order": message.message_order + 1,
                    },
                    delay_seconds=message.delay_after_seconds,
                )
                return

            session.add(
                UserActionLog(
                    user_id=user.id,
                    action_type="step_delivered",
                    funnel_step_id=step.id,
                    payload={"step_order": step.step_order, "funnel_id": step.funnel_id},
                )
            )
            await session.commit()

            await self._execute_post_actions(session, user, state, step)
            await self._schedule_next_step(session, user.id, state.id, step)
        finally:
            await bot.session.close()

    async def _schedule_next_step(
        self,
        session: AsyncSession,
        user_id: int,
        funnel_state_id: int,
        step: FunnelStep,
    ) -> None:
        if step.trigger_conditions.get("wait_for_payment") is True:
            return

        next_step_order = step.step_order + 1
        await self._schedule_task(
            session=session,
            user_id=user_id,
            task_type="funnel_step_dispatch",
            payload={"funnel_state_id": funnel_state_id, "step_order": next_step_order},
            delay_seconds=step.delay_before_seconds,
        )

    async def _execute_post_actions(
        self,
        session: AsyncSession,
        user: User,
        state: UserFunnelState,
        step: FunnelStep,
    ) -> None:
        actions = step.trigger_conditions.get("post_actions", {})
        add_tags = actions.get("add_tags", [])
        for tag in add_tags:
            await TagService.add_tag(session, user.id, str(tag))

        launch_funnel = actions.get("launch_funnel")
        if isinstance(launch_funnel, dict):
            await self._schedule_task(
                session=session,
                user_id=user.id,
                task_type="start_funnel",
                payload={
                    "funnel_name": str(launch_funnel.get("name", "")),
                    "required_tag": launch_funnel.get("required_tag"),
                },
                delay_seconds=int(launch_funnel.get("delay_seconds", 0)),
            )

        dozhim_no_click_hours = actions.get("start_dozhim_if_no_click_hours")
        if dozhim_no_click_hours is not None:
            await self._schedule_task(
                session=session,
                user_id=user.id,
                task_type="start_dozhim_if_no_choice",
                payload={"required_absent_tag": "community_choice_made"},
                delay_seconds=int(dozhim_no_click_hours) * 3600,
            )

    async def handle_payment_confirmed(self, session: AsyncSession, purchase_id: int) -> None:
        result = await session.execute(
            select(Purchase).options(selectinload(Purchase.product)).where(Purchase.id == purchase_id)
        )
        purchase = result.scalar_one_or_none()
        if purchase is None or purchase.payment_status != PaymentStatus.paid:
            return

        user_result = await session.execute(select(User).where(User.id == purchase.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        if purchase.metadata_payload.get("paid_tag") == "купил_комьюнити":
            await self._send_track_choice(session, user.telegram_id)
            return

        funnel_result = await session.execute(select(Funnel).where(Funnel.name == "product"))
        funnel = funnel_result.scalar_one_or_none()
        if funnel is None:
            return

        state_result = await session.execute(
            select(UserFunnelState).where(
                UserFunnelState.user_id == user.id,
                UserFunnelState.funnel_id == funnel.id,
            )
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            return

        await self._schedule_task(
            session=session,
            user_id=user.id,
            task_type="funnel_step_dispatch",
            payload={"funnel_state_id": state.id, "step_order": 3},
            delay_seconds=0,
        )

    async def handle_community_track(self, session: AsyncSession, user_id: int, track_id: int) -> None:
        track_result = await session.execute(select(CommunityTrack).where(CommunityTrack.id == track_id))
        track = track_result.scalar_one_or_none()
        if track is None:
            return

        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        bot = Bot(token=self.settings.bot_token)
        try:
            for item in track.messages_payload:
                text = str(item.get("text", ""))
                if text:
                    await self._send_text_with_retry(bot, user.telegram_id, text)
        finally:
            await bot.session.close()

    @staticmethod
    def _build_step_keyboard(buttons, user_tags: set[str]) -> InlineKeyboardMarkup | None:
        active_buttons = sorted((b for b in buttons if b.is_enabled), key=lambda item: item.button_order)
        if not active_buttons:
            return None

        row = []
        for button in active_buttons:
            required_tags = set(button.conditions.get("require_tags", []))
            exclude_tags = set(button.conditions.get("exclude_tags", []))
            if required_tags and not required_tags.issubset(user_tags):
                continue
            if exclude_tags and exclude_tags.intersection(user_tags):
                continue

            if button.button_type == ButtonType.url:
                row.append(InlineKeyboardButton(text=button.text, url=button.value))
            elif button.button_type == ButtonType.callback:
                row.append(InlineKeyboardButton(text=button.text, callback_data=button.value))
            elif button.button_type == ButtonType.payment:
                row.append(InlineKeyboardButton(text=button.text, callback_data=f"pay:{button.value}"))

        return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None

    async def _send_submessage_with_retry(
        self,
        bot: Bot,
        telegram_id: int,
        message: StepMessage,
        keyboard: InlineKeyboardMarkup | None,
    ) -> None:
        try:
            await self._send_submessage(bot, telegram_id, message, keyboard)
            return
        except Exception as error:
            logger.exception("Failed to send message_id=%s: %s", message.id, error)
            await asyncio.sleep(self.settings.send_retry_seconds)
            await self._send_submessage(bot, telegram_id, message, keyboard)

    @staticmethod
    async def _send_submessage(
        bot: Bot,
        telegram_id: int,
        message: StepMessage,
        keyboard: InlineKeyboardMarkup | None,
    ) -> None:
        parse_mode = message.parse_mode or "HTML"

        if message.message_type == StepMessageType.text:
            await bot.send_message(
                chat_id=telegram_id,
                text=message.content_text or "",
                reply_markup=keyboard,
                parse_mode=parse_mode,
            )
            return

        if message.message_type == StepMessageType.photo and message.content_file:
            await bot.send_photo(
                chat_id=telegram_id,
                photo=message.content_file,
                caption=message.caption,
                reply_markup=keyboard,
                parse_mode=parse_mode,
            )
            return

        if message.message_type == StepMessageType.document and message.content_file:
            await bot.send_document(
                chat_id=telegram_id,
                document=message.content_file,
                caption=message.caption,
                reply_markup=keyboard,
                parse_mode=parse_mode,
            )
            return

        if message.message_type == StepMessageType.video_note and message.content_file:
            await bot.send_video_note(chat_id=telegram_id, video_note=message.content_file)
            return

        if message.message_type == StepMessageType.voice and message.content_file:
            await bot.send_voice(
                chat_id=telegram_id,
                voice=message.content_file,
                caption=message.caption,
                parse_mode=parse_mode,
            )
            return

        if message.message_type == StepMessageType.video and message.content_file:
            await bot.send_video(
                chat_id=telegram_id,
                video=message.content_file,
                caption=message.caption,
                parse_mode=parse_mode,
                reply_markup=keyboard,
            )

    async def _send_text_with_retry(self, bot: Bot, telegram_id: int, text: str) -> None:
        try:
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
            return
        except Exception as error:
            logger.exception("Failed to send text to user=%s: %s", telegram_id, error)
            await asyncio.sleep(self.settings.send_retry_seconds)
            await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")

    async def _send_track_choice(self, session: AsyncSession, telegram_id: int) -> None:
        tracks_result = await session.execute(select(CommunityTrack).order_by(CommunityTrack.id.asc()))
        tracks = list(tracks_result.scalars().all())
        if not tracks:
            return

        keyboard_rows = [
            [InlineKeyboardButton(text=track.title, callback_data=f"community:track:{track.id}")]
            for track in tracks
        ]
        bot = Bot(token=self.settings.bot_token)
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text="Выберите карьерный трек:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
            )
        finally:
            await bot.session.close()

    async def _schedule_task(
        self,
        session: AsyncSession,
        user_id: int,
        task_type: str,
        payload: dict,
        delay_seconds: int,
    ) -> None:
        session.add(
            ScheduledTask(
                user_id=user_id,
                task_type=task_type,
                payload=payload,
                run_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
                status=ScheduledTaskStatus.pending,
            )
        )
        await session.commit()
