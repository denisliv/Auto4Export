from aiogram import Bot, Router
from aiogram.filters import StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import methods
from core.keyboards.keyboard_inline import (create_choice_keyboard,
                                            create_url_keyboard)
from core.keyboards.keyboard_reply import create_call_request_keyboard
from core.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU
from core.services.services import bitrix_send_data
from core.utils.statesform import FSMFillUnbrokenForm

router: Router = Router()


# Этот хэндлер будет срабатывать на кнопку "Хочу без повреждений"
# и переводить бота в состояние ожидания ввода марки/модели
@router.callback_query(Text(text='let_without_damage_button'))
async def process_let_without_damage_button_press(callback: CallbackQuery, state: FSMContext):
    msg = await callback.message.edit_text(text='Укажите марку и модель 👇')
    await state.update_data(old_message_id=msg.message_id)
    await state.set_state(FSMFillUnbrokenForm.get_model)


# Этот хэндлер будет срабатывать, если введена марка/модель
# и переводить бота в состояние ожидания выбора года выпуска
@router.message(StateFilter(FSMFillUnbrokenForm.get_model))
async def process_model_print(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    old_message_id = data.get('old_message_id')
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()
    await message.answer(
        text='Выберите год выпуска 👇',
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU['year_buttons']
            )
        )
    await state.update_data(model=message.text)
    await state.set_state(FSMFillUnbrokenForm.get_year)


# Этот хэндлер будет срабатывать, если выбран год выпуска
# и переводить бота в состояние ожидания ввода имени
@router.callback_query(StateFilter(FSMFillUnbrokenForm.get_year))
async def process_year_buttons_press(callback: CallbackQuery, state: FSMContext):
    msg = await callback.message.edit_text(
            text='Укажите Ваше Имя.'
            )
    await state.update_data(year=callback.data)
    await state.update_data(old_message_id=msg.message_id)
    await state.set_state(FSMFillUnbrokenForm.get_name)


# Этот хэндлер будет срабатывать, если введено имя
# и переводить бота в состояние ожидания номера телефона
@router.message(StateFilter(FSMFillUnbrokenForm.get_name))
async def process_name_print(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    old_message_id = data.get('old_message_id')
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()
    msg = await message.answer(
            text=LEXICON_RU['choose_call_request_text'],
            reply_markup=create_call_request_keyboard()
            )
    await state.update_data(name=message.text)
    await state.update_data(old_message_id=msg.message_id)
    await state.set_state(FSMFillUnbrokenForm.get_phone)


# Этот хэндлер будет срабатывать, если указан номер телефона
# и выводить из машины состояний
@router.message(StateFilter(FSMFillUnbrokenForm.get_phone))
async def process_phone_sent(message: Message, bot: Bot, state: FSMContext, session: AsyncSession):
    try:
        await state.update_data(phone=message.contact.phone_number)
        data = await state.get_data()
        old_message_id = data.get('old_message_id')
        await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
        await message.delete()
        await methods.set_last_update(session, message.contact.user_id)
        await methods.add_unbroken_car(session, message.contact.user_id, data)

        await bitrix_send_data(tg_login=message.from_user.username,
                               tg_id=message.from_user.id,
                               data=data,
                               method='unbroken')

        await state.clear()
        await message.answer(text=LEXICON_RU['call_request_answer_text'],
                             reply_markup=create_url_keyboard(back=True))
    except AttributeError:
        await message.delete()
        await message.answer(text='Это не номер телефона. Нажмите <b>Отправить номер телефона</b> на клавиатуре снизу')
        await state.set_state(FSMFillUnbrokenForm.get_phone)
