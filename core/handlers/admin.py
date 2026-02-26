import asyncio

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
from aiogram.types import InputMediaPhoto, InputMediaVideo
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


# Буфер для сбора сообщений альбома (медиагруппы)
_album_buffer: dict[str, list[Message]] = {}


def _build_media_from_messages(messages: list[Message]) -> list[InputMediaPhoto | InputMediaVideo]:
    """Собирает список InputMedia из сообщений альбома (отсортированных по message_id)."""
    media_list = []
    caption = None
    for msg in sorted(messages, key=lambda m: m.message_id):
        if msg.photo:
            file_id = msg.photo[-1].file_id
            if caption is None and msg.caption:
                caption = msg.caption
            media_list.append(InputMediaPhoto(media=file_id, caption=caption))
            caption = None  # Подпись только у первого элемента
        elif msg.video:
            file_id = msg.video.file_id
            if caption is None and msg.caption:
                caption = msg.caption
            media_list.append(InputMediaVideo(media=file_id, caption=caption))
            caption = None
    return media_list


async def _process_album_after_delay(
    media_group_id: str,
    state: FSMContext,
    bot: Bot,
    chat_id: int,
):
    """Обрабатывает собранный альбом после короткой задержки."""
    await asyncio.sleep(0.5)
    if media_group_id not in _album_buffer:
        return
    messages = _album_buffer.pop(media_group_id)
    messages.sort(key=lambda m: m.message_id)

    media_list = _build_media_from_messages(messages)
    if not media_list:
        await bot.send_message(chat_id, "Не удалось обработать альбом. Отправь фото или видео.")
        return

    sorted_msgs = sorted(messages, key=lambda m: m.message_id)
    media_items = []
    for i, m in enumerate(sorted_msgs):
        caption = m.caption if i == 0 else None
        if m.photo:
            media_items.append(
                {"type": "photo", "file_id": m.photo[-1].file_id, "caption": caption}
            )
        elif m.video:
            media_items.append(
                {"type": "video", "file_id": m.video.file_id, "caption": caption}
            )

    await state.update_data(
        message_ids=[m.message_id for m in sorted_msgs],
        chat_id=chat_id,
        media_items=media_items,
        is_album=True,
    )
    await state.set_state(FSMAdminForm.get_button)
    await bot.send_message(
        chat_id,
        "Ок.\r\n"
        "Я запомнил альбом, который ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


@router.message(Text(text=LEXICON_ADMIN_BUTTONS_RU["newsletter_button"]))
async def admin_get_message(message: Message, state: FSMContext):
    await message.answer(
        "Ок.\r\n"
        "Отправь мне сообщение, которое будет использовано как рекламное.\r\n"
        "Можешь использовать текст, одно фото/видео или альбом (до 10 фото/видео)."
    )
    await state.set_state(FSMAdminForm.get_message)


@router.message(StateFilter(FSMAdminForm.get_message), F.photo | F.video)
async def admin_get_button_media(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает фото/видео — одно сообщение или альбом."""
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in _album_buffer:
            _album_buffer[mg_id] = []
            asyncio.create_task(
                _process_album_after_delay(mg_id, state, bot, message.chat.id)
            )
        _album_buffer[mg_id].append(message)
        return

    # Одно фото или видео
    await state.update_data(
        message_id=message.message_id,
        message_ids=None,
        chat_id=message.from_user.id,
        media_items=None,
        is_album=False,
    )
    await state.set_state(FSMAdminForm.get_button)
    await message.answer(
        text="Ок.\r\n"
        "Я запомнил сообщение, которое ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


@router.message(StateFilter(FSMAdminForm.get_message))
async def admin_get_button(message: Message, state: FSMContext):
    """Обрабатывает текстовое сообщение или другое медиа."""
    await state.update_data(
        message_id=message.message_id,
        message_ids=None,
        chat_id=message.from_user.id,
        media_items=None,
        is_album=False,
    )
    await state.set_state(FSMAdminForm.get_button)
    await message.answer(
        text="Ок.\r\n"
        "Я запомнил сообщение, которое ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


@router.callback_query(StateFilter(FSMAdminForm.get_button))
async def admin_button_press(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if callback.data == "add_button":
        await callback.message.answer(
            "Отправь текст, который будет отображаться на кнопке.", reply_markup=None
        )
        await state.set_state(FSMAdminForm.get_button_text)

    elif callback.data == "no_button":
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(text_button="Перейти в канал")
        await state.update_data(url_button="https://t.me/auto4export")
        data = await state.get_data()
        chat_id = int(data.get("chat_id"))
        is_album = data.get("is_album", False)
        if is_album:
            await callback.message.answer(
                "Введите текст, который будет отображаться над кнопкой:"
            )
            await state.set_state(FSMAdminForm.get_button_message_text)
        else:
            added_keyboards = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Перейти в канал", url="https://t.me/auto4export"
                        )
                    ]
                ]
            )
            await admin_confirm(
                callback.message, bot, chat_id, added_keyboards, state_data=data
            )
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
    chat_id = int(data.get("chat_id"))
    is_album = data.get("is_album", False)

    added_keyboards = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text_button, url=f"{message.text}")]
        ]
    )
    if is_album:
        await message.answer(
            "Введите текст, который будет отображаться над кнопкой:"
        )
        await state.set_state(FSMAdminForm.get_button_message_text)
    else:
        await admin_confirm(message, bot, chat_id, added_keyboards, state_data=data)


@router.message(StateFilter(FSMAdminForm.get_button_message_text))
async def admin_get_button_message_text(
    message: Message, bot: Bot, state: FSMContext
):
    """Получает текст над кнопкой (только для альбома)."""
    await state.update_data(button_message_text=message.text or "👇")
    data = await state.get_data()
    text_button = data.get("text_button")
    url_button = data.get("url_button")
    chat_id = int(data.get("chat_id"))

    added_keyboards = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text_button, url=url_button)]
        ]
    )
    await admin_confirm(message, bot, chat_id, added_keyboards, state_data=data)


def _build_media_list(media_items: list[dict]) -> list[InputMediaPhoto | InputMediaVideo]:
    """Собирает InputMedia из сохранённых media_items."""
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


async def admin_confirm(
    message: Message,
    bot: Bot,
    chat_id: int,
    reply_markup: InlineKeyboardMarkup = None,
    state_data: dict = None,
):
    """Показывает превью рассылки и запрашивает подтверждение."""
    is_album = state_data.get("is_album", False) if state_data else False

    if is_album and state_data.get("media_items"):
        media_list = _build_media_list(state_data["media_items"])
        await bot.send_media_group(chat_id, media=media_list)
        if reply_markup:
            button_text = state_data.get("button_message_text", "👇")
            await bot.send_message(
                chat_id,
                text=button_text,
                reply_markup=reply_markup,
            )
    else:
        message_id = int(state_data.get("message_id")) if state_data else None
        if message_id:
            await bot.copy_message(
                chat_id, chat_id, message_id, reply_markup=reply_markup
            )

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
    media_items = data.get("media_items")
    is_album = data.get("is_album", False)
    text_button = data.get("text_button")
    url_button = data.get("url_button")
    button_message_text = data.get("button_message_text", "👇")
    if callback.data == "confirm_sender":
        await callback.message.edit_text("Начинаю рассылку", reply_markup=None)
        if not await methods.admin_check_table(engine):
            await methods.admin_create_table(engine, session)

        count = await senderlist.broadcaster(
            session,
            chat_id=chat_id,
            message_id=message_id,
            media_items=media_items,
            is_album=is_album,
            text_button=text_button,
            url_button=url_button,
            button_message_text=button_message_text,
        )
        await callback.message.answer(
            f"Успешно разослали рекламное сообщение [{count}] пользователям"
        )
        await methods.admin_delete_table(engine)

    elif callback.data == "cancel_sender":
        await callback.message.edit_text("Отменил рассылку", reply_markup=None)
    await state.clear()
