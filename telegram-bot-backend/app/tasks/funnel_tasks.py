from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from celery import shared_task
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Funnel, FunnelStatus, FunnelStep, Purchase, ScheduledTask, ScheduledTaskStatus, User, UserFunnelState
from app.db.session import SessionLocal
from app.funnels.engine import FunnelEngine

logger = logging.getLogger(__name__)
settings = get_settings()


@shared_task(name="app.tasks.funnel_tasks.process_scheduled_tasks")
def process_scheduled_tasks() -> None:
    asyncio.run(_process_scheduled_tasks())


async def _process_scheduled_tasks() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    try:
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(ScheduledTask)
                .where(
                    ScheduledTask.status == ScheduledTaskStatus.pending,
                    ScheduledTask.execute_at <= now,
                )
                .order_by(ScheduledTask.execute_at.asc())
            )
            tasks = list(result.scalars().all())
            if not tasks:
                return

            engine = FunnelEngine(bot=bot, db=db)
            for task in tasks:
                task.status = ScheduledTaskStatus.processing
                await db.commit()

                try:
                    await _dispatch_task(engine, task)
                    task.status = ScheduledTaskStatus.done
                    await db.commit()
                except Exception as error:
                    logger.exception("Scheduled task %s failed: %s", task.id, error)
                    task.status = ScheduledTaskStatus.failed
                    await db.commit()

                await asyncio.sleep(1 / 30)
    finally:
        await bot.session.close()


async def _dispatch_task(engine: FunnelEngine, task: ScheduledTask) -> None:
    db = engine.db
    if db is None:
        raise RuntimeError("Funnel task processing requires a database session")

    payload = task.payload or {}

    if task.task_type == "execute_step":
        user = await db.get(User, task.user_id)
        step = await db.get(FunnelStep, UUID(payload["step_id"])) if payload.get("step_id") else None
        state = await db.get(UserFunnelState, UUID(payload["state_id"])) if payload.get("state_id") else None
        if user is not None and step is not None:
            await engine.execute_step_for_user(
                user,
                step,
                state=state,
                execution_id=UUID(payload["execution_id"]) if payload.get("execution_id") else UUID(int=0),
                start_block_index=int(payload.get("start_block_index", 0)),
                skip_trigger_check=True,
                skip_delay_before=True,
            )
        return

    if task.task_type == "continue_step":
        user = await db.get(User, task.user_id)
        step = await db.get(FunnelStep, UUID(payload["step_id"])) if payload.get("step_id") else None
        state = await db.get(UserFunnelState, UUID(payload["state_id"])) if payload.get("state_id") else None
        if user is not None and step is not None:
            await engine.execute_step_for_user(
                user,
                step,
                state=state,
                execution_id=UUID(payload["execution_id"]) if payload.get("execution_id") else UUID(int=0),
                start_block_index=int(payload.get("start_block_index", 0)),
                skip_trigger_check=True,
                skip_delay_before=True,
            )
        return

    if task.task_type == "start_funnel":
        user = await db.get(User, task.user_id)
        funnel = await _load_funnel(engine, payload)
        if user is not None and funnel is not None:
            await engine.start_funnel(user, funnel)
        return

    if task.task_type in {"continue_after_payment", "payment_confirmed"}:
        user = await db.get(User, task.user_id)
        if user is None:
            purchase_id = payload.get("purchase_id")
            if purchase_id:
                purchase = await db.get(Purchase, UUID(str(purchase_id)))
                if purchase is not None:
                    user = await db.get(User, purchase.user_id)
        if user is None:
            return

        active_states = list(
            (
                await db.execute(
                    select(UserFunnelState).where(
                        UserFunnelState.user_id == user.telegram_id,
                        UserFunnelState.status == FunnelStatus.active,
                    )
                )
            )
            .scalars()
            .all()
        )
        for state in active_states:
            funnel = await db.get(Funnel, state.funnel_id)
            if funnel is not None:
                await engine.continue_after_payment(user, funnel)
        return

    if task.task_type == "trigger_dozhim":
        user = await db.get(User, task.user_id)
        step = await db.get(FunnelStep, UUID(payload["step_id"])) if payload.get("step_id") else None
        if user is not None and step is not None:
            await engine.trigger_dozhim(user, step)
        return

    logger.warning("Unknown scheduled task type: %s", task.task_type)


async def _load_funnel(engine: FunnelEngine, payload: dict) -> Funnel | None:
    if payload.get("funnel_id"):
        return await engine._require_funnel(UUID(payload["funnel_id"]))
    if payload.get("entry_key"):
        return await engine._get_funnel_by_entry_key(str(payload["entry_key"]))
    if payload.get("funnel_name"):
        return await engine._get_funnel_by_name(str(payload["funnel_name"]))
    return None
