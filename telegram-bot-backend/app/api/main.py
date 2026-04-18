from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.payments import router as payments_router
from app.config import get_settings

app = FastAPI(title="Telegram Sales Bot API")
settings = get_settings()

app.add_middleware(SessionMiddleware, secret_key=settings.admin_session_secret)

app.include_router(payments_router, prefix="/api")
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
