from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.db.models import (
    ButtonClickStat,
    ButtonType,
    CommunityTrack,
    ScheduledTask,
    ScheduledTaskStatus,
    StepButton,
    User,
    UserActionLog,
)
from app.db.session import SessionLocal
from app.services.settings_service import SettingsService
from app.services.tag_service import TagService

router = Router(name="callbacks")


async def _track_callback_click(session, user_id: int, callback_data: str) -> None:
    button_result = await session.execute(
        select(StepButton).where(
            StepButton.button_type == ButtonType.callback,
            StepButton.value == callback_data,
        )
    )
    button = button_result.scalar_one_or_none()
    if button is not None:
        session.add(ButtonClickStat(step_button_id=button.id, user_id=user_id))
        session.add(
            UserActionLog(
                user_id=user_id,
                action_type="button_clicked",
                funnel_step_id=button.step_id,
                payload={"button_id": button.id, "callback": callback_data},
            )
        )
        await session.commit()


@router.callback_query(F.data == "community:join")
async def community_join_handler(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await callback.answer("Сначала используйте /start")
            return

        await _track_callback_click(session, user.id, "community:join")

        await TagService.add_tag(session, user.id, "community_choice_made")
        text = await SettingsService.get_text(
            session,
            key="community_payment_text",
            default="Выберите формат оплаты комьюнити:",
        )
        payment_url = await SettingsService.get_text(
            session,
            key="community_payment_url",
            default="https://example.com/community-pay",
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Оплатить комьюнити", url=payment_url)]]
        )
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    await callback.answer()


@router.callback_query(F.data == "community:doubt")
async def community_doubt_handler(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await callback.answer("Сначала используйте /start")
            return

        await _track_callback_click(session, user.id, "community:doubt")

        await TagService.add_tag(session, user.id, "community_choice_made")
        await TagService.add_tag(session, user.id, "есть_сомнения")

        calendly_url = await SettingsService.get_text(
            session,
            key="calendly_url",
            default="https://calendly.com/replace-me",
        )
        support_text = await SettingsService.get_text(
            session,
            key="doubt_support_text",
            default="Понимаем сомнения. Можно записаться на созвон:",
        )

        await callback.message.answer(
            f"{support_text}\n{calendly_url}",
            parse_mode="HTML",
        )

        delay_hours = await SettingsService.get_int(session, key="dozhim_after_doubt_hours", default=3)
        session.add(
            ScheduledTask(
                user_id=user.id,
                task_type="start_funnel",
                payload={"funnel_name": "dozhim"},
                run_at=datetime.now(timezone.utc) + timedelta(hours=delay_hours),
                status=ScheduledTaskStatus.pending,
            )
        )
        await session.commit()

    await callback.answer()


@router.callback_query(F.data.startswith("community:track:"))
async def community_track_handler(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    data = callback.data or ""
    try:
        track_id = int(data.split(":")[-1])
    except ValueError:
        await callback.answer("Некорректный трек")
        return

    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await callback.answer("Сначала используйте /start")
            return

        await _track_callback_click(session, user.id, data)

        track_result = await session.execute(select(CommunityTrack).where(CommunityTrack.id == track_id))
        track = track_result.scalar_one_or_none()
        if track is None:
            await callback.answer("Трек не найден")
            return

        for item in track.messages_payload:
            text = str(item.get("text", ""))
            if text:
                await callback.message.answer(text, parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data == "community:choose_track")
async def community_choose_track_handler(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    async with SessionLocal() as session:
        tracks_result = await session.execute(select(CommunityTrack).order_by(CommunityTrack.id.asc()))
        tracks = list(tracks_result.scalars().all())
        if not tracks:
            await callback.answer("Треки пока не настроены")
            return

        rows = [
            [InlineKeyboardButton(text=track.title, callback_data=f"community:track:{track.id}")]
            for track in tracks
        ]
        await callback.message.answer(
            "Выберите карьерный трек:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    await callback.answer()
