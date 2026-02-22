import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from core.lexicon.lexicon_ru import LEXICON_COMMANDS_RU

logger = logging.getLogger(__name__)


# Функция для настройки кнопки Menu бота
async def set_main_menu(bot: Bot, admin_ids: list[int] | None = None):
    # Команды для всех пользователей (без /admin)
    default_commands = [
        BotCommand(command=command, description=description)
        for command, description in LEXICON_COMMANDS_RU.items()
        if command != "/admin"
    ]

    # Устанавливаем команды для всех пользователей
    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())

    # Команды для администраторов (включая /admin)
    if admin_ids:
        admin_commands = [
            BotCommand(command=command, description=description)
            for command, description in LEXICON_COMMANDS_RU.items()
        ]

        # Устанавливаем команды для каждого администратора отдельно
        for admin_id in admin_ids:
            try:
                await bot.set_my_commands(
                    admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except TelegramBadRequest as e:
                # Если бот еще не взаимодействовал с администратором, пропускаем
                logger.warning(
                    f"Не удалось установить команды для администратора {admin_id}: {e.message}. "
                    "Бот должен сначала получить сообщение от этого пользователя."
                )
