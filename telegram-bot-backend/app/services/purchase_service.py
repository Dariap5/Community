from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentStatus, Purchase, ScheduledTask, ScheduledTaskStatus, UserTag
from app.services.tag_service import TagService


class PurchaseService:
    @staticmethod
    async def mark_paid(
        session: AsyncSession,
        external_payment_id: str,
        paid_amount: float,
        paid_tag: str,
        user_id: int | None = None,
        product_id: int | None = None,
    ) -> Purchase | None:
        result = await session.execute(
            select(Purchase).where(Purchase.external_payment_id == external_payment_id)
        )
        purchase = result.scalar_one_or_none()
        if purchase is None:
            if user_id is None or product_id is None:
                return None
            purchase = Purchase(
                user_id=user_id,
                product_id=product_id,
                amount=paid_amount,
                external_payment_id=external_payment_id,
                payment_status=PaymentStatus.pending,
            )
            session.add(purchase)
            await session.flush()

        purchase.payment_status = PaymentStatus.paid
        purchase.amount = paid_amount
        purchase.paid_at = datetime.now(timezone.utc)
        purchase.metadata_payload = {**purchase.metadata_payload, "paid_tag": paid_tag}

        if not await TagService.has_tag(session, purchase.user_id, paid_tag):
            session.add(UserTag(user_id=purchase.user_id, tag=paid_tag))

        session.add(
            ScheduledTask(
                user_id=purchase.user_id,
                task_type="payment_confirmed",
                payload={"purchase_id": purchase.id, "paid_tag": paid_tag},
                run_at=datetime.now(timezone.utc),
                status=ScheduledTaskStatus.pending,
            )
        )
        await session.commit()
        await session.refresh(purchase)
        return purchase
