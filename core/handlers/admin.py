from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from core.config_data.config import Config, load_config
from core.db import methods
from core.keyboards.keyboard_inline import create_admin_keyboard, create_choice_keyboard
from core.keyboards.keyboard_reply import create_admin_panel_keyboard
from core.lexicon.lexicon_ru import LEXICON_ADMIN_BUTTONS_RU, LEXICON_RU
from core.services.admin_sevices import SenderList
from core.utils.statesform import FSMAdminForm

router: Router = Router()

config: Config = load_config()
admin_ids: list = config.tg_bot.admin_ids


@router.message(Command(commands=["admin"]), F.from_user.id.in_(admin_ids))
async def admin_panel(message: Message):
    await message.answer(
        text=f"Здорова {message.from_user.first_name}. Снизу админ-панель. Чего изволите?",
        reply_markup=create_admin_panel_keyboard(),
    )


@router.message(Text(text=LEXICON_ADMIN_BUTTONS_RU["statistics_button"]))
async def admin_users_button_press(message: Message, session: AsyncSession):
    statistics = await methods.get_user_statistics(session)
    await message.answer(
        "Статистика 📊 по пользователям:\r\n\n"
        f"▪ Всего зарегистрировано: <b>{statistics[0]}</b>\n\r"
        f"▪ Сегодня зарегистрировались: <b>{statistics[1]}</b>\n\r"
        f"▪ Сегодня пользовались ботом: <b>{statistics[2]}</b>\n\r"
        f"▪ Всего пользователей с подпиской: <b>{statistics[3]}</b>\n\r"
        f"▪ Всего активных авто: <b>{statistics[4]}</b>\n\r"
        f"▪ Активных авто в среднем: "
        f"<b>{round(statistics[4] / statistics[3], 2) if statistics[3] != 0 else 0}</b>"
    )


@router.message(Text(text=LEXICON_ADMIN_BUTTONS_RU["exit_button"]))
async def admin_exit_button_press(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        text=f"{message.from_user.first_name}, до свидания! Заходи еще.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        text=LEXICON_RU["/start_text"](message.from_user.first_name),
        reply_markup=create_choice_keyboard(
            "choose_a_car_button", "contact_button", "more_information_button", width=1
        ),
    )


@router.message(Text(text=LEXICON_ADMIN_BUTTONS_RU["newsletter_button"]))
async def admin_get_message(message: Message, state: FSMContext):
    await message.answer(
        "Ок.\r\n"
        "Отправь мне сообщение, которое будет использовано как рекламное.\r\n"
        "Можешь использовать текст, фото, видео."
    )
    await state.set_state(FSMAdminForm.get_message)


@router.message(StateFilter(FSMAdminForm.get_message))
async def admin_get_button(message: Message, state: FSMContext):
    await message.answer(
        text="Ок.\r\n"
        "Я запомнил сообщение, которое ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )
    await state.update_data(message_id=message.message_id, chat_id=message.from_user.id)
    await state.set_state(FSMAdminForm.get_button)


@router.callback_query(StateFilter(FSMAdminForm.get_button))
async def admin_button_press(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.data == "add_button":
        await callback.message.answer(
            "Отправь текст, который будет отображаться на кнопке.", reply_markup=None
        )
        await state.set_state(FSMAdminForm.get_button_text)

    elif callback.data == "no_button":
        await callback.message.edit_reply_markup(reply_markup=None)
        data = await state.get_data()
        message_id = int(data.get("message_id"))
        chat_id = int(data.get("chat_id"))
        await state.update_data(text_button="Перейти в канал")
        await state.update_data(url_button="https://t.me/auto4export")
        added_keyboards = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Перейти в канал", url="https://t.me/auto4export"
                    )
                ]
            ]
        )
        await admin_confirm(callback.message, bot, message_id, chat_id, added_keyboards)
        await state.set_state(FSMAdminForm.get_button_text)
        await state.set_state(FSMAdminForm.get_button_url)

    await callback.answer()


@router.message(StateFilter(FSMAdminForm.get_button_text))
async def admin_get_button_text(message: Message, state: FSMContext):
    await message.answer(
        "Теперь отправь ссылку на ресурс, на который кнопка будет вести."
    )
    await state.update_data(text_button=message.text)
    await state.set_state(FSMAdminForm.get_button_url)


@router.message(StateFilter(FSMAdminForm.get_button_url))
async def admin_get_button_url(message: Message, bot: Bot, state: FSMContext):
    await state.update_data(url_button=message.text)
    data = await state.get_data()
    text_button = data.get("text_button")
    message_id = int(data.get("message_id"))
    chat_id = int(data.get("chat_id"))

    added_keyboards = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text_button, url=f"{message.text}")]
        ]
    )
    await admin_confirm(message, bot, message_id, chat_id, added_keyboards)


async def admin_confirm(
    message: Message,
    bot: Bot,
    message_id: int,
    chat_id: int,
    reply_markup: InlineKeyboardMarkup = None,
):
    await bot.copy_message(chat_id, chat_id, message_id, reply_markup=reply_markup)
    await message.answer(
        text="Вот сообщение, которое будет разослано пользователям. Подтверждаешь?",
        reply_markup=create_admin_keyboard("confirm_sender", "cancel_sender"),
    )


@router.callback_query(F.data.in_(["confirm_sender", "cancel_sender"]))
async def sender_decide(
    callback: CallbackQuery,
    state: FSMContext,
    senderlist: SenderList,
    session: AsyncSession,
    engine: AsyncEngine,
):
    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    text_button = data.get("text_button")
    url_button = data.get("url_button")
    if callback.data == "confirm_sender":
        await callback.message.edit_text("Начинаю рассылку", reply_markup=None)
        if not await methods.admin_check_table(engine):
            await methods.admin_create_table(engine, session)

        count = await senderlist.broadcaster(
            session, chat_id, message_id, text_button, url_button
        )
        await callback.message.answer(
            f"Успешно разослали рекламное сообщение [{count}] пользователям"
        )
        await methods.admin_delete_table(engine)

    elif callback.data == "cancel_sender":
        await callback.message.edit_text("Отменил рассылку", reply_markup=None)
    await state.clear()
