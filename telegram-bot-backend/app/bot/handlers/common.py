from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from app.bot.keyboards import main_reply_keyboard
from app.config import get_settings
from app.db.models import PaymentStatus, Product, Purchase, User
from app.db.session import SessionLocal
from app.services.settings_service import SettingsService
from app.services.support_service import SupportService

router = Router(name="common")
settings = get_settings()


class AskSupportState(StatesGroup):
    waiting_text = State()


def _price_text(value: Decimal | float) -> str:
    return f"{value} ₽"


@router.message(Command("products"))
@router.message(F.text == "🛍 Продукты и оплата")
async def products_handler(message: Message) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(Product).where(Product.is_active.is_(True)).order_by(Product.id.asc()))
        products = list(result.scalars().all())

    if not products:
        await message.answer("Список продуктов пока пуст.", reply_markup=main_reply_keyboard())
        return

    lines: list[str] = ["<b>Доступные продукты</b>"]
    for product in products:
        lines.append(f"• <b>{product.name}</b> — {_price_text(product.price)}")
        if product.description:
            lines.append(product.description)
        if product.payment_url:
            lines.append(f"Оплата: {product.payment_url}")
        lines.append("")

    await message.answer("\n".join(lines).strip(), parse_mode="HTML", reply_markup=main_reply_keyboard())


@router.message(Command("subscriptions"))
@router.message(F.text == "📂 Мои подписки")
async def subscriptions_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await message.answer("Покупок пока нет.", reply_markup=main_reply_keyboard())
            return

        purchases_result = await session.execute(
            select(Purchase, Product)
            .join(Product, Product.id == Purchase.product_id)
            .where(Purchase.user_id == user.id, Purchase.payment_status == PaymentStatus.paid)
            .order_by(Purchase.paid_at.desc())
        )
        rows = list(purchases_result.all())

    if not rows:
        await message.answer("У вас пока нет активных подписок.", reply_markup=main_reply_keyboard())
        return

    lines: list[str] = ["<b>Ваши подписки</b>"]
    for purchase, product in rows:
        paid_at = purchase.paid_at.strftime("%d.%m.%Y %H:%M") if purchase.paid_at else "-"
        lines.append(f"• <b>{product.name}</b> ({paid_at})")
        lines.append(f"Материал: {product.access_payload}")
        lines.append("")

    await message.answer("\n".join(lines).strip(), parse_mode="HTML", reply_markup=main_reply_keyboard())


@router.message(Command("ask"))
@router.message(F.text == "❓ Задать вопрос")
async def ask_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(AskSupportState.waiting_text)
    await message.answer("Напишите ваш вопрос одним сообщением.", reply_markup=main_reply_keyboard())


@router.message(AskSupportState.waiting_text)
async def ask_state_handler(message: Message, state: FSMContext) -> None:
    if settings.support_chat_id == 0:
        await message.answer("Чат поддержки еще не настроен.", reply_markup=main_reply_keyboard())
        await state.clear()
        return

    async with SessionLocal() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = user_result.scalar_one_or_none()
        if user is None:
            await message.answer("Сначала запустите /start.", reply_markup=main_reply_keyboard())
            await state.clear()
            return

        support_message = await message.bot.send_message(
            chat_id=settings.support_chat_id,
            text=(
                "<b>Новый вопрос от пользователя</b>\n"
                f"User ID: <code>{user.telegram_id}</code>\n"
                f"Username: @{user.username or '-'}\n\n"
                f"{message.text}"
            ),
            parse_mode="HTML",
        )
        await SupportService.bind_support_message(
            session=session,
            support_chat_id=settings.support_chat_id,
            support_message_id=support_message.message_id,
            user_id=user.id,
        )

    await message.answer("Вопрос отправлен в поддержку.", reply_markup=main_reply_keyboard())
    await state.clear()


@router.message(Command("offer"))
@router.message(F.text == "📄 Оферта")
async def offer_handler(message: Message) -> None:
    async with SessionLocal() as session:
        offer_value = await SettingsService.get_text(
            session,
            key="offer_content",
            default="https://example.com/oferta",
        )
    await message.answer(offer_value, parse_mode="HTML", reply_markup=main_reply_keyboard())


@router.message(Command("privacy"))
@router.message(F.text == "🔒 Конфиденциальность")
async def privacy_handler(message: Message) -> None:
    async with SessionLocal() as session:
        privacy_value = await SettingsService.get_text(
            session,
            key="privacy_content",
            default="https://example.com/privacy",
        )
    await message.answer(privacy_value, parse_mode="HTML", reply_markup=main_reply_keyboard())


@router.message(F.chat.id == settings.support_chat_id, F.reply_to_message)
async def support_reply_handler(message: Message) -> None:
    if not message.reply_to_message:
        return

    async with SessionLocal() as session:
        user_id = await SupportService.resolve_user_id(
            session=session,
            support_chat_id=message.chat.id,
            support_message_id=message.reply_to_message.message_id,
        )
        if user_id is None:
            return

        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

    if message.text:
        await message.bot.send_message(chat_id=user.telegram_id, text=message.text, parse_mode="HTML")
