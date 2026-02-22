import asyncio

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import methods
from core.filters.filters import IsActBookmarkCallbackData, IsDelBookmarkCallbackData
from core.keyboards.keyboard_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
    create_edit_keyboard,
    create_subs_keyboard,
    create_url_keyboard,
)
from core.keyboards.keyboard_reply import create_call_request_keyboard
from core.lexicon.lexicon_ru import LEXICON_RU
from core.services.services import bitrix_send_data, get_data, make_media_group
from core.utils.statesform import FSMPhoneForm

router: Router = Router()


# Этот хэндлер будет срабатывать на команду "/start" -
# отправлять пользователю приветственное сообщение, вносить его в БД
# а также предоставлять пользователю инлайн-кнопки с выбором
@router.message(Command(commands=["start"]))
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    # Удаляем сообщение с кнопкой запроса телефона, если оно есть
    data = await state.get_data()
    old_message_id = data.get("old_message_id")
    if old_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
        except TelegramBadRequest:
            pass  # Сообщение уже удалено или недоступно

    await methods.add_user(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    await message.answer(
        text=LEXICON_RU["/start_text"](message.from_user.first_name),
        reply_markup=create_choice_keyboard(
            "choose_a_car_button", "contact_button", "more_information_button", width=1
        ),
    )
    await state.clear()


# Этот хэндлер будет срабатывать на команду "/help"
# и отправлять пользователю сообщение со списком доступных команд в боте
@router.message(Command(commands=["help"]))
async def cmd_help(message: Message):
    await message.answer(text=LEXICON_RU["/help_text"])


# Этот хэндлер будет срабатывать на команду "/subscription"
@router.message(Command(commands=["subscription"]))
async def cmd_subscription(message: Message, session: AsyncSession):
    cars = await methods.user_active_car(session, message.from_user.id)
    if cars:
        await message.answer(
            text=LEXICON_RU["yes_subs_car_text"],
            reply_markup=create_subs_keyboard(cars),
        )

    else:
        await message.answer(
            text=LEXICON_RU["no_subs_car_text"],
            reply_markup=create_choice_keyboard("damaged_sub_button", "back_button"),
        )


# Этот хэндлер будет срабатывать на инлайн-кнопку Назад
@router.callback_query(Text(text="sub_again_button"))
async def process_sub_again_button_press(
    callback: CallbackQuery, session: AsyncSession
):
    cars = await methods.user_active_car(session, callback.from_user.id)
    if cars:
        await callback.message.edit_text(
            text=LEXICON_RU["yes_subs_car_text"],
            reply_markup=create_subs_keyboard(cars),
        )

    else:
        await callback.message.edit_text(
            text=LEXICON_RU["no_subs_car_text"],
            reply_markup=create_choice_keyboard("damaged_sub_button", "back_button"),
        )


# Этот хэндлер будет срабатывать на инлайн-кнопку Редактировать
@router.callback_query(Text(text="edit_subs_button"))
async def process_edit_button_press(callback: CallbackQuery, session: AsyncSession):
    cars = await methods.user_active_car(session, callback.from_user.id)
    if cars:
        await callback.message.edit_text(
            text=LEXICON_RU["edit_sub_text"], reply_markup=create_edit_keyboard(cars)
        )


# Этот хэндлер будет срабатывать на выбор автомобиля в подписках
@router.callback_query(IsActBookmarkCallbackData())
async def process_car_press(callback: CallbackQuery, session: AsyncSession):
    car = await methods.user_car_description(session, int(callback.data[3:]))
    await callback.answer()
    await callback.message.edit_text(
        text=f"Вы подписаны:\r\n\n"
        f"▪ Модель: {car.car_make} {car.car_model}\r\n"
        f"▪ Год выпуска: {car.car_year}\r\n"
        f"▪ Пробег: {car.car_odometer}\r\n",
        # f'▪ Тип повреждения: {car.car_damage_description}\r\n',
        reply_markup=create_choice_keyboard("sub_again_button"),
    )


# Этот хэндлер будет срабатывать на выбор автомобиля в режими редактирования
@router.callback_query(IsDelBookmarkCallbackData())
async def process_edit_car_press(callback: CallbackQuery, session: AsyncSession):
    await methods.user_car_edit_description(
        session, callback.from_user.id, int(callback.data[3:])
    )
    cars = await methods.user_active_car(session, callback.from_user.id)
    if cars:
        await callback.message.edit_text(
            text=LEXICON_RU["yes_subs_car_text"],
            reply_markup=create_subs_keyboard(cars),
        )

    else:
        await callback.message.edit_text(
            text=LEXICON_RU["no_subs_car_text"],
            reply_markup=create_choice_keyboard("damaged_sub_button", "back_button"),
        )
    await callback.answer()


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Важная информация"
@router.callback_query(Text(text="more_information_button"))
async def process_more_information_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["choose_more_information_text"],
        reply_markup=create_choice_keyboard(
            "choose_a_car_button", "remind_later_button", "back_button"
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Контакты"
@router.callback_query(Text(text="contact_button"))
async def process_contact_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["contacts_text"], reply_markup=create_url_keyboard(back=True)
    )


# Этот хэндлер будет срабатывать на кнопку "Назад"
# и предоставлять пользователю инлайн-кнопки с выбором
@router.callback_query(Text(text="back_button"))
async def procces_back_button_press(callback: CallbackQuery):
    await callback.message.edit_text(
        text=LEXICON_RU["/start_text"](callback.from_user.first_name),
        reply_markup=create_choice_keyboard(
            "choose_a_car_button", "contact_button", "more_information_button", width=1
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Подобрать авто"
@router.callback_query(Text(text="choose_a_car_button"))
async def process_choose_a_car_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        text=LEXICON_RU["choose_a_car_text"],
        reply_markup=create_choice_keyboard("damaged_button", "advice_button", width=1),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Подобрать авто"
# @router.callback_query(Text(text='choose_a_car_button'))
# async def process_choose_a_car_press(callback: CallbackQuery):
#    await callback.answer()
#    await callback.message.answer(
#        text=LEXICON_RU['choose_a_car_text'],
#        reply_markup=create_choice_keyboard(
#                    'knowing_button',
#                    'advice_button',
#                    width=1
#                )
#            )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Я знаю что хочу"
# @router.callback_query(Text(text='knowing_button'))
# async def process_knowing_press(callback: CallbackQuery):
#    await callback.message.edit_text(
#        text=LEXICON_RU['knowing_text'],
#        reply_markup=create_choice_keyboard(
#                    'damaged_button',
#                    'without_damage_button',
#                    'back_button',
#                    width=1
#                )
#            )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Без повреждений"
# @router.callback_query(Text(text='without_damage_button'))
# async def process_without_damage_press(callback: CallbackQuery):
#    await callback.message.edit_text(
#        text=LEXICON_RU['without_damage_text'](callback.from_user.first_name),
#        reply_markup=create_choice_keyboard(
#                    'damaged_button',
#                    'let_without_damage_button',
#                    'back_button',
#                    width=1
#                )
#            )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Оставить номер телефона"
@router.callback_query(Text(text="call_request_button"))
async def process_call_request_press(callback: CallbackQuery):
    await callback.message.answer(
        text=LEXICON_RU["choose_call_request_text"],
        reply_markup=create_call_request_keyboard(),
    )
    await callback.answer()


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Напомнить позже"
@router.callback_query(Text(text=["remind_later_button"]))
async def process_remind_later_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["remind_later_text"],
        reply_markup=create_url_keyboard(back=True),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Да, хочу"
@router.callback_query(
    Text(text="result_true_button"), flags={"long_operation": "typing"}
)
async def process_result_true_press(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    await callback.answer(
        text="Обратите внимание, обработка запроса может занимать до 30 секунд",
        show_alert=True,
    )
    await callback.message.delete()
    data = await get_data(session=session, tg_id=callback.from_user.id)
    if len(data) > 0:
        data_buttons = []
        number = 1

        for car in data[:3]:
            media_group = await make_media_group(
                car, callback.from_user.first_name, number
            )
            try:
                await callback.message.answer_media_group(media=media_group)
                data_buttons.append(
                    (
                        f"✅ Авто № {number}",
                        f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                    )
                )
                number += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await callback.message.answer_media_group(media=media_group)
                data_buttons.append(
                    (
                        f"✅ Авто № {number}",
                        f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                    )
                )
                number += 1
            except TelegramNetworkError:
                await asyncio.sleep(5)
                try:
                    await callback.message.answer_media_group(media=media_group)
                    data_buttons.append(
                        (
                            f"✅ Авто № {number}",
                            f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                        )
                    )
                    number += 1
                except Exception:
                    continue
            except TelegramBadRequest:
                continue
            else:
                await asyncio.sleep(1)

        await state.update_data(else_data=data[3:])
        await state.update_data(old_data_buttons=data_buttons)
        await state.update_data(number=number)

        if len(data) > 3:
            await callback.message.answer(
                text=LEXICON_RU["result_true_press_text"],
                reply_markup=create_auto_keyboard(data_buttons, else_car=True),
            )
        else:
            await callback.message.answer(
                text=LEXICON_RU["result_true_press_text"],
                reply_markup=create_auto_keyboard(data_buttons, else_car=False),
            )
    else:
        await callback.message.answer(
            text=LEXICON_RU["nothing_found_text"],
            reply_markup=create_choice_keyboard("again_button"),
        )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Еще варианты по текущему запросу"
@router.callback_query(Text(text="else_car_button"), flags={"long_operation": "typing"})
async def process_else_press(callback: CallbackQuery, state: FSMContext):
    await callback.answer(
        text="Обратите внимание, обработка запроса может занимать до 30 секунд",
        show_alert=True,
    )
    await callback.message.delete()
    else_data = await state.get_data()
    data = else_data.get("else_data")
    old_data_buttons = else_data.get("old_data_buttons")
    number = else_data.get("number")
    for car in data:
        media_group = await make_media_group(car, callback.from_user.first_name, number)
        try:
            await callback.message.answer_media_group(media=media_group)
            old_data_buttons.append(
                (
                    f"✅ Авто № {number}",
                    f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                )
            )
            number += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await callback.message.answer_media_group(media=media_group)
            old_data_buttons.append(
                (
                    f"✅ Авто № {number}",
                    f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                )
            )
            number += 1
        except TelegramNetworkError:
            await asyncio.sleep(5)
            try:
                await callback.message.answer_media_group(media=media_group)
                old_data_buttons.append(
                    (
                        f"✅ Авто № {number}",
                        f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                    )
                )
                number += 1
            except Exception:
                continue
        except TelegramBadRequest:
            continue
        else:
            await asyncio.sleep(1)
    await callback.message.answer(
        text=LEXICON_RU["result_true_press_text"],
        reply_markup=create_auto_keyboard(old_data_buttons, else_car=False),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки с выбором автомобиля
@router.callback_query(Text(startswith="Лот №:"))
async def process_auto_press(callback: CallbackQuery, state: FSMContext):
    data = {"name": callback.from_user.first_name, "lot": callback.data}
    if callback.from_user.username:
        await bitrix_send_data(
            tg_login=callback.from_user.username,
            tg_id=callback.from_user.id,
            data=data,
            method="damaged",
        )
        await callback.message.edit_text(
            text=LEXICON_RU["call_request_answer_text"],
            reply_markup=create_url_keyboard(back=True),
        )
    else:
        msg = await callback.message.answer(
            text=LEXICON_RU["choose_call_request_text"],
            reply_markup=create_call_request_keyboard(),
        )
        await state.update_data(old_message_id=msg.message_id)
        await state.update_data(data=data)
        await state.set_state(FSMPhoneForm.get_phone)

    await callback.answer()


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки с выбором автомобиля у пользователей без логина
@router.message(F.contact, StateFilter(FSMPhoneForm.get_phone))
async def process_phone_sent(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    data["phone"] = message.contact.phone_number
    old_message_id = data.get("old_message_id")
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()
    await state.clear()

    await bitrix_send_data(
        tg_login=message.from_user.username,
        tg_id=message.from_user.id,
        data=data,
        method="damaged",
    )

    await message.answer(
        text=LEXICON_RU["call_request_answer_text"],
        reply_markup=create_url_keyboard(back=True),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Подписаться на обновления"
@router.callback_query(Text(text=["subscription_button", "result_false_button"]))
async def process_subscription_button_press(
    callback: CallbackQuery, session: AsyncSession
):
    limit = 5
    count = limit - await methods.set_subscription(
        session, callback.from_user.id, limit
    )
    if count != 0:
        await callback.message.edit_text(
            text=LEXICON_RU["yes_subscription_text"](count),
            reply_markup=create_choice_keyboard("again_button", "back_button"),
        )
    else:
        await callback.message.edit_text(
            text=LEXICON_RU["no_subscription_text"](count),
            reply_markup=create_choice_keyboard("again_button", "back_button"),
        )
    await callback.answer()
