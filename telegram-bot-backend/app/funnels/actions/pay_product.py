from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models import PaymentStatus, Product, Purchase, User
from app.funnels.actions import ActionResult
from app.schemas.step_config import ButtonActionPayProduct

logger = logging.getLogger(__name__)


async def handle_pay_product(bot, db, user: User, action: ButtonActionPayProduct) -> ActionResult:
    try:
        product_id = UUID(action.value)
    except ValueError:
        logger.warning("Invalid product id in pay_product action: %s", action.value)
        return ActionResult()

    product_result = await db.execute(select(Product).where(Product.id == product_id))
    product = product_result.scalar_one_or_none()
    if product is None:
        logger.warning("Product not found for pay_product action: %s", action.value)
        return ActionResult()

    purchase_result = await db.execute(
        select(Purchase).where(
            Purchase.user_id == user.telegram_id,
            Purchase.product_id == product.id,
            Purchase.status == PaymentStatus.pending,
        )
    )
    purchase = purchase_result.scalar_one_or_none()
    if purchase is None:
        purchase = Purchase(
            user_id=user.telegram_id,
            product_id=product.id,
            amount=product.price,
            status=PaymentStatus.pending,
        )
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)

    if bot is not None:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"Создана заявка на оплату продукта {product.name}.",
            parse_mode="HTML",
        )

    return ActionResult()
