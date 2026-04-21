from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from app.schemas.step_config import MessageContent

logger = logging.getLogger(__name__)


async def send_block(
    bot: Bot,
    chat_id: int,
    message: MessageContent,
    reply_markup: InlineKeyboardMarkup | None = None,
    retry_count: int = 3,
) -> bool:
    for attempt in range(retry_count):
        try:
            if message.type == "text":
                await bot.send_message(
                    chat_id=chat_id,
                    text=message.content_text or "",
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "document":
                await bot.send_document(
                    chat_id=chat_id,
                    document=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "video":
                await bot.send_video(
                    chat_id=chat_id,
                    video=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            elif message.type == "video_note":
                await bot.send_video_note(
                    chat_id=chat_id,
                    video_note=message.file_id,
                )
            elif message.type == "voice":
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=message.file_id,
                    caption=message.content_text,
                    parse_mode=message.parse_mode,
                    reply_markup=reply_markup,
                )
            return True
        except TelegramRetryAfter as error:
            logger.warning("Rate limited for chat %s, sleeping %ss", chat_id, error.retry_after)
            await asyncio.sleep(error.retry_after)
        except TelegramBadRequest as error:
            logger.error("Bad request sending to %s: %s", chat_id, error)
            return False

    return False
