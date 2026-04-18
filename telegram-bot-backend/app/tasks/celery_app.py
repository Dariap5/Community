from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "telegram_sales_bot",
    broker=settings.redis_dsn,
    backend=settings.redis_dsn,
)

celery_app.conf.beat_schedule = {
    "poll-scheduled-tasks": {
        "task": "app.tasks.jobs.poll_scheduled_tasks",
        "schedule": settings.scheduler_poll_seconds,
    }
}
celery_app.conf.timezone = "UTC"
