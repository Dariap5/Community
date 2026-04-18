from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.bot.keyboards import main_reply_keyboard
from app.db.session import SessionLocal
from app.services.funnel_service import FunnelService
from app.services.user_service import UserService

router = Router(name="start")


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject) -> None:
    deeplink = command.args if command and command.args else None
    async with SessionLocal() as session:
        user = await UserService.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            source_deeplink=deeplink,
        )

        if await FunnelService.has_active_funnel(session, user.id):
            await message.answer(
                "Вы уже в нашей программе 🙌",
                reply_markup=main_reply_keyboard(),
            )
            return

        funnel_name = FunnelService.funnel_name_from_deeplink(deeplink)
        state = await FunnelService.start_funnel(session, user, funnel_name)
        if state is None:
            await message.answer(
                "Сценарий временно недоступен, попробуйте позже.",
                reply_markup=main_reply_keyboard(),
            )
            return

        await message.answer("Добро пожаловать. Запустили программу для вас.", reply_markup=main_reply_keyboard())
