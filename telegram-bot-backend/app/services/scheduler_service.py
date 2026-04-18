from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScheduledTask, ScheduledTaskStatus


class SchedulerService:
    @staticmethod
    async def fetch_due_tasks(session: AsyncSession, limit: int = 100) -> list[ScheduledTask]:
        query = (
            select(ScheduledTask)
            .where(
                ScheduledTask.status == ScheduledTaskStatus.pending,
                ScheduledTask.run_at <= datetime.now(timezone.utc),
            )
            .order_by(ScheduledTask.run_at.asc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def mark_processing(session: AsyncSession, task: ScheduledTask) -> None:
        task.status = ScheduledTaskStatus.processing
        await session.commit()

    @staticmethod
    async def mark_done(session: AsyncSession, task: ScheduledTask) -> None:
        task.status = ScheduledTaskStatus.done
        await session.commit()

    @staticmethod
    async def mark_failed(session: AsyncSession, task: ScheduledTask, error_text: str) -> None:
        task.retry_count += 1
        task.last_error = error_text
        if task.retry_count >= task.max_retries:
            task.status = ScheduledTaskStatus.failed
        else:
            task.status = ScheduledTaskStatus.pending
            task.run_at = datetime.now(timezone.utc)
        await session.commit()
