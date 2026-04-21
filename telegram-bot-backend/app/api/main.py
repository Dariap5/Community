from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_pages import router as admin_pages_router
from app.api.routes.funnels import router as funnels_router
from app.api.routes.payments import router as payments_router
from app.config import get_settings
from app.db.models import Funnel
from app.db.session import get_db_session

app = FastAPI(title="Telegram Sales Bot API")
settings = get_settings()
static_dir = Path(__file__).resolve().parents[1] / "static"

app.add_middleware(SessionMiddleware, secret_key=settings.admin_session_secret)

app.include_router(payments_router, prefix="/api")
app.include_router(funnels_router)
app.include_router(admin_pages_router)
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _error_response(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_response("validation_error", "Invalid request data", exc.errors()),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_response("validation_error", "Invalid request data", exc.errors()),
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_error_response("conflict", "Resource already exists", {"error": str(exc.orig)}),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and {"code", "message"}.issubset(detail.keys()):
        payload = _error_response(detail["code"], detail["message"], detail.get("details"))
    else:
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
        }
        payload = _error_response(code_map.get(exc.status_code, "bad_request"), str(detail))
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.get("/health")
async def health(session: AsyncSession = Depends(get_db_session)) -> dict:
    funnels_result = await session.execute(select(func.count(Funnel.id)))
    return {"status": "ok", "funnels_count": int(funnels_result.scalar_one())}
