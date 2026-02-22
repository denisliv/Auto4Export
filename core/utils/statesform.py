from aiogram.fsm.state import State, StatesGroup


class FSMFillAdviceForm(StatesGroup):
    get_year = State()
    get_budjet = State()
    get_type = State()
    get_buytime = State()
    get_name = State()
    get_phone = State()


class FSMFillUnbrokenForm(StatesGroup):
    get_model = State()
    get_year = State()
    get_name = State()
    get_phone = State()


class FSMFillDamagedForm(StatesGroup):
    get_make = State()
    get_model = State()
    get_year = State()
    get_odometer = State()
    get_description = State()


class FSMAdminForm(StatesGroup):
    get_message = State()
    get_button = State()
    get_button_text = State()
    get_button_url = State()


class FSMPhoneForm(StatesGroup):
    get_phone = State()


class FSMGeneralMessageForm(StatesGroup):
    get_phone = State()