import asyncio
import logging

from aiogram import Bot
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    Broadcast,
    BroadcastRecipient,
    ScheduledTaskStatus,
    User,
    UserActionLog,
)
from app.db.session import SessionLocal
from app.funnels.engine import FunnelEngine
from app.services.funnel_service import FunnelService
from app.services.scheduler_service import SchedulerService
from app.services.tag_service import TagService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="app.tasks.jobs.poll_scheduled_tasks")
def poll_scheduled_tasks() -> None:
    asyncio.run(_poll_scheduled_tasks_async())


async def _poll_scheduled_tasks_async() -> None:
    engine = FunnelEngine()
    async with SessionLocal() as session:
        tasks = await SchedulerService.fetch_due_tasks(session)
        for task in tasks:
            await SchedulerService.mark_processing(session, task)
            try:
                if task.task_type == "funnel_step_dispatch":
                    await engine.dispatch_step(
                        session,
                        funnel_state_id=task.payload["funnel_state_id"],
                        step_order=task.payload["step_order"],
                    )
                elif task.task_type == "continue_step_messages":
                    await engine.continue_step_messages(
                        session,
                        funnel_state_id=task.payload["funnel_state_id"],
                        step_order=task.payload["step_order"],
                        start_message_order=task.payload["start_message_order"],
                    )
                elif task.task_type == "payment_confirmed":
                    await engine.handle_payment_confirmed(session, purchase_id=task.payload["purchase_id"])
                elif task.task_type == "start_funnel":
                    await _handle_start_funnel_task(session, task)
                elif task.task_type == "start_dozhim_if_no_choice":
                    await _handle_start_dozhim_if_no_choice(session, task)
                elif task.task_type == "community_track_delivery":
                    await engine.handle_community_track(
                        session,
                        user_id=task.user_id,
                        track_id=task.payload["track_id"],
                    )
                elif task.task_type == "broadcast_dispatch":
                    await _handle_broadcast_dispatch(session, task.payload["broadcast_id"])

                task.status = ScheduledTaskStatus.done
                await session.commit()
            except Exception as error:
                logger.exception("Task %s failed: %s", task.id, error)
                await SchedulerService.mark_failed(session, task, str(error))


async def _handle_start_funnel_task(session, task) -> None:
    user_result = await session.execute(select(User).where(User.id == task.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    required_tag = task.payload.get("required_tag")
    if required_tag and not await TagService.has_tag(session, user.id, str(required_tag)):
        return

    if await FunnelService.has_active_funnel(session, user.id):
        return

    await FunnelService.start_funnel(session, user, funnel_name=task.payload["funnel_name"])


async def _handle_start_dozhim_if_no_choice(session, task) -> None:
    absent_tag = str(task.payload.get("required_absent_tag", "community_choice_made"))
    if await TagService.has_tag(session, task.user_id, absent_tag):
        return

    user_result = await session.execute(select(User).where(User.id == task.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    if await FunnelService.has_active_funnel(session, user.id):
        return

    await FunnelService.start_funnel(session, user, funnel_name="dozhim")


async def _handle_broadcast_dispatch(session, broadcast_id: int) -> None:
    broadcast_result = await session.execute(select(Broadcast).where(Broadcast.id == broadcast_id))
    broadcast = broadcast_result.scalar_one_or_none()
    if broadcast is None:
        return

    rec_result = await session.execute(
        select(BroadcastRecipient).where(
            BroadcastRecipient.broadcast_id == broadcast.id,
            BroadcastRecipient.delivery_status == "pending",
        )
    )
    recipients = list(rec_result.scalars().all())
    if not recipients:
        broadcast.status = "done"
        await session.commit()
        return

    bot = Bot(token=settings.bot_token)
    try:
        for recipient in recipients:
            user_result = await session.execute(select(User).where(User.id == recipient.user_id))
            user = user_result.scalar_one_or_none()
            if user is None:
                recipient.delivery_status = "failed"
                await session.commit()
                continue

            try:
                if broadcast.content_type == "text":
                    await bot.send_message(chat_id=user.telegram_id, text=broadcast.content_text or "", parse_mode="HTML")
                elif broadcast.content_type == "photo" and broadcast.content_file:
                    await bot.send_photo(
                        chat_id=user.telegram_id,
                        photo=broadcast.content_file,
                        caption=broadcast.content_text,
                        parse_mode="HTML",
                    )
                elif broadcast.content_type == "document" and broadcast.content_file:
                    await bot.send_document(
                        chat_id=user.telegram_id,
                        document=broadcast.content_file,
                        caption=broadcast.content_text,
                        parse_mode="HTML",
                    )
                else:
                    await bot.send_message(chat_id=user.telegram_id, text=broadcast.content_text or "", parse_mode="HTML")

                recipient.delivery_status = "done"
                session.add(
                    UserActionLog(
                        user_id=user.id,
                        action_type="broadcast_delivered",
                        payload={"broadcast_id": broadcast.id},
                    )
                )
                await session.commit()
            except Exception:
                recipient.delivery_status = "failed"
                await session.commit()

            await asyncio.sleep(1 / 30)
    finally:
        await bot.session.close()

    broadcast.status = "done"
    await session.commit()
