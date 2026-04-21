from aiogram import Router

from app.bot.handlers.callbacks import router as callbacks_router
from app.bot.handlers.start import router as start_router


def build_router() -> Router:
    router = Router()
    router.include_router(start_router)
    router.include_router(callbacks_router)
    return router
