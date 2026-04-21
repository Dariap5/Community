from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import SESSION_KEY, require_admin, verify_password
from app.admin.settings_crypto import SettingsCrypto
from app.config import get_settings
from app.db.models import (
    BotSetting,
    Funnel,
    FunnelStep,
    PaymentStatus,
    Product,
    Purchase,
    ScheduledTask,
    ScheduledTaskStatus,
    Track,
    User,
    UserFunnelState,
    UserTag,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
settings = get_settings()


def _assert_admin(request: Request) -> None:
    require_admin(request)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": ""},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    if username == settings.admin_username and verify_password(password):
        request.session[SESSION_KEY] = True
        return templates.TemplateResponse(
            request=request,
            name="admin/panel.html",
            context={"username": username, "technical_hint": _technical_hint()},
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": "Неверный логин или пароль"},
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse({"ok": True})


@router.get("", response_class=HTMLResponse)
async def panel_page(request: Request) -> HTMLResponse:
    _assert_admin(request)
    return templates.TemplateResponse(
        request=request,
        name="admin/panel.html",
        context={"username": settings.admin_username, "technical_hint": _technical_hint()},
    )


@router.get("/api/products")
async def products_list(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Product).order_by(Product.id.desc()))
    items = [
        {
            "id": str(p.id),
            "name": p.name,
            "price": float(p.price),
            "description": p.description,
            "photo_file_id": p.photo_file_id,
            "is_active": p.is_active,
            "payment_url": None,
            "access_type": None,
            "access_payload": None,
            "is_archived": not p.is_active,
        }
        for p in result.scalars().all()
    ]
    return {"items": items}


@router.post("/api/products")
async def product_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    product = Product(
        name=str(payload.get("name", "Новый продукт")),
        price=float(payload.get("price", 0)),
        description=payload.get("description"),
        photo_file_id=payload.get("photo_file_id"),
        is_active=bool(payload.get("is_active", True)),
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return {"id": product.id}


@router.patch("/api/products/{product_id}")
async def product_update(
    request: Request,
    product_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if "name" in payload:
        product.name = str(payload["name"])
    if "price" in payload:
        product.price = float(payload["price"])
    if "description" in payload:
        product.description = payload["description"]
    if "photo_file_id" in payload:
        product.photo_file_id = payload["photo_file_id"]
    if "is_active" in payload:
        product.is_active = bool(payload["is_active"])
    await session.commit()
    return {"ok": True}


@router.post("/api/products/{product_id}/archive")
async def product_archive(
    request: Request,
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    await session.commit()
    return {"ok": True}


@router.get("/api/tracks")
async def tracks_list(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Track).order_by(Track.id.asc()))
    items = [
        {
            "id": str(t.id),
            "title": t.name,
            "is_active": t.is_active,
            "messages_payload": (t.config or {}).get("messages_payload", []),
            "config": t.config,
        }
        for t in result.scalars().all()
    ]
    return {"items": items}


@router.post("/api/tracks")
async def track_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    track = Track(
        name=str(payload.get("title", "Новый трек")),
        is_active=bool(payload.get("is_active", True)),
        config={"messages_payload": payload.get("messages_payload", []), **(payload.get("config") or {})},
    )
    session.add(track)
    await session.commit()
    await session.refresh(track)
    return {"id": track.id}


@router.patch("/api/tracks/{track_id}")
async def track_update(
    request: Request,
    track_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Track).where(Track.id == track_id))
    track = result.scalar_one_or_none()
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")

    if "title" in payload:
        track.name = str(payload["title"])
    if "is_active" in payload:
        track.is_active = bool(payload["is_active"])
    if "messages_payload" in payload:
        track.config = {**(track.config or {}), "messages_payload": payload["messages_payload"]}
    if "config" in payload:
        track.config = payload["config"]

    await session.commit()
    return {"ok": True}


@router.delete("/api/tracks/{track_id}")
async def track_delete(
    request: Request,
    track_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Track).where(Track.id == track_id))
    track = result.scalar_one_or_none()
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")
    await session.delete(track)
    await session.commit()
    return {"ok": True}


@router.get("/api/users")
async def users_list(
    request: Request,
    q: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    step_id: int | None = Query(default=None),
    paid_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    query = (
        select(User, UserFunnelState)
        .outerjoin(UserFunnelState, UserFunnelState.user_id == User.telegram_id)
        .order_by(User.created_at.desc())
    )

    conditions = []
    if q:
        conditions.append(
            or_(
                User.first_name.ilike(f"%{q}%"),
                User.username.ilike(f"%{q}%"),
                func.cast(User.telegram_id, str).ilike(f"%{q}%"),
            )
        )

    if step_id is not None:
        conditions.append(UserFunnelState.current_step_id == step_id)

    if conditions:
        query = query.where(and_(*conditions))

    rows = list((await session.execute(query)).all())
    user_ids = [row[0].telegram_id for row in rows]

    if tag and user_ids:
        tag_rows = await session.execute(
            select(UserTag.user_id).where(UserTag.user_id.in_(user_ids), UserTag.tag == tag)
        )
        allowed = {item[0] for item in tag_rows.all()}
        rows = [row for row in rows if row[0].telegram_id in allowed]

    if paid_only and user_ids:
        paid_rows = await session.execute(
            select(Purchase.user_id)
            .where(Purchase.user_id.in_(user_ids), Purchase.status == PaymentStatus.paid)
            .distinct()
        )
        paid_set = {item[0] for item in paid_rows.all()}
        rows = [row for row in rows if row[0].telegram_id in paid_set]

    items = []
    for user, state in rows:
        tags_result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user.telegram_id))
        tags = [row[0] for row in tags_result.all()]
        items.append(
            {
                "id": user.telegram_id,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "username": user.username,
                "registered_at": user.created_at.isoformat(),
                "source_deeplink": user.source_deeplink,
                "current_step_id": state.current_step_id if state else None,
                "funnel_status": state.status.value if state else None,
                "tags": tags,
            }
        )

    return {"items": items}


@router.get("/api/users/{user_id}")
async def user_card(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    user_result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    tags_result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user_id))
    purchases_result = await session.execute(
        select(Purchase, Product)
        .join(Product, Product.id == Purchase.product_id)
        .where(Purchase.user_id == user_id)
        .order_by(Purchase.created_at.desc())
    )
    state_result = await session.execute(select(UserFunnelState).where(UserFunnelState.user_id == user_id))
    state = state_result.scalar_one_or_none()

    return {
        "user": {
            "id": user.telegram_id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "source_deeplink": user.source_deeplink,
            "registered_at": user.created_at.isoformat(),
        },
        "tags": [row[0] for row in tags_result.all()],
        "purchases": [
            {
                "id": purchase.id,
                "product": product.name,
                "status": purchase.status.value,
                "amount": float(purchase.amount),
                "paid_at": purchase.paid_at.isoformat() if purchase.paid_at else None,
            }
            for purchase, product in purchases_result.all()
        ],
        "history": [],
        "funnel_state": {
            "current_step_id": state.current_step_id if state else None,
            "status": state.status.value if state else None,
        },
    }


@router.post("/api/users/{user_id}/tags")
async def user_tag_add(
    request: Request,
    user_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    tag = str(payload.get("tag", "")).strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Empty tag")

    existing = await session.execute(select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag))
    if existing.scalar_one_or_none() is None:
        session.add(UserTag(user_id=user_id, tag=tag))
        await session.commit()
    return {"ok": True}


@router.delete("/api/users/{user_id}/tags/{tag}")
async def user_tag_remove(
    request: Request,
    user_id: int,
    tag: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag))
    user_tag = result.scalar_one_or_none()
    if user_tag is not None:
        await session.delete(user_tag)
        await session.commit()
    return {"ok": True}


@router.post("/api/users/{user_id}/move-step")
async def user_move_step(
    request: Request,
    user_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    target_step_id = int(payload["step_id"])
    state_result = await session.execute(select(UserFunnelState).where(UserFunnelState.user_id == user_id))
    state = state_result.scalar_one_or_none()
    if state is None:
        raise HTTPException(status_code=404, detail="User funnel state not found")

    state.current_step_id = target_step_id
    state.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.post("/api/users/{user_id}/message")
async def user_send_message(
    request: Request,
    user_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    user_result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text required")

    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="HTML")
    finally:
        await bot.session.close()

    return {"ok": True}


@router.post("/api/broadcasts/preview")
async def broadcast_preview(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    user_ids = await _segment_user_ids(session, payload.get("segment_tags", []), payload.get("segment_logic", "OR"))
    return {"audience_count": len(user_ids)}


@router.post("/api/broadcasts/send")
async def broadcast_send(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    tags = payload.get("segment_tags", [])
    logic = payload.get("segment_logic", "OR")
    user_ids = await _segment_user_ids(session, tags, logic)

    broadcast = Broadcast(
        title=str(payload.get("title", "Рассылка")),
        segment_logic=str(logic),
        segment_tags=tags,
        content_type=str(payload.get("content_type", "text")),
        content_text=payload.get("content_text"),
        content_file=payload.get("content_file"),
        buttons_payload=payload.get("buttons_payload", []),
        status="queued",
    )
    session.add(broadcast)
    await session.flush()

    for user_id in user_ids:
        session.add(BroadcastRecipient(broadcast_id=broadcast.id, user_id=user_id, delivery_status="pending"))

    session.add(
        ScheduledTask(
            user_id=user_ids[0] if user_ids else 0,
            task_type="broadcast_dispatch",
            payload={"broadcast_id": broadcast.id},
            execute_at=datetime.now(timezone.utc),
            status=ScheduledTaskStatus.pending,
        )
    )
    await session.commit()
    return {"ok": True, "broadcast_id": broadcast.id, "audience_count": len(user_ids)}


@router.get("/api/users/export")
async def users_export_csv(
    request: Request,
    tag: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    _assert_admin(request)
    query = select(User)
    rows = list((await session.execute(query)).scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["telegram_id", "first_name", "username", "registered_at", "source", "tags"])

    for user in rows:
        tags_result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user.telegram_id))
        tags = [row[0] for row in tags_result.all()]
        if tag and tag not in tags:
            continue
        writer.writerow(
            [
                user.telegram_id,
                user.first_name or "",
                user.username or "",
                user.created_at.isoformat(),
                user.source_deeplink or "",
                "|".join(tags),
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@router.get("/api/analytics")
async def analytics_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    funnels_result = await session.execute(select(Funnel).order_by(Funnel.created_at.asc(), Funnel.name.asc()))
    funnel_rows = []
    for funnel in funnels_result.scalars().all():
        steps_result = await session.execute(
            select(FunnelStep).where(FunnelStep.funnel_id == funnel.id).order_by(FunnelStep.order.asc())
        )
        steps = list(steps_result.scalars().all())
        step_data = []
        prev = None
        for step in steps:
            count_result = await session.execute(
                select(func.count(UserFunnelState.id)).where(UserFunnelState.current_step_id == step.id)
            )
            reached = int(count_result.scalar_one())
            conversion = None if prev in (None, 0) else round((reached / prev) * 100, 2)
            step_data.append({"step_id": str(step.id), "step_order": step.order, "reached": reached, "conversion": conversion})
            prev = reached

        funnel_rows.append({"funnel_id": str(funnel.id), "name": funnel.name, "steps": step_data})

    button_rows: list[dict] = []

    finance_result = await session.execute(
        select(
            Product.name,
            func.count(Purchase.id),
            func.coalesce(func.sum(Purchase.amount), 0),
            func.coalesce(func.avg(Purchase.amount), 0),
        )
        .join(Purchase, Purchase.product_id == Product.id)
        .where(Purchase.status == PaymentStatus.paid)
        .group_by(Product.name)
    )
    finance = [
        {
            "product": row[0],
            "purchases": int(row[1]),
            "revenue": float(row[2]),
            "avg_check": float(row[3]),
        }
        for row in finance_result.all()
    ]

    return {"funnels": funnel_rows, "buttons": button_rows, "finance": finance}


@router.get("/api/settings")
async def settings_get(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(BotSetting).order_by(BotSetting.key.asc()))
    items = []
    for row in result.scalars().all():
        value = row.value_text or ""
        if row.key.startswith("payment_") or row.key in {"bot_token"}:
            value = SettingsCrypto.decrypt(value)
        try:
            value_json = json.loads(value) if value else None
        except json.JSONDecodeError:
            value_json = None
        items.append({"key": row.key, "value_text": value, "value_json": value_json})
    return {"items": items}


@router.post("/api/settings")
async def setting_set(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    key = str(payload.get("key", "")).strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")

    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = BotSetting(key=key)
        session.add(setting)

    if "value_text" in payload:
        value = payload["value_text"]
        value_text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        if key.startswith("payment_") or key == "bot_token":
            value_text = SettingsCrypto.encrypt(value_text)
        setting.value_text = value_text

    if "value_json" in payload:
        value_json = payload["value_json"]
        value_text = json.dumps(value_json, ensure_ascii=False)
        if key.startswith("payment_") or key == "bot_token":
            value_text = SettingsCrypto.encrypt(value_text)
        setting.value_text = value_text

    await session.commit()
    return {"ok": True}


async def _segment_user_ids(session: AsyncSession, tags: list[str], logic: str) -> list[int]:
    users_result = await session.execute(select(User.id))
    all_user_ids = [row[0] for row in users_result.all()]
    if not tags:
        return all_user_ids

    tag_rows = await session.execute(select(UserTag.user_id, UserTag.tag).where(UserTag.tag.in_(tags)))
    user_to_tags: dict[int, set[str]] = {}
    for user_id, tag in tag_rows.all():
        user_to_tags.setdefault(user_id, set()).add(tag)

    wanted = []
    for user_id in all_user_ids:
        owned = user_to_tags.get(user_id, set())
        if logic == "AND" and set(tags).issubset(owned):
            wanted.append(user_id)
        if logic != "AND" and owned.intersection(tags):
            wanted.append(user_id)
    return wanted
def _technical_hint() -> str:
    return (
        "Изменения контента применяются только к новым отправкам. Уже отправленные сообщения Telegram изменить нельзя."
    )
