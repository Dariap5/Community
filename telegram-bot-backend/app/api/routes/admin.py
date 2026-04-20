from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
    Broadcast,
    BroadcastRecipient,
    ButtonClickStat,
    ButtonType,
    Funnel,
    FunnelStep,
    PaymentStatus,
    Product,
    Purchase,
    ScheduledTask,
    ScheduledTaskStatus,
    StepButton,
    StepMessage,
    User,
    UserActionLog,
    UserFunnelState,
    UserTag,
    CommunityTrack,
)
from app.db.session import get_db_session

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
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


@router.get("/api/funnels")
async def funnels_list(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    funnels_result = await session.execute(select(Funnel).order_by(Funnel.order_index.asc()))
    funnels = list(funnels_result.scalars().all())

    data = []
    for funnel in funnels:
        steps_result = await session.execute(
            select(FunnelStep).where(FunnelStep.funnel_id == funnel.id).order_by(FunnelStep.step_order.asc())
        )
        steps = list(steps_result.scalars().all())
        counts = []
        for step in steps:
            step_count_result = await session.execute(
                select(func.count(UserFunnelState.id)).where(UserFunnelState.current_step_id == step.id)
            )
            counts.append({"step_id": step.id, "step_order": step.step_order, "users": step_count_result.scalar_one()})

        data.append(
            {
                "id": funnel.id,
                "name": funnel.name,
                "is_enabled": funnel.is_enabled,
                "is_archived": funnel.is_archived,
                "step_counts": counts,
            }
        )

    return {"items": data}


@router.post("/api/funnels")
async def funnel_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    funnel = Funnel(
        name=str(payload.get("name", "Новая воронка")),
        is_enabled=bool(payload.get("is_enabled", True)),
        order_index=int(payload.get("order_index", 999)),
    )
    session.add(funnel)
    await session.commit()
    await session.refresh(funnel)
    return {"id": funnel.id}


@router.patch("/api/funnels/{funnel_id}")
async def funnel_update(
    request: Request,
    funnel_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    funnel = result.scalar_one_or_none()
    if funnel is None:
        raise HTTPException(status_code=404, detail="Funnel not found")

    if "name" in payload:
        funnel.name = str(payload["name"])
    if "is_enabled" in payload:
        funnel.is_enabled = bool(payload["is_enabled"])
    if "is_archived" in payload:
        funnel.is_archived = bool(payload["is_archived"])

    await session.commit()
    return {"ok": True}


@router.post("/api/funnels/{funnel_id}/copy")
async def funnel_copy(
    request: Request,
    funnel_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Funnel not found")

    clone = Funnel(name=f"{source.name} (copy)", is_enabled=False, order_index=source.order_index + 1)
    session.add(clone)
    await session.flush()

    steps_result = await session.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == source.id).order_by(FunnelStep.step_order.asc())
    )
    source_steps = list(steps_result.scalars().all())
    old_to_new: dict[int, int] = {}

    for step in source_steps:
        copied = FunnelStep(
            funnel_id=clone.id,
            step_order=step.step_order,
            step_key=step.step_key,
            internal_name=step.internal_name,
            is_enabled=step.is_enabled,
            delay_unit=step.delay_unit,
            delay_before_seconds=step.delay_before_seconds,
            trigger_conditions=step.trigger_conditions,
        )
        session.add(copied)
        await session.flush()
        old_to_new[step.id] = copied.id

    for step in source_steps:
        msg_result = await session.execute(
            select(StepMessage).where(StepMessage.step_id == step.id).order_by(StepMessage.message_order.asc())
        )
        for message in msg_result.scalars().all():
            session.add(
                StepMessage(
                    step_id=old_to_new[step.id],
                    message_order=message.message_order,
                    message_type=message.message_type,
                    content_text=message.content_text,
                    content_file=message.content_file,
                    caption=message.caption,
                    target_buttons_anchor=message.target_buttons_anchor,
                    parse_mode=message.parse_mode,
                    delay_after_seconds=message.delay_after_seconds,
                )
            )

        btn_result = await session.execute(select(StepButton).where(StepButton.step_id == step.id))
        for button in btn_result.scalars().all():
            session.add(
                StepButton(
                    step_id=old_to_new[step.id],
                    button_order=button.button_order,
                    text=button.text,
                    button_type=button.button_type,
                    value=button.value,
                    conditions=button.conditions,
                    is_enabled=button.is_enabled,
                )
            )

    await session.commit()
    return {"ok": True, "id": clone.id}


@router.post("/api/funnels/{funnel_id}/archive")
async def funnel_archive(
    request: Request,
    funnel_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    funnel = result.scalar_one_or_none()
    if funnel is None:
        raise HTTPException(status_code=404, detail="Funnel not found")
    funnel.is_archived = True
    funnel.is_enabled = False
    await session.commit()
    return {"ok": True}


@router.get("/api/funnels/{funnel_id}/steps")
async def steps_list(
    request: Request,
    funnel_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(
        select(FunnelStep).where(FunnelStep.funnel_id == funnel_id).order_by(FunnelStep.step_order.asc())
    )
    items = [
        {
            "id": step.id,
            "funnel_id": step.funnel_id,
            "step_order": step.step_order,
            "step_key": step.step_key,
            "internal_name": step.internal_name,
            "is_enabled": step.is_enabled,
            "delay_unit": step.delay_unit,
            "delay_before_seconds": step.delay_before_seconds,
            "trigger_conditions": step.trigger_conditions,
        }
        for step in result.scalars().all()
    ]
    return {"items": items}


@router.post("/api/steps")
async def step_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    funnel_id = int(payload["funnel_id"])
    funnel_result = await session.execute(select(Funnel).where(Funnel.id == funnel_id))
    if funnel_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Funnel not found")

    step = FunnelStep(
        funnel_id=funnel_id,
        step_order=int(payload.get("step_order", 1)),
        step_key=payload.get("step_key"),
        internal_name=payload.get("internal_name"),
        is_enabled=bool(payload.get("is_enabled", True)),
        delay_unit=str(payload.get("delay_unit", "seconds")),
        delay_before_seconds=int(payload.get("delay_before_seconds", 0)),
        trigger_conditions=payload.get("trigger_conditions", {}),
    )
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return {"id": step.id}


@router.get("/api/steps/{step_id}")
async def step_get(
    request: Request,
    step_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(FunnelStep).where(FunnelStep.id == step_id))
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    return {
        "id": step.id,
        "funnel_id": step.funnel_id,
        "step_order": step.step_order,
        "step_key": step.step_key,
        "internal_name": step.internal_name,
        "is_enabled": step.is_enabled,
        "delay_unit": step.delay_unit,
        "delay_before_seconds": step.delay_before_seconds,
        "trigger_conditions": step.trigger_conditions,
    }


@router.patch("/api/steps/{step_id}")
async def step_update(
    request: Request,
    step_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(FunnelStep).where(FunnelStep.id == step_id))
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    for field in [
        "step_key",
        "internal_name",
        "delay_unit",
        "delay_before_seconds",
        "trigger_conditions",
        "is_enabled",
        "step_order",
    ]:
        if field in payload:
            setattr(step, field, payload[field])

    await session.commit()
    return {"ok": True}


@router.delete("/api/steps/{step_id}")
async def step_delete(
    request: Request,
    step_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(FunnelStep).where(FunnelStep.id == step_id))
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    await session.delete(step)
    await session.commit()
    return {"ok": True}


@router.post("/api/steps/reorder")
async def steps_reorder(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    ids = payload.get("ids", [])
    for idx, step_id in enumerate(ids, start=1):
        result = await session.execute(select(FunnelStep).where(FunnelStep.id == int(step_id)))
        step = result.scalar_one_or_none()
        if step is not None:
            step.step_order = idx
    await session.commit()
    return {"ok": True}


@router.get("/api/steps/{step_id}/messages")
async def messages_list(
    request: Request,
    step_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    step_result = await session.execute(select(FunnelStep.id).where(FunnelStep.id == step_id))
    if step_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Step not found")

    result = await session.execute(
        select(StepMessage).where(StepMessage.step_id == step_id).order_by(StepMessage.message_order.asc())
    )
    items = [
        {
            "id": m.id,
            "step_id": m.step_id,
            "message_order": m.message_order,
            "message_type": m.message_type.value,
            "content_text": m.content_text,
            "content_file": m.content_file,
            "caption": m.caption,
            "parse_mode": m.parse_mode,
            "target_buttons_anchor": m.target_buttons_anchor,
            "delay_after_seconds": m.delay_after_seconds,
        }
        for m in result.scalars().all()
    ]
    return {"items": items}


@router.post("/api/messages")
async def message_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    step_id = int(payload["step_id"])
    step_result = await session.execute(select(FunnelStep.id).where(FunnelStep.id == step_id))
    if step_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Step not found")

    # Validate inputs
    message_type = _validate_message_type(payload.get("message_type", "text"))
    parse_mode = _validate_parse_mode(payload.get("parse_mode", "HTML"))
    delay_seconds = _validate_delay_seconds(int(payload.get("delay_after_seconds", 0)))

    message = StepMessage(
        step_id=step_id,
        message_order=int(payload.get("message_order", 1)),
        message_type=message_type,
        content_text=payload.get("content_text"),
        content_file=payload.get("content_file"),
        caption=payload.get("caption"),
        parse_mode=parse_mode,
        target_buttons_anchor=payload.get("target_buttons_anchor"),
        delay_after_seconds=delay_seconds,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return {"id": message.id}


@router.patch("/api/messages/{message_id}")
async def message_update(
    request: Request,
    message_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(StepMessage).where(StepMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    # Validate specific fields if they're being updated
    if "message_type" in payload:
        payload["message_type"] = _validate_message_type(payload["message_type"])
    if "parse_mode" in payload:
        payload["parse_mode"] = _validate_parse_mode(payload["parse_mode"])
    if "delay_after_seconds" in payload:
        payload["delay_after_seconds"] = _validate_delay_seconds(int(payload["delay_after_seconds"]))

    for field in [
        "message_order",
        "message_type",
        "content_text",
        "content_file",
        "caption",
        "parse_mode",
        "target_buttons_anchor",
        "delay_after_seconds",
    ]:
        if field in payload:
            setattr(message, field, payload[field])
    await session.commit()
    return {"ok": True}


@router.delete("/api/messages/{message_id}")
async def message_delete(
    request: Request,
    message_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(StepMessage).where(StepMessage.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await session.delete(message)
    await session.commit()
    return {"ok": True}


@router.get("/api/steps/{step_id}/buttons")
async def buttons_list(
    request: Request,
    step_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    step_result = await session.execute(select(FunnelStep.id).where(FunnelStep.id == step_id))
    if step_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Step not found")

    result = await session.execute(
        select(StepButton).where(StepButton.step_id == step_id).order_by(StepButton.button_order.asc(), StepButton.id.asc())
    )
    items = [
        {
            "id": b.id,
            "step_id": b.step_id,
            "button_order": b.button_order,
            "text": b.text,
            "button_type": b.button_type.value,
            "value": b.value,
            "conditions": b.conditions,
            "is_enabled": b.is_enabled,
        }
        for b in result.scalars().all()
    ]
    return {"items": items}


@router.post("/api/buttons")
async def button_create(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    step_id = int(payload["step_id"])
    step_result = await session.execute(select(FunnelStep.id).where(FunnelStep.id == step_id))
    if step_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Step not found")

    button = StepButton(
        step_id=step_id,
        button_order=int(payload.get("button_order", 999)),
        text=str(payload.get("text", "Кнопка")),
        button_type=payload.get("button_type", "url"),
        value=str(payload.get("value", "")),
        conditions=payload.get("conditions", {}),
        is_enabled=bool(payload.get("is_enabled", True)),
    )
    session.add(button)
    await session.commit()
    await session.refresh(button)
    return {"id": button.id}


@router.patch("/api/buttons/{button_id}")
async def button_update(
    request: Request,
    button_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(StepButton).where(StepButton.id == button_id))
    button = result.scalar_one_or_none()
    if button is None:
        raise HTTPException(status_code=404, detail="Button not found")
    for field in ["button_order", "text", "button_type", "value", "conditions", "is_enabled"]:
        if field in payload:
            setattr(button, field, payload[field])
    await session.commit()
    return {"ok": True}


@router.delete("/api/buttons/{button_id}")
async def button_delete(
    request: Request,
    button_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(StepButton).where(StepButton.id == button_id))
    button = result.scalar_one_or_none()
    if button is None:
        raise HTTPException(status_code=404, detail="Button not found")
    await session.delete(button)
    await session.commit()
    return {"ok": True}


@router.post("/api/messages/reorder")
async def messages_reorder(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    ids = payload.get("ids", [])
    for idx, message_id in enumerate(ids, start=1):
        result = await session.execute(select(StepMessage).where(StepMessage.id == int(message_id)))
        message = result.scalar_one_or_none()
        if message is not None:
            message.message_order = idx
    await session.commit()
    return {"ok": True}


@router.post("/api/buttons/reorder")
async def buttons_reorder(
    request: Request,
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    ids = payload.get("ids", [])
    for idx, button_id in enumerate(ids, start=1):
        result = await session.execute(select(StepButton).where(StepButton.id == int(button_id)))
        button = result.scalar_one_or_none()
        if button is not None:
            button.button_order = idx
    await session.commit()
    return {"ok": True}


@router.post("/api/steps/{step_id}/send-test")
async def send_test_step(
    request: Request,
    step_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    step_result = await session.execute(select(FunnelStep).where(FunnelStep.id == step_id))
    step = step_result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    admin_chat = await _setting_text(session, "admin_test_telegram_id", "")
    if not admin_chat:
        raise HTTPException(status_code=400, detail="Set admin_test_telegram_id in Settings")

    # Load messages and buttons for this step
    messages_result = await session.execute(
        select(StepMessage).where(StepMessage.step_id == step_id).order_by(StepMessage.message_order.asc())
    )
    messages = list(messages_result.scalars().all())

    buttons_result = await session.execute(
        select(StepButton).where(StepButton.step_id == step_id).order_by(StepButton.button_order.asc())
    )
    buttons = list(buttons_result.scalars().all())

    # Build keyboard once (matches production behavior)
    keyboard = _build_test_keyboard(buttons)

    bot = Bot(token=settings.bot_token)
    try:
        for msg in messages:
            parse_mode = msg.parse_mode or "HTML"

            if msg.message_type.value == "text":
                await bot.send_message(
                    chat_id=int(admin_chat),
                    text=msg.content_text or "",
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            elif msg.message_type.value == "photo" and msg.content_file:
                await bot.send_photo(
                    chat_id=int(admin_chat),
                    photo=msg.content_file,
                    caption=msg.caption or "",
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            elif msg.message_type.value == "document" and msg.content_file:
                await bot.send_document(
                    chat_id=int(admin_chat),
                    document=msg.content_file,
                    caption=msg.caption or "",
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            elif msg.message_type.value == "video" and msg.content_file:
                await bot.send_video(
                    chat_id=int(admin_chat),
                    video=msg.content_file,
                    caption=msg.caption or "",
                    parse_mode=parse_mode,
                    reply_markup=keyboard,
                )
            elif msg.message_type.value == "video_note" and msg.content_file:
                # video_note doesn't support caption or reply_markup
                await bot.send_video_note(
                    chat_id=int(admin_chat),
                    video_note=msg.content_file,
                )
            elif msg.message_type.value == "voice" and msg.content_file:
                # voice supports caption but not reply_markup
                await bot.send_voice(
                    chat_id=int(admin_chat),
                    voice=msg.content_file,
                    caption=msg.caption or "",
                    parse_mode=parse_mode,
                )
    finally:
        await bot.session.close()

    return {"ok": True}


@router.get("/api/products")
async def products_list(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(Product).order_by(Product.id.desc()))
    items = [
        {
            "id": p.id,
            "name": p.name,
            "price": float(p.price),
            "description": p.description,
            "photo_file_id": p.photo_file_id,
            "payment_url": p.payment_url,
            "access_type": p.access_type,
            "access_payload": p.access_payload,
            "is_active": p.is_active,
            "is_archived": p.is_archived,
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
        payment_url=payload.get("payment_url"),
        access_type=str(payload.get("access_type", "text")),
        access_payload=str(payload.get("access_payload", "")),
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

    for field in [
        "name",
        "price",
        "description",
        "photo_file_id",
        "payment_url",
        "access_type",
        "access_payload",
        "is_active",
        "is_archived",
    ]:
        if field in payload:
            setattr(product, field, payload[field])
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
    product.is_archived = True
    product.is_active = False
    await session.commit()
    return {"ok": True}


@router.get("/api/tracks")
async def tracks_list(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(CommunityTrack).order_by(CommunityTrack.id.asc()))
    items = [
        {
            "id": t.id,
            "title": t.title,
            "is_active": t.is_active,
            "messages_payload": t.messages_payload,
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
    track = CommunityTrack(
        title=str(payload.get("title", "Новый трек")),
        is_active=bool(payload.get("is_active", True)),
        messages_payload=payload.get("messages_payload", []),
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
    result = await session.execute(select(CommunityTrack).where(CommunityTrack.id == track_id))
    track = result.scalar_one_or_none()
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")

    for field in ["title", "is_active", "messages_payload"]:
        if field in payload:
            setattr(track, field, payload[field])

    await session.commit()
    return {"ok": True}


@router.delete("/api/tracks/{track_id}")
async def track_delete(
    request: Request,
    track_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _assert_admin(request)
    result = await session.execute(select(CommunityTrack).where(CommunityTrack.id == track_id))
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
        .outerjoin(UserFunnelState, UserFunnelState.user_id == User.id)
        .order_by(User.created_at.desc())
    )

    conditions = []
    if q:
        conditions.append(
            or_(
                User.first_name.ilike(f"%{q}%"),
                User.username.ilike(f"%{q}%"),
            )
        )

    if step_id is not None:
        conditions.append(UserFunnelState.current_step_id == step_id)

    if conditions:
        query = query.where(and_(*conditions))

    rows = list((await session.execute(query)).all())
    user_ids = [row[0].id for row in rows]

    if tag and user_ids:
        tag_rows = await session.execute(
            select(UserTag.user_id).where(UserTag.user_id.in_(user_ids), UserTag.tag == tag)
        )
        allowed = {item[0] for item in tag_rows.all()}
        rows = [row for row in rows if row[0].id in allowed]

    if paid_only and user_ids:
        paid_rows = await session.execute(
            select(Purchase.user_id)
            .where(Purchase.user_id.in_(user_ids), Purchase.payment_status == PaymentStatus.paid)
            .distinct()
        )
        paid_set = {item[0] for item in paid_rows.all()}
        rows = [row for row in rows if row[0].id in paid_set]

    items = []
    for user, state in rows:
        tags_result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user.id))
        tags = [row[0] for row in tags_result.all()]
        items.append(
            {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "username": user.username,
                "registered_at": user.registered_at.isoformat(),
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
    user_result = await session.execute(select(User).where(User.id == user_id))
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
    actions_result = await session.execute(
        select(UserActionLog).where(UserActionLog.user_id == user_id).order_by(UserActionLog.created_at.desc())
    )
    state_result = await session.execute(select(UserFunnelState).where(UserFunnelState.user_id == user_id))
    state = state_result.scalar_one_or_none()

    return {
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "source_deeplink": user.source_deeplink,
            "registered_at": user.registered_at.isoformat(),
        },
        "tags": [row[0] for row in tags_result.all()],
        "purchases": [
            {
                "id": purchase.id,
                "product": product.name,
                "status": purchase.payment_status.value,
                "amount": float(purchase.amount),
                "paid_at": purchase.paid_at.isoformat() if purchase.paid_at else None,
            }
            for purchase, product in purchases_result.all()
        ],
        "history": [
            {
                "action_type": item.action_type,
                "funnel_step_id": item.funnel_step_id,
                "payload": item.payload,
                "created_at": item.created_at.isoformat(),
            }
            for item in actions_result.scalars().all()
        ],
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
    state.last_step_at = datetime.now(timezone.utc)
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
    user_result = await session.execute(select(User).where(User.id == user_id))
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
            run_at=datetime.now(timezone.utc),
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
        tags_result = await session.execute(select(UserTag.tag).where(UserTag.user_id == user.id))
        tags = [row[0] for row in tags_result.all()]
        if tag and tag not in tags:
            continue
        writer.writerow(
            [
                user.telegram_id,
                user.first_name or "",
                user.username or "",
                user.registered_at.isoformat(),
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
    funnels_result = await session.execute(select(Funnel).order_by(Funnel.order_index.asc()))
    funnel_rows = []
    for funnel in funnels_result.scalars().all():
        steps_result = await session.execute(
            select(FunnelStep).where(FunnelStep.funnel_id == funnel.id).order_by(FunnelStep.step_order.asc())
        )
        steps = list(steps_result.scalars().all())
        step_data = []
        prev = None
        for step in steps:
            count_result = await session.execute(
                select(func.count(UserActionLog.id)).where(
                    UserActionLog.funnel_step_id == step.id,
                    UserActionLog.action_type == "step_delivered",
                )
            )
            reached = int(count_result.scalar_one())
            conversion = None if prev in (None, 0) else round((reached / prev) * 100, 2)
            step_data.append({"step_id": step.id, "step_order": step.step_order, "reached": reached, "conversion": conversion})
            prev = reached

        funnel_rows.append({"funnel_id": funnel.id, "name": funnel.name, "steps": step_data})

    button_rows_result = await session.execute(
        select(
            StepButton.id,
            StepButton.text,
            func.count(ButtonClickStat.id).label("clicks"),
        )
        .outerjoin(ButtonClickStat, ButtonClickStat.step_button_id == StepButton.id)
        .group_by(StepButton.id)
        .order_by(StepButton.id.asc())
    )
    button_rows = [
        {"button_id": row[0], "text": row[1], "clicks": int(row[2])}
        for row in button_rows_result.all()
    ]

    finance_result = await session.execute(
        select(
            Product.name,
            func.count(Purchase.id),
            func.coalesce(func.sum(Purchase.amount), 0),
            func.coalesce(func.avg(Purchase.amount), 0),
        )
        .join(Purchase, Purchase.product_id == Product.id)
        .where(Purchase.payment_status == PaymentStatus.paid)
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
        items.append({"key": row.key, "value_text": value, "value_json": row.value_json})
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
        value_text = str(payload["value_text"])
        if key.startswith("payment_") or key == "bot_token":
            value_text = SettingsCrypto.encrypt(value_text)
        setting.value_text = value_text

    if "value_json" in payload:
        setting.value_json = payload["value_json"]

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


def _build_test_keyboard(buttons: list[StepButton]) -> InlineKeyboardMarkup | None:
    """Build keyboard for test message (admin sees all buttons, no tag filtering)."""
    active_buttons = sorted((b for b in buttons if b.is_enabled), key=lambda item: item.button_order)
    if not active_buttons:
        return None

    row = []
    for button in active_buttons:
        if button.button_type == ButtonType.url:
            row.append(InlineKeyboardButton(text=button.text, url=button.value))
        elif button.button_type == ButtonType.callback:
            row.append(InlineKeyboardButton(text=button.text, callback_data=button.value))
        elif button.button_type == ButtonType.payment:
            row.append(InlineKeyboardButton(text=button.text, callback_data=f"pay:{button.value}"))

    return InlineKeyboardMarkup(inline_keyboard=[row]) if row else None


def _validate_message_type(message_type: str) -> str:
    """Validate message type and raise HTTPException if invalid."""
    valid_types = {"text", "photo", "document", "video", "video_note", "voice"}
    if message_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid message_type '{message_type}'. Valid types: {', '.join(sorted(valid_types))}",
        )
    return message_type


def _validate_parse_mode(parse_mode: str) -> str:
    """Validate parse mode."""
    valid_modes = {"HTML", "Markdown", "MarkdownV2"}
    mode = (parse_mode or "HTML").upper()
    if mode not in valid_modes and mode != "HTML":
        # Default to HTML if invalid
        return "HTML"
    return mode


def _validate_delay_seconds(delay: int) -> int:
    """Validate delay_after_seconds is non-negative."""
    if delay < 0:
        raise HTTPException(status_code=400, detail="delay_after_seconds cannot be negative")
    return delay


async def _setting_text(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None or setting.value_text is None:
        return default
    return setting.value_text


def _technical_hint() -> str:
    return (
        "Изменения контента применяются только к новым отправкам. Уже отправленные сообщения Telegram изменить нельзя."
    )
