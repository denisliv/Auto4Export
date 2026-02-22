from aiogram import Router
from aiogram.filters import StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import methods
from core.keyboards.keyboard_inline import create_choice_keyboard
from core.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU
from core.utils.statesform import FSMFillDamagedForm

router: Router = Router()


# Этот хэндлер будет срабатывать на кнопку "Выбрать марку/модель"
# и переводить бота в состояние ожидания выбора марки
@router.callback_query(
    Text(text=["damaged_button", "again_button", "damaged_sub_button"]),
    flags={"blocking": "blocking"},
)
async def process_damaged_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        text="Выберите марку 👇",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["make_buttons"], width=2
        ),
    )
    await state.set_state(FSMFillDamagedForm.get_make)


# Этот хэндлер будет срабатывать, если введена марка
# и переводить бота в состояние ожидания выбора модели
@router.callback_query(StateFilter(FSMFillDamagedForm.get_make))
async def process_make_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Выберите модель 👇",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["model_buttons"][callback.data], width=2
        ),
    )
    await state.update_data(make=callback.data)
    await state.set_state(FSMFillDamagedForm.get_model)


# Этот хэндлер будет срабатывать, если выбрана модель
# и переводить бота в состояние ожидания выбора года выпуска
@router.callback_query(StateFilter(FSMFillDamagedForm.get_model))
async def process_model_buttons_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Выберите год выпуска 👇",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["year_damaged_car_buttons"], width=1
        ),
    )
    await state.update_data(model=callback.data)
    await state.set_state(FSMFillDamagedForm.get_year)


# Этот хэндлер будет срабатывать, если выбран год выпуска
# и переводить бота в состояние ожидания выбора пробега
@router.callback_query(StateFilter(FSMFillDamagedForm.get_year))
async def process_drive_buttons_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Выберите желаемый пробег 👇",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["odometer_buttons"], width=1
        ),
    )
    await state.update_data(year=callback.data)
    await state.set_state(FSMFillDamagedForm.get_odometer)


# Этот хэндлер будет срабатывать, если выбран пробег
# и переводить бота в состояние ожидания выбора типа повреждения
# @router.callback_query(StateFilter(FSMFillDamagedForm.get_odometer))
# async def process_odometer_buttons_press(callback: CallbackQuery, state: FSMContext):
#    await callback.message.edit_text(
#        text='Выберите тип повреждения 👇',
#        reply_markup=create_choice_keyboard(
#            *LEXICON_FORM_BUTTONS_RU['description_buttons']
#            )
#        )
#    await state.update_data(odometer=callback.data)
#    await state.set_state(FSMFillDamagedForm.get_description)


# Этот хэндлер будет срабатывать, если выбран тип повреждения
# и выводить из машины состояний
@router.callback_query(StateFilter(FSMFillDamagedForm.get_odometer))
async def process_description_buttons_press(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    await state.update_data(odometer=callback.data)
    user_dict = await state.get_data()
    await methods.set_last_update(session, callback.from_user.id)
    await methods.add_damaged_car(session, callback.from_user.id, user_dict)
    await state.clear()
    await callback.message.edit_text(
        text=LEXICON_RU["result_text"],
        reply_markup=create_choice_keyboard(
            "result_true_button", "result_false_button"
        ),
    )
