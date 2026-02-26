import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
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

    def _build_media_list(
        self, media_items: list[dict]
    ) -> list[InputMediaPhoto | InputMediaVideo]:
        """Собирает InputMedia из media_items для send_media_group."""
        result = []
        for item in media_items:
            media_type = item["type"]
            file_id = item["file_id"]
            caption = item.get("caption")
            if media_type == "photo":
                result.append(InputMediaPhoto(media=file_id, caption=caption))
            else:
                result.append(InputMediaVideo(media=file_id, caption=caption))
        return result

    async def send_message(
        self,
        session: AsyncSession,
        user_id: int,
        from_chat_id: int,
        message_id: int,
        keyboard: InlineKeyboardMarkup = None,
        media_items: list[dict] = None,
        is_album: bool = False,
        button_message_text: str = "👇",
    ):
        if is_album and media_items:
            return await self._send_album(
                session,
                user_id,
                media_items,
                keyboard,
                button_message_text,
            )
        try:
            await self.bot.copy_message(
                user_id, from_chat_id, message_id, reply_markup=keyboard
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self.send_message(
                session, user_id, from_chat_id, message_id, keyboard
            )
        except Exception as e:
            await methods.update_status(session, user_id, "unsuccessful", f"{e}")
        else:
            await methods.update_status(session, user_id, "success", "No errors")
            return True
        return False

    async def _send_album(
        self,
        session: AsyncSession,
        user_id: int,
        media_items: list[dict],
        keyboard: InlineKeyboardMarkup = None,
        button_message_text: str = "👇",
    ) -> bool:
        """Отправляет альбом пользователю через send_media_group."""
        try:
            media_list = self._build_media_list(media_items)
            await self.bot.send_media_group(user_id, media=media_list)
            if keyboard:
                await self.bot.send_message(
                    user_id,
                    text=button_message_text,
                    reply_markup=keyboard,
                )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self._send_album(
                session, user_id, media_items, keyboard, button_message_text
            )
        except Exception as e:
            await methods.update_status(session, user_id, "unsuccessful", f"{e}")
            return False
        await methods.update_status(session, user_id, "success", "No errors")
        return True

    async def broadcaster(
        self,
        session: AsyncSession,
        chat_id: int,
        message_id: int = None,
        media_items: list[dict] = None,
        is_album: bool = False,
        text_button: str = None,
        url_button: str = None,
        button_message_text: str = "👇",
    ):
        keyboard = None

        if text_button and url_button:
            keyboard = await self.get_keyboard(text_button, url_button)

        user_ids = await methods.get_users(session)

        count = 0
        try:
            for user_id in user_ids:
                success = await self.send_message(
                    session,
                    int(user_id),
                    chat_id,
                    message_id,
                    keyboard,
                    media_items=media_items,
                    is_album=is_album,
                    button_message_text=button_message_text,
                )
                if success:
                    count += 1
                await asyncio.sleep(0.1)
        finally:
            print(f"Разослали сообщение {count} пользователям")

        return count
