from dataclasses import dataclass

from environs import Env


@dataclass
class TgBot:
    bot_token: str  # Токен для доступа к телеграм-боту
    database_url: str  # url подключения к БД
    redis_url: str  # url подключения к Redis
    admin_ids: list  # Список id администраторов бота
    copart_url: str  # URL для обновления csv файл
    bitrix_webhook_url: str  # Входящий вебхук Bitrix24 для создания лидов


@dataclass
class Config:
    tg_bot: TgBot


# Функция, читающая файл .env и возвращающая экземпляр класса Config
def load_config(path: str | None = None) -> Config:
    env = Env()
    env.read_env(path)
    return Config(
        tg_bot=TgBot(bot_token=env.str('BOT_TOKEN'),
                     database_url=env.str('DATABASE_URL'),
                     redis_url=env.str('REDIS_URL'),
                     admin_ids=list(map(int, env.list('ADMIN_IDS'))),
                     copart_url=env.str('COPART_URL'),
                     # Без значения по умолчанию: без вебхука бот не стартует,
                     # вместо того чтобы молча терять заявки клиентов.
                     bitrix_webhook_url=env.str('BITRIX_WEBHOOK_URL'),
                     )
    )
