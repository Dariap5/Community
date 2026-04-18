from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Продукты и оплата")],
            [KeyboardButton(text="📂 Мои подписки")],
            [KeyboardButton(text="❓ Задать вопрос")],
            [KeyboardButton(text="📄 Оферта"), KeyboardButton(text="🔒 Конфиденциальность")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
