from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db_session
from app.payments.verification import PaymentSignatureVerifier
from app.services.purchase_service import PurchaseService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    payload = await request.json()

    if not x_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    if not PaymentSignatureVerifier.verify(settings.payment_webhook_secret, payload, x_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    external_payment_id = str(payload.get("payment_id", ""))
    amount = float(payload.get("amount", 0))
    tag = str(payload.get("tag", "купил_продукт"))
    user_id = int(payload["user_id"]) if payload.get("user_id") is not None else None
    product_id = int(payload["product_id"]) if payload.get("product_id") is not None else None

    purchase = await PurchaseService.mark_paid(
        session=session,
        external_payment_id=external_payment_id,
        paid_amount=amount,
        paid_tag=tag,
        user_id=user_id,
        product_id=product_id,
    )
    if purchase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found")

    return {"ok": True, "purchase_id": purchase.id}
