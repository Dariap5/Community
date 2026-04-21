import asyncio
from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from app.config import settings
from app.db.models import Funnel, FunnelStep, FunnelCrossEntryBehavior, Product
from app.schemas.step_config import StepConfig

async def seed():
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    product_490 = Product(
        id=uuid4(),
        name="Продукт 490",
        price=490,
        description="Основной продукт из seed",
        photo_file_id=None,
        is_active=True,
    )

    funnels = [
        Funnel(id=uuid4(), name="Гайд", entry_key="guide"),
        Funnel(id=uuid4(), name="Продукт 490", entry_key="product"),
        Funnel(id=uuid4(), name="Комьюнити", entry_key="community"),
        Funnel(id=uuid4(), name="Дожим", entry_key="dozhim"),
    ]

    steps = []

    # 1. Гайд (3 шага)
    # Шаг 1
    c_g1 = StepConfig(
        blocks=[{"type": "text", "content_text": "Вот ваш гайд!"}],
        after_step={"add_tags": ["получил_гайд"]},
    ).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[0].id, order=1, name="Отправка гайда", step_key="guide_1", config=c_g1))
    
    # Шаг 2
    c_g2 = StepConfig(delay_before={"value": 48, "unit": "hours"}, blocks=[{"type": "text", "content_text": "Прошло 48 часов!"}]).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[0].id, order=2, name="Тишина 48 ч", step_key="guide_2", config=c_g2))

    # Шаг 3 (опциональный переход к продукту)
    c_g3 = StepConfig(blocks=[{"type": "text", "content_text": "Купите наш продукт!"}]).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[0].id, order=3, name="Переход к продукту", step_key="guide_3", is_active=False, config=c_g3))

    # 2. Продукт (3 шага)
    # Шаг 1
    c_p1 = StepConfig(
        wait_for_payment=True,
        linked_product_id=product_490.id,
        blocks=[
            {"type": "text", "content_text": "Информация о продукте"},
            {
                "type": "buttons",
                "buttons": [
                    {"text": "Оплатить", "action": {"type": "pay_product", "value": str(product_490.id)}}
                ],
            },
        ],
    ).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[1].id, order=1, name="Информация", step_key="prod_info", config=c_p1))
    
    # Шаг 2
    c_p2 = StepConfig(blocks=[{"type": "text", "content_text": "Спасибо за оплату, вот материалы!"}]).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[1].id, order=2, name="Спасибо за оплату", step_key="prod_wait", config=c_p2))

    # Шаг 3
    c_p3 = StepConfig(blocks=[{"type": "text", "content_text": "Выдача материалов завершена."}]).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[1].id, order=3, name="Выдача", step_key="prod_delivery", config=c_p3))

    # 3. Комьюнити (1 шаг)
    c_com1 = StepConfig(
        blocks=[
            {"type": "text", "content_text": "Приглашение"},
            {
                "type": "buttons",
                "buttons": [
                    {"text": "Вступить", "action": {"type": "url", "value": "https://t.me"}},
                    {"text": "Есть сомнения", "action": {"type": "add_tag", "value": "есть_сомнения"}},
                ],
            },
        ],
        after_step={"dozhim_if_no_click_hours": 3},
    ).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[2].id, order=1, name="Приветствие", step_key="com_1", config=c_com1))

    # 4. Дожим (2 шага)
    c_d1 = StepConfig(
        blocks=[
            {"type": "text", "content_text": "Экспертный пост"},
            {
                "type": "buttons",
                "buttons": [
                    {
                        "text": "Консультация",
                        "action": {"type": "url", "value": "https://calendly.com/replace-me"},
                        "visible_if": {"not_has_tags": ["есть_сомнения"]},
                    }
                ],
            },
        ]
    ).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[3].id, order=1, name="Пост 1", step_key="dozhim_1", config=c_d1))

    c_d2 = StepConfig(
        delay_before={"value": 24, "unit": "hours"},
        blocks=[
            {"type": "text", "content_text": "Продающий пост"},
            {
                "type": "buttons",
                "buttons": [
                    {
                        "text": "Купить",
                        "action": {"type": "url", "value": "https://t.me"},
                        "visible_if": {"not_has_tags": ["есть_сомнения"]},
                    }
                ],
            },
        ],
    ).model_dump(mode="json")
    steps.append(FunnelStep(funnel_id=funnels[3].id, order=2, name="Пост 2", step_key="dozhim_2", config=c_d2))

    try:
        async with async_session() as db:
            count = await db.execute(text("SELECT COUNT(*) FROM funnels"))
            if count.scalar() == 0:
                db.add(product_490)
                for f in funnels:
                    db.add(f)
                for s in steps:
                    db.add(s)
                await db.commit()
                print("Seed ok!")
            else:
                print("Seed already run. Skipping.")
    except Exception as e:
        print(f"Error seeding: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
