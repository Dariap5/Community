from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "telegram_sales_bot",
    broker=settings.redis_dsn,
    backend=settings.redis_dsn,
    include=["app.tasks.funnel_tasks"],
)

celery_app.conf.beat_schedule = {
    "poll-scheduled-tasks": {
        "task": "app.tasks.funnel_tasks.process_scheduled_tasks",
        "schedule": settings.scheduler_poll_seconds,
    }
}
celery_app.conf.timezone = "UTC"
