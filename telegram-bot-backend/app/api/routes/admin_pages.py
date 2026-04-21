from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import require_admin
from app.db.models import Funnel, FunnelStep
from app.db.session import get_db_session

router = APIRouter(prefix="/admin", tags=["admin-pages"], dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


@router.get("/funnels/{funnel_id}/steps/{step_id}", response_class=HTMLResponse)
async def step_editor_page(
    request: Request,
    funnel_id: UUID,
    step_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    funnel_result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    funnel = funnel_result.scalar_one_or_none()
    if funnel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Funnel not found")

    step_result = await session.execute(
        select(FunnelStep).where(FunnelStep.id == step_id, FunnelStep.funnel_id == funnel_id)
    )
    step = step_result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    return templates.TemplateResponse(
        request=request,
        name="admin/step_editor.html",
        context={
            "funnel_id": str(funnel.id),
            "step_id": str(step.id),
            "funnel_name": funnel.name,
            "step_name": step.name,
            "step_key": step.step_key,
            "page_title": f"Редактор шага — {step.name}",
        },
    )