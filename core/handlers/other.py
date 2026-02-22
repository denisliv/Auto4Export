from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from core.keyboards.keyboard_inline import create_url_keyboard
from core.keyboards.keyboard_reply import create_call_request_keyboard
from core.lexicon.lexicon_ru import LEXICON_RU
from core.services.services import bitrix_send_data
from core.utils.statesform import FSMGeneralMessageForm

router: Router = Router()


# Этот хэндлер будет реагировать на отправку телефонного номера (только если НЕ в состоянии FSMGeneralMessageForm)
@router.message(F.contact, ~StateFilter(FSMGeneralMessageForm.get_phone))
async def call_request_answer(message: Message):
    await message.answer(
        text=LEXICON_RU["call_request_answer_text"], reply_markup=create_url_keyboard()
    )


# Этот хэндлер будет реагировать на любые сообщения пользователя,
# не предусмотренные логикой работы бота (только если НЕ в состоянии FSMGeneralMessageForm)
@router.message(~StateFilter(FSMGeneralMessageForm.get_phone))
async def other_fsm_answer(message: Message, state: FSMContext, bot: Bot):
    # Сохраняем сообщение пользователя
    await state.update_data(message=message.text, name=message.from_user.first_name)

    # Отправляем сообщение с запросом телефона
    msg = await message.answer(
        text=LEXICON_RU["general_message_text"],
        reply_markup=create_call_request_keyboard(),
    )

    # Сохраняем ID сообщения для последующего удаления
    await state.update_data(old_message_id=msg.message_id)

    # Устанавливаем состояние ожидания телефона
    await state.set_state(FSMGeneralMessageForm.get_phone)


# Этот хэндлер будет собирать дополнительные текстовые сообщения пользователя в ожидании телефона
@router.message(F.text, StateFilter(FSMGeneralMessageForm.get_phone))
async def process_additional_messages(message: Message, state: FSMContext):
    data = await state.get_data()
    # Добавляем новое сообщение к уже существующим
    current_message = data.get("message", "")
    updated_message = (
        f"{current_message}\n{message.text}" if current_message else message.text
    )
    await state.update_data(message=updated_message)


# Этот хэндлер будет срабатывать на отправку телефона для общего сообщения
@router.message(F.contact, StateFilter(FSMGeneralMessageForm.get_phone))
async def process_general_phone_sent(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    data["phone"] = message.contact.phone_number
    old_message_id = data.get("old_message_id")

    # Удаляем сообщение с запросом телефона
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()
    await state.clear()

    # Отправляем данные в CRM
    await bitrix_send_data(
        tg_login=message.from_user.username,
        tg_id=message.from_user.id,
        data=data,
        method="general",
    )

    await message.answer(
        text=LEXICON_RU["call_request_answer_text"],
        reply_markup=create_url_keyboard(back=True),
    )
