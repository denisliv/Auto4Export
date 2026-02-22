from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from core.lexicon.lexicon_ru import (LEXICON_ADMIN_BUTTONS_RU,
                                     LEXICON_BUTTONS_RU)


# Функция, генерирующая клавиатуру для отправки номера телефона
def create_call_request_keyboard() -> ReplyKeyboardMarkup:
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(KeyboardButton(text=LEXICON_BUTTONS_RU['phone_number_button'], request_contact=True))
    return kb_builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


# Функция, генерирующая клавиатуру для администратора
def create_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU['statistics_button']),
                   KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU['newsletter_button']),
                   KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU['exit_button']),
                   width=2)
    return kb_builder.as_markup(resize_keyboard=True)
