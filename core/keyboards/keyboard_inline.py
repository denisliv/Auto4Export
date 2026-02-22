from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.lexicon.lexicon_ru import LEXICON_ADMIN_BUTTONS_RU, LEXICON_BUTTONS_RU


# Функция, генерирующая клавиатуру для выбора пользователем дальнейшего шага
def create_choice_keyboard(*buttons: str, width: int = 2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU[button]
                if button in LEXICON_BUTTONS_RU
                else button,
                callback_data=button,
            )
            for button in buttons
        ],
        width=width,
    )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для выбора подписки
def create_subs_keyboard(cars: list) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()

    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=f"📅 {car.date.date()} ▪ {car.car_make} {car.car_model} ▪ {car.car_year} ▪ {car.car_odometer}",
                callback_data=f"act{car.id}",
            )
            for car in cars
        ],
        width=1,
    )

    kb_builder.row(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["edit_subs_button"],
            callback_data="edit_subs_button",
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["back_button"], callback_data="back_button"
        ),
        width=2,
    )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для редактирования подписки
def create_edit_keyboard(cars: list) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()

    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=f"❌ {car.date.date()} ▪ {car.car_make} {car.car_model} ▪ {car.car_year} ▪ {car.car_odometer}",
                callback_data=f"del{car.id}",
            )
            for car in cars
        ],
        width=1,
    )

    kb_builder.row(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["sub_again_button"],
            callback_data="sub_again_button",
        )
    )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для перехода на сайт
def create_url_keyboard(back=False, width=2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    if back:
        kb_builder.row(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["url_site_button"], url="https://a4e.by"
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["see_reviews_button"],
                url="https://www.google.com/search?client=firefox-b-d&q="
                "auto4export+%D0%BE%D1%82%D0%B7%D1%8B%D0%B2%D1%8B",
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_button"], callback_data="back_button"
            ),
            width=width,
        )
    else:
        kb_builder.row(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["url_site_button"], url="https://a4e.by"
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["see_reviews_button"],
                url="https://www.google.com/search?client=firefox-b-d&q="
                "auto4export+%D0%BE%D1%82%D0%B7%D1%8B%D0%B2%D1%8B",
            ),
            width=width,
        )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для выбора понравившегося автомобиля
def create_auto_keyboard(
    buttons: dict, width: int = 1, else_car: bool = True
) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    if else_car:
        kb_builder.row(
            *[
                InlineKeyboardButton(text=button[0], callback_data=button[1])
                for button in buttons
            ],
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["else_car_button"],
                callback_data="else_car_button",
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["again_button"], callback_data="again_button"
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["subscription_button"],
                callback_data="subscription_button",
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_button"], callback_data="back_button"
            ),
            width=width,
        )
    else:
        kb_builder.row(
            *[
                InlineKeyboardButton(text=button[0], callback_data=button[1])
                for button in buttons
            ],
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["again_button"], callback_data="again_button"
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["subscription_button"],
                callback_data="subscription_button",
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_button"], callback_data="back_button"
            ),
            width=width,
        )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для выбора понравившегося автомобиля при рассылке
def create_sub_auto_keyboard(buttons: dict, width: int = 1) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    kb_builder.row(
        *[
            InlineKeyboardButton(text=button[0], callback_data=button[1])
            for button in buttons
        ],
        width=width,
    )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для администраторов
def create_admin_keyboard(*buttons: str, width: int = 2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=LEXICON_ADMIN_BUTTONS_RU[button]
                if button in LEXICON_ADMIN_BUTTONS_RU
                else button,
                callback_data=button,
            )
            for button in buttons
        ],
        width=width,
    )
    return kb_builder.as_markup()
