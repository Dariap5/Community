from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db.models import (
    Funnel,
    FunnelCrossEntryBehavior,
    FunnelStatus,
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
from app.funnels.condition_checker import should_execute_step
from app.funnels.engine import FunnelEngine, THRESHOLD_INLINE_DELAY_SECONDS
from app.funnels.keyboard_builder import build_keyboard_for_step
from app.schemas.step_config import StepConfig, TriggerCondition


@dataclass(slots=True)
class FakeBot:
    messages: list[dict]

    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> SimpleNamespace:
        return self._record("message", chat_id=chat_id, text=text, **kwargs)

    async def send_photo(self, chat_id: int, photo: str, **kwargs) -> SimpleNamespace:
        return self._record("photo", chat_id=chat_id, photo=photo, **kwargs)

    async def send_document(self, chat_id: int, document: str, **kwargs) -> SimpleNamespace:
        return self._record("document", chat_id=chat_id, document=document, **kwargs)

    async def send_video(self, chat_id: int, video: str, **kwargs) -> SimpleNamespace:
        return self._record("video", chat_id=chat_id, video=video, **kwargs)

    async def send_video_note(self, chat_id: int, video_note: str, **kwargs) -> SimpleNamespace:
        return self._record("video_note", chat_id=chat_id, video_note=video_note, **kwargs)

    async def send_voice(self, chat_id: int, voice: str, **kwargs) -> SimpleNamespace:
        return self._record("voice", chat_id=chat_id, voice=voice, **kwargs)

    def _record(self, kind: str, **payload) -> SimpleNamespace:
        event = {"kind": kind, **payload}
        self.messages.append(event)
        return SimpleNamespace(message_id=len(self.messages))


@asynccontextmanager
async def _db_session():
    engine = create_async_engine(get_settings().postgres_dsn, poolclass=NullPool, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as db:
        try:
            yield db
        finally:
            await engine.dispose()


def _build_config(
    message_text: str,
    *,
    buttons: list[dict] | None = None,
    delay_before_seconds: int = 0,
    delay_after_seconds: int = 0,
    trigger_type: str = "always",
    trigger_tags: list[str] | None = None,
    wait_for_payment: bool = False,
    after_step: dict | None = None,
) -> StepConfig:
    blocks: list[dict] = [
        {
            "type": "text",
            "content_text": message_text,
            "delay_after": delay_after_seconds,
        }
    ]
    if buttons is not None:
        blocks.append({"type": "buttons", "buttons": buttons})

    return StepConfig(
        delay_before={"value": delay_before_seconds, "unit": "seconds"},
        trigger_condition={"type": trigger_type, "tags": trigger_tags or []},
        wait_for_payment=wait_for_payment,
        blocks=blocks,
        after_step=after_step or {},
    )


async def _create_user(db, *, telegram_id: int | None = None) -> User:
    user = User(
        telegram_id=telegram_id or (900000000000 + uuid4().int % 1_000_000_000),
        username=f"pytest_{uuid4().hex[:8]}",
        first_name="Pytest",
        last_name="Bot",
        source_deeplink="pytest",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_funnel(
    db,
    *,
    name: str | None = None,
    entry_key: str | None = None,
    cross_entry_behavior: FunnelCrossEntryBehavior = FunnelCrossEntryBehavior.allow,
    is_active: bool = True,
    is_archived: bool = False,
) -> Funnel:
    funnel = Funnel(
        name=name or f"Funnel {uuid4().hex[:8]}",
        entry_key=entry_key,
        cross_entry_behavior=cross_entry_behavior,
        is_active=is_active,
        is_archived=is_archived,
    )
    db.add(funnel)
    await db.commit()
    await db.refresh(funnel)
    return funnel


async def _create_step(
    db,
    funnel: Funnel,
    *,
    order: int,
    step_key: str | None = None,
    name: str | None = None,
    config: StepConfig,
    is_active: bool = True,
) -> FunnelStep:
    step = FunnelStep(
        funnel_id=funnel.id,
        order=order,
        name=name or f"Step {order} {uuid4().hex[:6]}",
        step_key=step_key or f"step_{order}_{uuid4().hex[:8]}",
        is_active=is_active,
        config=config.model_dump(mode="json"),
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def _create_product(db, *, name: str | None = None, price: Decimal | float = Decimal("490.00")) -> Product:
    product = Product(
        name=name or f"Product {uuid4().hex[:8]}",
        price=price,
        description="pytest",
        photo_file_id=None,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _cleanup(db, *, user_ids=(), funnel_ids=(), product_ids=(), track_ids=()) -> None:
    if product_ids:
        await db.execute(delete(Product).where(Product.id.in_(list(product_ids))))
    if funnel_ids:
        await db.execute(delete(FunnelStep).where(FunnelStep.funnel_id.in_(list(funnel_ids))))
        await db.execute(delete(Funnel).where(Funnel.id.in_(list(funnel_ids))))
    if track_ids:
        await db.execute(delete(Track).where(Track.id.in_(list(track_ids))))
    if user_ids:
        await db.execute(delete(User).where(User.telegram_id.in_(list(user_ids))))
    await db.commit()


def _callback_button_id(step: FunnelStep) -> UUID:
    config = StepConfig.model_validate(step.config or {})
    button_group = next(block for block in config.blocks if getattr(block, "type", None) == "buttons")
    return button_group.buttons[0].id


def test_step_config_parses_button_actions() -> None:
    config = _build_config(
        "Hello",
        buttons=[
            {"text": "Go", "action": {"type": "url", "value": "https://example.com"}},
            {"text": "Tag", "action": {"type": "add_tag", "value": "vip"}},
        ],
    )

    assert config.blocks[0].type == "text"
    assert config.blocks[1].type == "buttons"
    assert config.blocks[1].buttons[0].action.type == "url"
    assert config.blocks[1].buttons[1].action.type == "add_tag"


def test_keyboard_visibility_filters_buttons() -> None:
    config = _build_config(
        "Hello",
        buttons=[
            {
                "text": "VIP",
                "action": {"type": "url", "value": "https://example.com/vip"},
                "visible_if": {"has_tags": ["vip"]},
            },
            {
                "text": "Open",
                "action": {"type": "url", "value": "https://example.com/open"},
            },
        ],
    )

    keyboard_for_guest = build_keyboard_for_step(config, uuid4(), user_tags=set())
    keyboard_for_vip = build_keyboard_for_step(config, uuid4(), user_tags={"vip"})

    assert keyboard_for_guest is not None
    assert keyboard_for_guest.inline_keyboard[0][0].text == "Open"
    assert keyboard_for_guest.inline_keyboard[0][0].url == "https://example.com/open"
    assert keyboard_for_vip is not None
    assert len(keyboard_for_vip.inline_keyboard) == 2


def test_trigger_condition_helpers() -> None:
    assert should_execute_step(TriggerCondition(type="always"), set()) is True
    assert should_execute_step(TriggerCondition(type="has_tags", tags=["paid"]), {"paid"}) is True
    assert should_execute_step(TriggerCondition(type="has_tags", tags=["paid"]), set()) is False
    assert should_execute_step(TriggerCondition(type="not_has_tags", tags=["blocked"]), set()) is True


@pytest.mark.asyncio
async def test_start_same_funnel_is_idempotent() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"same_{uuid4().hex[:8]}")
        first_step = await _create_step(
            db,
            funnel,
            order=1,
            step_key=f"same_{uuid4().hex[:8]}",
            config=_build_config("Step 1", wait_for_payment=True),
        )

        try:
            state_1 = await engine.start_funnel(user, funnel)
            state_2 = await engine.start_funnel(user, funnel)

            assert state_1 is not None
            assert state_2 is not None
            assert state_1.id == state_2.id
            assert len(fake_bot.messages) == 1

            active_count = await db.scalar(
                select(func.count(UserFunnelState.id)).where(
                    UserFunnelState.user_id == user.telegram_id,
                    UserFunnelState.funnel_id == funnel.id,
                    UserFunnelState.status == FunnelStatus.active,
                )
            )
            assert int(active_count or 0) == 1
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_cross_entry_deny_blocks_start() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel_a = await _create_funnel(db, entry_key=f"a_{uuid4().hex[:8]}")
        funnel_b = await _create_funnel(
            db,
            entry_key=f"b_{uuid4().hex[:8]}",
            cross_entry_behavior=FunnelCrossEntryBehavior.deny,
        )
        await _create_step(db, funnel_a, order=1, config=_build_config("A", wait_for_payment=True))
        await _create_step(db, funnel_b, order=1, config=_build_config("B", wait_for_payment=True))

        try:
            first_state = await engine.start_funnel(user, funnel_a)
            second_state = await engine.start_funnel(user, funnel_b)

            assert first_state is not None
            assert second_state is None
            assert len(fake_bot.messages) == 1

            active_funnels = await db.execute(
                select(UserFunnelState.funnel_id).where(
                    UserFunnelState.user_id == user.telegram_id,
                    UserFunnelState.status == FunnelStatus.active,
                )
            )
            assert [row[0] for row in active_funnels.all()] == [funnel_a.id]
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel_a.id, funnel_b.id])


@pytest.mark.asyncio
async def test_short_delay_uses_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"short_{uuid4().hex[:8]}")
        await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config("Short delay", delay_before_seconds=5, wait_for_payment=True),
        )

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("app.funnels.engine.asyncio.sleep", fake_sleep)

        try:
            await engine.start_funnel(user, funnel)
            assert sleep_calls == [5]
            assert len(fake_bot.messages) == 1
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_long_delay_creates_scheduled_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"long_{uuid4().hex[:8]}")
        step = await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config(
                "Long delay",
                delay_before_seconds=THRESHOLD_INLINE_DELAY_SECONDS + 10,
                wait_for_payment=True,
            ),
        )

        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("app.funnels.engine.asyncio.sleep", fake_sleep)

        try:
            await engine.start_funnel(user, funnel)

            assert sleep_calls == []
            assert len(fake_bot.messages) == 0

            tasks = list(
                (
                    await db.execute(
                        select(ScheduledTask).where(
                            ScheduledTask.user_id == user.telegram_id,
                            ScheduledTask.task_type == "execute_step",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(tasks) == 1
            assert tasks[0].payload["step_id"] == str(step.id)
            assert tasks[0].status == ScheduledTaskStatus.pending
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_trigger_condition_skips_step() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        await db.execute(delete(UserTag).where(UserTag.user_id == user.telegram_id))
        await db.commit()

        funnel = await _create_funnel(db, entry_key=f"trigger_{uuid4().hex[:8]}")
        await _create_step(
            db,
            funnel,
            order=1,
            step_key=f"gated_{uuid4().hex[:8]}",
            config=_build_config("Hidden", trigger_type="has_tags", trigger_tags=["paid"]),
        )
        step_2 = await _create_step(
            db,
            funnel,
            order=2,
            step_key=f"visible_{uuid4().hex[:8]}",
            config=_build_config("Visible", wait_for_payment=True),
        )

        try:
            await engine.start_funnel(user, funnel)

            assert len(fake_bot.messages) == 1
            assert fake_bot.messages[0]["text"] == "Visible"
            state = await db.execute(
                select(UserFunnelState).where(UserFunnelState.user_id == user.telegram_id, UserFunnelState.funnel_id == funnel.id)
            )
            active_state = state.scalar_one_or_none()
            assert active_state is not None
            assert active_state.current_step_id == step_2.id
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_button_click_add_tag_and_is_idempotent() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"tag_{uuid4().hex[:8]}")
        step = await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config(
                "Tag step",
                buttons=[
                    {"text": "Mark", "action": {"type": "add_tag", "value": "vip"}},
                ],
                wait_for_payment=True,
            ),
        )

        try:
            await engine.start_funnel(user, funnel)
            button_id = _callback_button_id(step)

            await engine.handle_button_click(user, step, button_id, f"btn:{step.id.hex[:8]}:{button_id.hex[:8]}")
            await engine.handle_button_click(user, step, button_id, f"btn:{step.id.hex[:8]}:{button_id.hex[:8]}")

            tag_count = await db.scalar(
                select(func.count(UserTag.user_id)).where(
                    UserTag.user_id == user.telegram_id,
                    UserTag.tag == "vip",
                )
            )
            click_tag_count = await db.scalar(
                select(func.count(UserTag.user_id)).where(
                    UserTag.user_id == user.telegram_id,
                    UserTag.tag == f"funnel_step_clicked:{step.id}",
                )
            )

            assert int(tag_count or 0) == 1
            assert int(click_tag_count or 0) == 1
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_button_click_goto_step() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"goto_{uuid4().hex[:8]}")
        step_2 = await _create_step(db, funnel, order=2, config=_build_config("Destination", wait_for_payment=True))
        step_1 = await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config(
                "Source",
                buttons=[
                    {"text": "Next", "action": {"type": "goto_step", "value": step_2.step_key}},
                ],
                wait_for_payment=True,
            ),
        )

        try:
            await engine.start_funnel(user, funnel)
            button_id = _callback_button_id(step_1)

            await engine.handle_button_click(user, step_1, button_id, f"btn:{step_1.id.hex[:8]}:{button_id.hex[:8]}")

            assert fake_bot.messages[-1]["text"] == "Destination"
            state = await db.execute(
                select(UserFunnelState).where(UserFunnelState.user_id == user.telegram_id, UserFunnelState.funnel_id == funnel.id)
            )
            active_state = state.scalar_one_or_none()
            assert active_state is not None
            assert active_state.current_step_id == step_2.id
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])


@pytest.mark.asyncio
async def test_pay_product_creates_pending_purchase() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        product = await _create_product(db, price=Decimal("490.00"))
        funnel = await _create_funnel(db, entry_key=f"pay_{uuid4().hex[:8]}")
        step = await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config(
                "Buy it",
                buttons=[
                    {"text": "Pay", "action": {"type": "pay_product", "value": str(product.id)}},
                ],
                wait_for_payment=True,
            ),
        )

        try:
            await engine.start_funnel(user, funnel)
            button_id = _callback_button_id(step)

            await engine.handle_button_click(user, step, button_id, f"btn:{step.id.hex[:8]}:{button_id.hex[:8]}")

            purchase = await db.execute(
                select(Purchase).where(Purchase.user_id == user.telegram_id, Purchase.product_id == product.id)
            )
            purchase_row = purchase.scalar_one_or_none()
            assert purchase_row is not None
            assert purchase_row.status == PaymentStatus.pending
            assert float(purchase_row.amount) == 490.0
            assert fake_bot.messages[-1]["text"].startswith("Создана заявка на оплату продукта")
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id], product_ids=[product.id])


@pytest.mark.asyncio
async def test_continue_after_payment_advances_waiting_step() -> None:
    async with _db_session() as db:
        fake_bot = FakeBot()
        engine = FunnelEngine(bot=fake_bot, db=db)
        user = await _create_user(db)
        funnel = await _create_funnel(db, entry_key=f"payment_{uuid4().hex[:8]}")
        step_2 = await _create_step(db, funnel, order=2, config=_build_config("After payment", wait_for_payment=True))
        await _create_step(
            db,
            funnel,
            order=1,
            config=_build_config("Waiting payment", wait_for_payment=True),
        )

        try:
            await engine.start_funnel(user, funnel)
            assert fake_bot.messages[-1]["text"] == "Waiting payment"

            await engine.continue_after_payment(user, funnel)

            assert fake_bot.messages[-1]["text"] == "After payment"
            state = await db.execute(
                select(UserFunnelState).where(UserFunnelState.user_id == user.telegram_id, UserFunnelState.funnel_id == funnel.id)
            )
            active_state = state.scalar_one_or_none()
            assert active_state is not None
            assert active_state.current_step_id == step_2.id
        finally:
            await _cleanup(db, user_ids=[user.telegram_id], funnel_ids=[funnel.id])
