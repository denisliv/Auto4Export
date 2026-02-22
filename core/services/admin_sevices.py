import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import methods


class SenderList:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def get_keyboard(self, text_button, url_button):
        keyboard_builder = InlineKeyboardBuilder()
        keyboard_builder.button(text=text_button, url=url_button)
        keyboard_builder.adjust(1)
        return keyboard_builder.as_markup()

    async def send_message(self, session: AsyncSession, user_id: int, from_chat_id: int, message_id: int,
                           keyboard: InlineKeyboardMarkup = None):
        try:
            await self.bot.copy_message(user_id, from_chat_id, message_id, reply_markup=keyboard)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self.send_message(user_id, from_chat_id, message_id, reply_markup=keyboard)
        except Exception as e:
            await methods.update_status(session, user_id, '​unsuccessful', f'{e}')
        else:
            await methods.update_status(session, user_id, 'success', 'No errors')
            return True
        return False

    async def broadcaster(self, session: AsyncSession, from_chat_id: int, message_id: int,
                          text_button: str = None, url_button: str = None):
        keyboard = None

        if text_button and url_button:
            keyboard = await self.get_keyboard(text_button, url_button)

        user_ids = await methods.get_users(session)

        count = 0
        try:
            for user_id in user_ids:
                if await self.send_message(session, int(user_id), from_chat_id, message_id, keyboard):
                    count += 1
                await asyncio.sleep(0.1)
        finally:
            print(f'Разослали сообщение {count} пользователям')

        return count
