from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import require_admin
from app.db.models import Funnel, FunnelCrossEntryBehavior, FunnelStep
from app.db.session import get_db_session
from app.schemas.api import (
    ErrorResponse,
    FunnelCreate,
    FunnelListItem,
    FunnelRead,
    FunnelUpdate,
    StepCreate,
    StepRead,
    StepReorder,
    StepUpdate,
)
from app.services.funnels import (
    duplicate_funnel_with_steps,
    duplicate_step_in_funnel,
    get_funnel_with_stats,
    get_next_step_order,
    has_active_users_on_step,
    ensure_unique_step_key,
    list_funnels_with_stats,
    reorder_funnel_steps,
)

ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

router = APIRouter(
    prefix="/api/funnels",
    tags=["funnels"],
    dependencies=[Depends(require_admin)],
    responses=ERROR_RESPONSES,
)


def _api_error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": details})


def _serialize_step(step: FunnelStep) -> dict:
    return {
        "id": str(step.id),
        "funnel_id": str(step.funnel_id),
        "order": step.order,
        "name": step.name,
        "step_key": step.step_key,
        "is_active": step.is_active,
        "config": step.config,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


async def _require_funnel(session: AsyncSession, funnel_id: UUID) -> Funnel:
    result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    funnel = result.scalar_one_or_none()
    if funnel is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "not_found", "Funnel not found")
    return funnel


async def _require_step(session: AsyncSession, funnel_id: UUID, step_id: UUID) -> FunnelStep:
    result = await session.execute(
        select(FunnelStep).where(FunnelStep.id == step_id, FunnelStep.funnel_id == funnel_id)
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "not_found", "Step not found")
    return step


@router.get("", response_model=list[FunnelListItem])
async def list_funnels(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    return await list_funnels_with_stats(session, include_archived=include_archived)


@router.post("", response_model=FunnelRead, status_code=status.HTTP_201_CREATED)
async def create_funnel(
    data: FunnelCreate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    name = data.name.strip()
    if not name:
        raise _api_error(status.HTTP_400_BAD_REQUEST, "bad_request", "Funnel name is required")

    existing_name_result = await session.execute(select(Funnel.id).where(Funnel.name == name))
    if existing_name_result.scalar_one_or_none() is not None:
        raise _api_error(status.HTTP_409_CONFLICT, "conflict", "Resource already exists", {"field": "name"})

    entry_key = data.entry_key.strip() if data.entry_key else None
    if entry_key:
        existing_entry_result = await session.execute(select(Funnel.id).where(Funnel.entry_key == entry_key))
        if existing_entry_result.scalar_one_or_none() is not None:
            raise _api_error(
                status.HTTP_409_CONFLICT,
                "conflict",
                "Resource already exists",
                {"field": "entry_key"},
            )

    funnel = Funnel(
        name=name,
        entry_key=entry_key,
        is_active=True,
        is_archived=False,
        cross_entry_behavior=FunnelCrossEntryBehavior(data.cross_entry_behavior),
        notes=data.notes,
    )
    session.add(funnel)
    await session.commit()
    await session.refresh(funnel)
    return await get_funnel_with_stats(session, funnel.id)


@router.get("/{funnel_id}", response_model=FunnelRead)
async def get_funnel(
    funnel_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await get_funnel_with_stats(session, funnel_id)


@router.patch("/{funnel_id}", response_model=FunnelRead)
async def update_funnel(
    funnel_id: UUID,
    data: FunnelUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    funnel = await _require_funnel(session, funnel_id)

    if "name" in data.model_fields_set:
        name = data.name.strip() if data.name is not None else ""
        if not name:
            raise _api_error(status.HTTP_400_BAD_REQUEST, "bad_request", "Funnel name is required")
        if name != funnel.name:
            existing_name_result = await session.execute(
                select(Funnel.id).where(Funnel.name == name, Funnel.id != funnel.id)
            )
            if existing_name_result.scalar_one_or_none() is not None:
                raise _api_error(status.HTTP_409_CONFLICT, "conflict", "Resource already exists", {"field": "name"})
            funnel.name = name

    if "entry_key" in data.model_fields_set:
        entry_key = data.entry_key.strip() if data.entry_key else None
        if entry_key != funnel.entry_key:
            if entry_key:
                existing_entry_result = await session.execute(
                    select(Funnel.id).where(Funnel.entry_key == entry_key, Funnel.id != funnel.id)
                )
                if existing_entry_result.scalar_one_or_none() is not None:
                    raise _api_error(
                        status.HTTP_409_CONFLICT,
                        "conflict",
                        "Resource already exists",
                        {"field": "entry_key"},
                    )
            funnel.entry_key = entry_key

    if "is_active" in data.model_fields_set and data.is_active is not None:
        funnel.is_active = data.is_active
    if "is_archived" in data.model_fields_set and data.is_archived is not None:
        funnel.is_archived = data.is_archived
    if "cross_entry_behavior" in data.model_fields_set and data.cross_entry_behavior is not None:
        funnel.cross_entry_behavior = FunnelCrossEntryBehavior(data.cross_entry_behavior)
    if "notes" in data.model_fields_set:
        funnel.notes = data.notes

    await session.commit()
    return await get_funnel_with_stats(session, funnel.id)


@router.delete("/{funnel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_funnel(
    funnel_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    funnel = await _require_funnel(session, funnel_id)
    funnel.is_archived = True
    funnel.is_active = False
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{funnel_id}/restore", response_model=FunnelRead)
async def restore_funnel(
    funnel_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    funnel = await _require_funnel(session, funnel_id)
    funnel.is_archived = False
    funnel.is_active = True
    await session.commit()
    return await get_funnel_with_stats(session, funnel.id)


@router.post("/{funnel_id}/duplicate", response_model=FunnelRead, status_code=status.HTTP_201_CREATED)
async def duplicate_funnel(
    funnel_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    clone = await duplicate_funnel_with_steps(session, funnel_id)
    return await get_funnel_with_stats(session, clone.id)


@router.get("/{funnel_id}/steps", response_model=list[StepRead])
async def list_steps(
    funnel_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    await _require_funnel(session, funnel_id)
    result = await session.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id).order_by(FunnelStep.order.asc())
    )
    return [_serialize_step(step) for step in result.scalars().all()]


@router.post("/{funnel_id}/steps", response_model=StepRead, status_code=status.HTTP_201_CREATED)
async def create_step(
    funnel_id: UUID,
    data: StepCreate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _require_funnel(session, funnel_id)

    name = data.name.strip()
    if not name:
        raise _api_error(status.HTTP_400_BAD_REQUEST, "bad_request", "Step name is required")

    if not await ensure_unique_step_key(session, funnel_id, data.step_key):
        raise _api_error(status.HTTP_409_CONFLICT, "conflict", "Resource already exists", {"field": "step_key"})

    order = data.order if data.order is not None else await get_next_step_order(session, funnel_id)
    if data.order is not None:
        await session.execute(
            update(FunnelStep)
            .where(FunnelStep.funnel_id == funnel_id, FunnelStep.order >= order)
            .values(order=FunnelStep.order + 1)
        )

    step = FunnelStep(
        funnel_id=funnel_id,
        order=order,
        name=name,
        step_key=data.step_key,
        is_active=data.is_active,
        config=data.config.model_dump(mode="json"),
    )
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return _serialize_step(step)


@router.get("/{funnel_id}/steps/{step_id}", response_model=StepRead)
async def get_step(
    funnel_id: UUID,
    step_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _require_funnel(session, funnel_id)
    step = await _require_step(session, funnel_id, step_id)
    return _serialize_step(step)


@router.put("/{funnel_id}/steps/{step_id}", response_model=StepRead)
async def update_step(
    funnel_id: UUID,
    step_id: UUID,
    data: StepUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _require_funnel(session, funnel_id)
    step = await _require_step(session, funnel_id, step_id)

    name = data.name.strip()
    if not name:
        raise _api_error(status.HTTP_400_BAD_REQUEST, "bad_request", "Step name is required")

    if data.step_key != step.step_key:
        if not await ensure_unique_step_key(session, funnel_id, data.step_key, exclude_id=step.id):
            raise _api_error(status.HTTP_409_CONFLICT, "conflict", "Resource already exists", {"field": "step_key"})
        step.step_key = data.step_key

    step.name = name
    step.is_active = data.is_active
    step.config = data.config.model_dump(mode="json")

    await session.commit()
    await session.refresh(step)
    return _serialize_step(step)


@router.delete("/{funnel_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    funnel_id: UUID,
    step_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_funnel(session, funnel_id)
    step = await _require_step(session, funnel_id, step_id)

    if await has_active_users_on_step(session, step.id):
        raise _api_error(
            status.HTTP_409_CONFLICT,
            "conflict",
            "Step has active users",
            {"step_id": str(step.id)},
        )

    await session.execute(
        update(FunnelStep)
        .where(FunnelStep.funnel_id == funnel_id, FunnelStep.order > step.order)
        .values(order=FunnelStep.order - 1)
    )
    await session.delete(step)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{funnel_id}/steps/{step_id}/duplicate", response_model=StepRead, status_code=status.HTTP_201_CREATED)
async def duplicate_step(
    funnel_id: UUID,
    step_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _require_funnel(session, funnel_id)
    clone = await duplicate_step_in_funnel(session, funnel_id, step_id)
    return _serialize_step(clone)


@router.post("/{funnel_id}/steps/reorder", response_model=list[StepRead])
async def reorder_steps(
    funnel_id: UUID,
    data: StepReorder,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    await _require_funnel(session, funnel_id)
    steps = await reorder_funnel_steps(session, funnel_id, list(data.step_ids_in_order))
    return [_serialize_step(step) for step in steps]