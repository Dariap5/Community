from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ButtonType,
    Funnel,
    FunnelStep,
    StepButton,
    StepMessage,
    StepMessageType,
)


async def seed_default_scenarios(session: AsyncSession) -> None:
    guide = await _upsert_funnel(session, "guide", 1)
    product = await _upsert_funnel(session, "product", 2)
    community = await _upsert_funnel(session, "community", 3)
    dozhim = await _upsert_funnel(session, "dozhim", 4)

    await _replace_funnel_steps(session, guide.id)
    await _replace_funnel_steps(session, product.id)
    await _replace_funnel_steps(session, community.id)
    await _replace_funnel_steps(session, dozhim.id)

    await _seed_guide(session, guide.id)
    await _seed_product(session, product.id)
    await _seed_community(session, community.id)
    await _seed_dozhim(session, dozhim.id)

    await session.commit()


async def _upsert_funnel(session: AsyncSession, name: str, order_index: int) -> Funnel:
    result = await session.execute(select(Funnel).where(Funnel.name == name))
    funnel = result.scalar_one_or_none()
    if funnel is None:
        funnel = Funnel(name=name, order_index=order_index, is_enabled=True)
        session.add(funnel)
        await session.flush()
    else:
        funnel.order_index = order_index
        funnel.is_enabled = True
        await session.flush()
    return funnel


async def _replace_funnel_steps(session: AsyncSession, funnel_id: int) -> None:
    await session.execute(delete(FunnelStep).where(FunnelStep.funnel_id == funnel_id))
    await session.flush()


async def _seed_guide(session: AsyncSession, funnel_id: int) -> None:
    a1 = FunnelStep(
        funnel_id=funnel_id,
        step_order=1,
        step_key="A1",
        delay_before_seconds=0,
        trigger_conditions={"post_actions": {"add_tags": ["получил_гайд"]}},
    )
    session.add(a1)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=a1.id,
                message_order=1,
                message_type=StepMessageType.text,
                content_text="Привет! Держи гайд 👇",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=a1.id,
                message_order=2,
                message_type=StepMessageType.document,
                content_file="GUIDE_PDF_FILE_ID",
                caption="Гайд",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=a1.id,
                message_order=3,
                message_type=StepMessageType.text,
                content_text="Внутри гайда структура, чеклисты и шаги запуска.",
                delay_after_seconds=0,
            ),
        ]
    )

    a2 = FunnelStep(
        funnel_id=funnel_id,
        step_order=2,
        step_key="A2",
        delay_before_seconds=172800,
        trigger_conditions={},
    )
    session.add(a2)
    await session.flush()

    a3 = FunnelStep(
        funnel_id=funnel_id,
        step_order=3,
        step_key="A3",
        delay_before_seconds=0,
        trigger_conditions={
            "enabled": False,
            "post_actions": {
                "launch_funnel": {"name": "product", "delay_seconds": 0},
            },
        },
    )
    session.add(a3)
    await session.flush()


async def _seed_product(session: AsyncSession, funnel_id: int) -> None:
    b1 = FunnelStep(
        funnel_id=funnel_id,
        step_order=1,
        step_key="B1",
        delay_before_seconds=0,
        trigger_conditions={"post_actions": {"add_tags": ["видел_продукт_1"]}},
    )
    session.add(b1)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=b1.id,
                message_order=1,
                message_type=StepMessageType.photo,
                content_file="PRODUCT_490_PHOTO_FILE_ID",
                caption="Продукт 490 ₽",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=b1.id,
                message_order=2,
                message_type=StepMessageType.text,
                content_text="<b>Что дает продукт:</b> четкий путь, шаблоны и быстрый старт.",
                delay_after_seconds=0,
            ),
        ]
    )
    session.add(
        StepButton(
            step_id=b1.id,
            text="Купить за 490 ₽",
            button_type=ButtonType.url,
            value="https://example.com/pay/product-490",
            is_enabled=True,
            conditions={},
        )
    )

    b2 = FunnelStep(
        funnel_id=funnel_id,
        step_order=2,
        step_key="B2",
        delay_before_seconds=0,
        trigger_conditions={"wait_for_payment": True},
    )
    session.add(b2)
    await session.flush()

    b3 = FunnelStep(
        funnel_id=funnel_id,
        step_order=3,
        step_key="B3",
        delay_before_seconds=0,
        trigger_conditions={
            "post_actions": {
                "launch_funnel": {
                    "name": "community",
                    "delay_seconds": 86400,
                    "required_tag": "купил_продукт_1",
                }
            }
        },
    )
    session.add(b3)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=b3.id,
                message_order=1,
                message_type=StepMessageType.text,
                content_text="Оплата прошла! Вот ваш материал:",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=b3.id,
                message_order=2,
                message_type=StepMessageType.document,
                content_file="PRODUCT_1_MATERIAL_FILE_ID",
                caption="Материал продукта 1",
                delay_after_seconds=0,
            ),
        ]
    )


async def _seed_community(session: AsyncSession, funnel_id: int) -> None:
    v1 = FunnelStep(
        funnel_id=funnel_id,
        step_order=1,
        step_key="V1",
        delay_before_seconds=0,
        trigger_conditions={"post_actions": {"start_dozhim_if_no_click_hours": 3}},
    )
    session.add(v1)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=v1.id,
                message_order=1,
                message_type=StepMessageType.photo,
                content_file="COMMUNITY_INVITE_PHOTO_FILE_ID",
                caption="Комьюнити",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=v1.id,
                message_order=2,
                message_type=StepMessageType.text,
                content_text="Приглашаем в комьюнити. Готовы вступить?",
                delay_after_seconds=0,
            ),
        ]
    )

    session.add_all(
        [
            StepButton(
                step_id=v1.id,
                text="Вступить",
                button_type=ButtonType.callback,
                value="community:join",
                is_enabled=True,
                conditions={},
            ),
            StepButton(
                step_id=v1.id,
                text="Есть сомнения",
                button_type=ButtonType.callback,
                value="community:doubt",
                is_enabled=True,
                conditions={},
            ),
        ]
    )


async def _seed_dozhim(session: AsyncSession, funnel_id: int) -> None:
    d1 = FunnelStep(
        funnel_id=funnel_id,
        step_order=1,
        step_key="D1",
        delay_before_seconds=86400,
        trigger_conditions={},
    )
    session.add(d1)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=d1.id,
                message_order=1,
                message_type=StepMessageType.video_note,
                content_file="EXPERT_VIDEO_NOTE_FILE_ID",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=d1.id,
                message_order=2,
                message_type=StepMessageType.text,
                content_text="Экспертный пост: опыт, кейсы и история результатов.",
                delay_after_seconds=0,
            ),
        ]
    )

    d2 = FunnelStep(
        funnel_id=funnel_id,
        step_order=2,
        step_key="D2",
        delay_before_seconds=0,
        trigger_conditions={},
    )
    session.add(d2)
    await session.flush()

    session.add_all(
        [
            StepMessage(
                step_id=d2.id,
                message_order=1,
                message_type=StepMessageType.photo,
                content_file="DOZHIM_SELL_PHOTO_FILE_ID",
                caption="Комьюнити",
                delay_after_seconds=0,
            ),
            StepMessage(
                step_id=d2.id,
                message_order=2,
                message_type=StepMessageType.text,
                content_text="Продающий пост о ценности комьюнити и формате участия.",
                delay_after_seconds=0,
            ),
        ]
    )

    session.add_all(
        [
            StepButton(
                step_id=d2.id,
                text="Оплатить",
                button_type=ButtonType.url,
                value="https://example.com/pay/community",
                is_enabled=True,
                conditions={},
            ),
            StepButton(
                step_id=d2.id,
                text="Записаться на консультацию",
                button_type=ButtonType.url,
                value="https://calendly.com/replace-me",
                is_enabled=True,
                conditions={"exclude_tags": ["есть_сомнения"]},
            ),
        ]
    )
