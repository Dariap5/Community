from __future__ import annotations

from copy import deepcopy
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Funnel, FunnelStatus, FunnelStep, UserFunnelState
from app.schemas.step_config import StepConfig


def _api_error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": details})


def _clone_config_with_new_ids(value):
    if isinstance(value, dict):
        cloned: dict = {}
        for key, item in value.items():
            if key == "id":
                cloned[key] = str(uuid4())
            else:
                cloned[key] = _clone_config_with_new_ids(item)
        return cloned
    if isinstance(value, list):
        return [_clone_config_with_new_ids(item) for item in value]
    return value


def _step_payload(step: FunnelStep, *, summary: dict | None = None) -> dict:
    payload = {
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
    if summary:
        payload.update(summary)
    return payload


def _funnel_payload(
    funnel: Funnel,
    *,
    steps_count: int,
    active_users_count: int,
    steps: list[dict] | None = None,
) -> dict:
    payload = {
        "id": str(funnel.id),
        "name": funnel.name,
        "entry_key": funnel.entry_key,
        "is_active": funnel.is_active,
        "is_archived": funnel.is_archived,
        "cross_entry_behavior": getattr(funnel.cross_entry_behavior, "value", funnel.cross_entry_behavior),
        "notes": funnel.notes,
        "created_at": funnel.created_at,
        "updated_at": funnel.updated_at,
        "steps_count": steps_count,
        "active_users_count": active_users_count,
        "steps": steps or [],
    }
    return payload


def _hours_from_delay(delay) -> float:
    unit_hours = {"seconds": 1 / 3600, "minutes": 1 / 60, "hours": 1, "days": 24}
    return float(delay.value) * unit_hours[delay.unit]


async def compute_step_summary(step: FunnelStep) -> dict:
    config = StepConfig.model_validate(step.config or {})
    messages_count = sum(1 for block in config.blocks if getattr(block, "type", None) != "buttons")
    buttons_count = sum(len(block.buttons) for block in config.blocks if getattr(block, "type", None) == "buttons")
    delay_before_hours = _hours_from_delay(config.delay_before)
    return {
        "messages_count": messages_count,
        "buttons_count": buttons_count,
        "delay_before_hours": delay_before_hours,
    }


async def get_next_step_order(db: AsyncSession, funnel_id: UUID) -> int:
    result = await db.execute(select(func.coalesce(func.max(FunnelStep.order), 0)).where(FunnelStep.funnel_id == funnel_id))
    return int(result.scalar_one()) + 1


async def ensure_unique_step_key(
    db: AsyncSession,
    funnel_id: UUID,
    step_key: str,
    exclude_id: UUID | None = None,
) -> bool:
    query = select(FunnelStep.id).where(FunnelStep.funnel_id == funnel_id, FunnelStep.step_key == step_key)
    if exclude_id is not None:
        query = query.where(FunnelStep.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is None


async def has_active_users_on_step(db: AsyncSession, step_id: UUID) -> bool:
    result = await db.execute(
        select(func.count(UserFunnelState.id)).where(
            UserFunnelState.current_step_id == step_id,
            UserFunnelState.status == FunnelStatus.active,
        )
    )
    return int(result.scalar_one()) > 0


async def _next_copy_step_key(db: AsyncSession, funnel_id: UUID, base_key: str) -> str:
    candidate_number = 1
    while True:
        candidate = f"{base_key}_copy_{candidate_number}"
        if await ensure_unique_step_key(db, funnel_id, candidate):
            return candidate
        candidate_number += 1


async def _ensure_unique_funnel_name(db: AsyncSession, base_name: str) -> str:
    candidate = base_name.strip() or "Новая воронка"
    suffix = 2
    while True:
        result = await db.execute(select(Funnel.id).where(Funnel.name == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_name} {suffix}"
        suffix += 1


async def _ensure_unique_funnel_entry_key(db: AsyncSession, entry_key: str | None, *, exclude_id: UUID | None = None) -> str | None:
    if entry_key is None:
        return None

    candidate = entry_key.strip()
    if not candidate:
        return None

    query = select(Funnel.id).where(Funnel.entry_key == candidate)
    if exclude_id is not None:
        query = query.where(Funnel.id != exclude_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is None:
        return candidate
    raise _api_error(status.HTTP_409_CONFLICT, "conflict", "Resource already exists", {"field": "entry_key"})


async def get_funnel_with_stats(db: AsyncSession, funnel_id: UUID) -> dict:
    funnel_result = await db.execute(select(Funnel).where(Funnel.id == funnel_id))
    funnel = funnel_result.scalar_one_or_none()
    if funnel is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "not_found", "Funnel not found")

    active_users_result = await db.execute(
        select(func.count(UserFunnelState.id)).where(
            UserFunnelState.funnel_id == funnel_id,
            UserFunnelState.status == FunnelStatus.active,
        )
    )
    active_users_count = int(active_users_result.scalar_one())

    steps_result = await db.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id).order_by(FunnelStep.order.asc())
    )
    steps = list(steps_result.scalars().all())
    summaries: list[dict] = []
    for step in steps:
        summary = await compute_step_summary(step)
        summaries.append(
            {
                "id": str(step.id),
                "order": step.order,
                "name": step.name,
                "step_key": step.step_key,
                "is_active": step.is_active,
                **summary,
            }
        )

    return _funnel_payload(
        funnel,
        steps_count=len(steps),
        active_users_count=active_users_count,
        steps=summaries,
    )


async def list_funnels_with_stats(db: AsyncSession, *, include_archived: bool = False) -> list[dict]:
    query = select(Funnel).order_by(Funnel.created_at.asc(), Funnel.name.asc())
    if not include_archived:
        query = query.where(Funnel.is_archived.is_(False))
    funnels = list((await db.execute(query)).scalars().all())
    if not funnels:
        return []

    funnel_ids = [funnel.id for funnel in funnels]

    step_counts_result = await db.execute(
        select(FunnelStep.funnel_id, func.count(FunnelStep.id))
        .where(FunnelStep.funnel_id.in_(funnel_ids))
        .group_by(FunnelStep.funnel_id)
    )
    step_counts = {funnel_id: int(count) for funnel_id, count in step_counts_result.all()}

    active_users_result = await db.execute(
        select(UserFunnelState.funnel_id, func.count(UserFunnelState.id))
        .where(
            UserFunnelState.funnel_id.in_(funnel_ids),
            UserFunnelState.status == FunnelStatus.active,
        )
        .group_by(UserFunnelState.funnel_id)
    )
    active_users_counts = {funnel_id: int(count) for funnel_id, count in active_users_result.all()}

    return [
        {
            "id": str(funnel.id),
            "name": funnel.name,
            "entry_key": funnel.entry_key,
            "is_active": funnel.is_active,
            "is_archived": funnel.is_archived,
            "steps_count": step_counts.get(funnel.id, 0),
            "active_users_count": active_users_counts.get(funnel.id, 0),
        }
        for funnel in funnels
    ]


async def duplicate_funnel_with_steps(db: AsyncSession, funnel_id: UUID) -> Funnel:
    source_result = await db.execute(select(Funnel).where(Funnel.id == funnel_id))
    source = source_result.scalar_one_or_none()
    if source is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "not_found", "Funnel not found")

    clone = Funnel(
        name=await _ensure_unique_funnel_name(db, f"{source.name} (копия)"),
        entry_key=None,
        is_active=False,
        is_archived=False,
        cross_entry_behavior=source.cross_entry_behavior,
        notes=source.notes,
    )
    db.add(clone)
    await db.flush()

    steps_result = await db.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == source.id).order_by(FunnelStep.order.asc())
    )
    for step in steps_result.scalars().all():
        step_copy = FunnelStep(
            funnel_id=clone.id,
            order=step.order,
            name=step.name,
            step_key=await _next_copy_step_key(db, clone.id, step.step_key),
            is_active=step.is_active,
            config=_clone_config_with_new_ids(deepcopy(step.config or {})),
        )
        db.add(step_copy)

    await db.commit()
    await db.refresh(clone)
    return clone


async def duplicate_step_in_funnel(db: AsyncSession, funnel_id: UUID, step_id: UUID) -> FunnelStep:
    source_result = await db.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id, FunnelStep.id == step_id)
    )
    source = source_result.scalar_one_or_none()
    if source is None:
        raise _api_error(status.HTTP_404_NOT_FOUND, "not_found", "Step not found")

    await db.execute(
        update(FunnelStep)
        .where(FunnelStep.funnel_id == funnel_id, FunnelStep.order > source.order)
        .values(order=FunnelStep.order + 1)
    )

    clone = FunnelStep(
        funnel_id=funnel_id,
        order=source.order + 1,
        name=f"{source.name} (копия)",
        step_key=await _next_copy_step_key(db, funnel_id, source.step_key),
        is_active=source.is_active,
        config=_clone_config_with_new_ids(deepcopy(source.config or {})),
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return clone


async def reorder_funnel_steps(db: AsyncSession, funnel_id: UUID, ordered_ids: list[UUID]) -> list[FunnelStep]:
    steps_result = await db.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id).order_by(FunnelStep.order.asc())
    )
    current_steps = list(steps_result.scalars().all())
    current_ids = [step.id for step in current_steps]

    if len(ordered_ids) != len(current_steps):
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "bad_request",
            "Step count does not match",
            {"expected": len(current_steps), "received": len(ordered_ids)},
        )

    if len(set(ordered_ids)) != len(ordered_ids):
        raise _api_error(status.HTTP_400_BAD_REQUEST, "bad_request", "Duplicate step ids in reorder payload")

    if set(ordered_ids) != set(current_ids):
        raise _api_error(
            status.HTTP_400_BAD_REQUEST,
            "bad_request",
            "Step ids do not match funnel steps",
        )

    ordering = {step_id: index for index, step_id in enumerate(ordered_ids, start=1)}
    await db.execute(
        update(FunnelStep)
        .where(FunnelStep.funnel_id == funnel_id, FunnelStep.id.in_(ordered_ids))
        .values(order=case(ordering, value=FunnelStep.id))
    )
    await db.commit()

    refreshed = await db.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id).order_by(FunnelStep.order.asc())
    )
    return list(refreshed.scalars().all())