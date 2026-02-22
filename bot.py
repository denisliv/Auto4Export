import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config_data.config import Config, load_config
from core.db.methods import create_db_tables
from core.handlers import admin, advice_form, damaged_form, other, unbroken_form, user
from core.keyboards.set_menu import set_main_menu
from core.middlewares import (
    ChatActionMiddleware,
    DbSessionMiddleware,
    LimitActionMiddleware,
    ThrottlingMiddleware,
)
from core.services.admin_sevices import SenderList
from core.services.services import download_csv, subscription_sender

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(filename)s:%(lineno)d #%(levelname)-8s "
        "[%(asctime)s] - %(name)s - %(message)s",
    )
    logger.info("Starting bot")

    config: Config = load_config()
    copart_url: str = config.tg_bot.copart_url
    admin_ids: list = config.tg_bot.admin_ids

    storage: RedisStorage = RedisStorage.from_url(config.tg_bot.redis_url)

    engine = create_async_engine(url=config.tg_bot.database_url, echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    bot: Bot = Bot(token=config.tg_bot.bot_token, parse_mode="HTML")

    dp: Dispatcher = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker, engine=engine))
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        download_csv, trigger="interval", minutes=30, kwargs={"url": copart_url}
    )
    scheduler.add_job(
        subscription_sender,
        trigger="cron",
        hour=9,
        minute=30,
        kwargs={"bot": bot, "sessionmaker": sessionmaker},
    )
    scheduler.start()

    dp.callback_query.middleware(ChatActionMiddleware())
    dp.message.middleware(ThrottlingMiddleware(storage=storage, admin_ids=admin_ids))
    dp.callback_query.middleware(LimitActionMiddleware(storage=storage))

    dp.include_router(user.router)
    dp.include_router(advice_form.router)
    dp.include_router(unbroken_form.router)
    dp.include_router(damaged_form.router)
    dp.include_router(admin.router)
    dp.include_router(other.router)

    sender_list = SenderList(bot)

    await create_db_tables(engine)
    await set_main_menu(bot, admin_ids=admin_ids)

    # Загрузка CSV при первом запуске (дальше обновляется по расписанию каждые 30 мин)
    logger.info("Downloading initial Copart CSV...")
    try:
        await download_csv(url=copart_url)
        logger.info("Copart CSV downloaded successfully")
    except Exception as e:
        logger.warning(f"Initial CSV download failed (will retry in 30 min): {e}")

    await dp.start_polling(bot, senderlist=sender_list)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.error("Bot stopped")
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}", exc_info=True)
