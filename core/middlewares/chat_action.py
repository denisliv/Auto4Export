from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery
from aiogram.utils.chat_action import ChatActionSender


class ChatActionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        long_operation_type = get_flag(data, "long_operation")

        if not long_operation_type:
            return await handler(event, data)

        async with ChatActionSender(
            action=long_operation_type, chat_id=event.message.chat.id, interval=1
        ):
            return await handler(event, data)
