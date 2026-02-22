import asyncio
import csv
import random
import re
from typing import List, Tuple
from urllib.parse import quote

import aiofiles
import aiohttp
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InputMediaPhoto
from aiohttp.client_exceptions import ContentTypeError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Query

from core.db import methods
from core.keyboards.keyboard_inline import create_sub_auto_keyboard
from core.lexicon.lexicon_ru import (
    LEXICON_CAPTION_RU,
    LEXICON_EN_RU,
    LEXICON_RU,
    LEXICON_RU_CSV,
)


# Функция нормализации строк для сравнения
def normalize_string(text: str) -> str:
    """
    Нормализует строку: приводит к верхнему регистру и оставляет только буквы и цифры.
    Удаляет слово "AUTOMOTIVE" для корректного сравнения марок (например, "FISKER" == "FISKER AUTOMOTIVE").
    """
    if not text:
        return ""
    # Удаляем слово "AUTOMOTIVE" (с учетом регистра и возможных пробелов)
    text = re.sub(r"\s*AUTOMOTIVE\s*", "", text, flags=re.IGNORECASE)
    # Оставляем только буквы и цифры, приводим к верхнему регистру
    return re.sub(r"[^A-Za-z0-9]", "", text.upper())


# Функция получения json
async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()


# Функция получения url изображений
async def get_images(car: dict) -> list:
    urls = []
    url = car["Image URL"]
    async with aiohttp.ClientSession() as session:
        try:
            response = await fetch_json(session, url)
            image_count = int(response["imgCount"])
            for i in range(image_count):
                links = response["lotImages"][i]["link"]
                for link in links:
                    if link["isHdImage"] is True:
                        urls.append(link["url"].strip())
        except (ContentTypeError, KeyError):
            print(f"Изображения не найдены: {url}")
    return urls[0:9]


# Функция фильтр получения данных по марке, моделе, году из сsv
async def filter_by_make_and_model(row, make, model, year):
    """
    Фильтрует данные по марке, модели и году.
    - Если model == "ALL_MODELS" или "ALL MODELS", то выбираются все модели марки
    - Сравнение происходит после нормализации (верхний регистр, только буквы и цифры)
    """
    # Нормализуем значения из CSV
    normalized_csv_make = normalize_string(row["Make"])
    normalized_csv_model = normalize_string(row["Model Group"])

    # Нормализуем значения от пользователя
    normalized_make = normalize_string(make)
    normalized_model = normalize_string(model)

    # Проверяем марку
    make_match = normalized_csv_make == normalized_make

    # Проверяем модель: если выбрано "ALL_MODELS" или "ALL MODELS", пропускаем проверку модели
    # После нормализации оба варианта становятся "ALLMODELS"
    is_all_models = normalized_model == "ALLMODELS"
    model_match = is_all_models or (normalized_csv_model == normalized_model)

    # Проверяем год и дату продажи
    if year is None:
        # Если год не имеет значения, пропускаем проверку года
        year_match = row["Sale Date M/D/CY"] != "0"
    else:
        try:
            year_value = int(float(row["Year"])) if row.get("Year") else 0
        except (ValueError, TypeError):
            year_value = 0

        year_match = year_value in year and row["Sale Date M/D/CY"] != "0"

    return make_match and model_match and year_match


# Функция получения данных из сsv для показа
async def get_data(session: AsyncSession, tg_id: int, count: int = 6) -> List[Tuple]:
    data = await methods.get_damaged_car(session, tg_id)
    make = data.car_make
    model = data.car_model
    year = LEXICON_RU_CSV[data.car_year]
    odometer = LEXICON_RU_CSV[data.car_odometer] if data.car_odometer else None
    description = (
        LEXICON_RU_CSV[data.car_damage_description]
        if data.car_damage_description
        else None
    )

    cars = []
    async with aiofiles.open("core/data/csv/salesdata.csv") as csvfile:
        shuffled_list = []
        csv_list = await csvfile.readlines()
        shuffled_list.append(csv_list[0])
        csv_list = csv_list[1:]
        random.shuffle(csv_list)
        shuffled_list.extend(csv_list)
        reader = csv.DictReader(shuffled_list)
        for row in reader:
            if odometer and description:
                if (
                    await filter_by_make_and_model(row, make, model, year)
                    and float(row["Odometer"]) >= odometer[0]
                    and float(row["Odometer"]) <= odometer[1]
                    and row["Damage Description"] == description
                ):
                    car_images_urls = await get_images(row)
                    if car_images_urls:
                        cars.append((row, car_images_urls))
                        if len(cars) >= count:
                            break
            elif odometer:
                if (
                    await filter_by_make_and_model(row, make, model, year)
                    and float(row["Odometer"]) >= odometer[0]
                    and float(row["Odometer"]) <= odometer[1]
                ):
                    car_images_urls = await get_images(row)
                    if car_images_urls:
                        cars.append((row, car_images_urls))
                        if len(cars) >= count:
                            break
            elif description:
                if (
                    await filter_by_make_and_model(row, make, model, year)
                    and row["Damage Description"] == description
                ):
                    car_images_urls = await get_images(row)
                    if car_images_urls:
                        cars.append((row, car_images_urls))
                        if len(cars) >= count:
                            break
            else:
                if await filter_by_make_and_model(row, make, model, year):
                    car_images_urls = await get_images(row)
                    if car_images_urls:
                        cars.append((row, car_images_urls))
                        if len(cars) >= count:
                            break
    return cars[:count]


# Функция получения данных из сsv для рассылки
async def get_subscription_data(
    session: AsyncSession, data: Query = None, count: int = 3
) -> List[Tuple]:
    make = data.car_make
    model = data.car_model
    year = LEXICON_RU_CSV[data.car_year]
    odometer = LEXICON_RU_CSV[data.car_odometer] if data.car_odometer else None
    description = (
        LEXICON_RU_CSV[data.car_damage_description]
        if data.car_damage_description
        else None
    )
    car_id = data.id
    car_vins = data.subscription_vins if data.subscription_vins else []

    cars = []
    async with aiofiles.open("core/data/csv/salesdata.csv") as csvfile:
        shuffled_list = []
        csv_list = await csvfile.readlines()
        shuffled_list.append(csv_list[0])
        csv_list = csv_list[1:]
        random.shuffle(csv_list)
        shuffled_list.extend(csv_list)
        reader = csv.DictReader(shuffled_list)
        for row in reader:
            if row["VIN"] in car_vins:
                continue
            else:
                if odometer and description:
                    if (
                        await filter_by_make_and_model(row, make, model, year)
                        and float(row["Odometer"]) >= odometer[0]
                        and float(row["Odometer"]) <= odometer[1]
                        and row["Damage Description"] == description
                    ):
                        car_images_urls = await get_images(row)
                        if car_images_urls:
                            cars.append((row, car_images_urls))
                            car_vin = row["VIN"]
                            await methods.add_vins(session, car_id, car_vin)
                            if len(cars) >= count:
                                break
                elif odometer:
                    if (
                        await filter_by_make_and_model(row, make, model, year)
                        and float(row["Odometer"]) >= odometer[0]
                        and float(row["Odometer"]) <= odometer[1]
                    ):
                        car_images_urls = await get_images(row)
                        if car_images_urls:
                            cars.append((row, car_images_urls))
                            car_vin = row["VIN"]
                            await methods.add_vins(session, car_id, car_vin)
                            if len(cars) >= count:
                                break
                elif description:
                    if (
                        await filter_by_make_and_model(row, make, model, year)
                        and row["Damage Description"] == description
                    ):
                        car_images_urls = await get_images(row)
                        if car_images_urls:
                            cars.append((row, car_images_urls))
                            car_vin = row["VIN"]
                            await methods.add_vins(session, car_id, car_vin)
                            if len(cars) >= count:
                                break
                else:
                    if await filter_by_make_and_model(row, make, model, year):
                        car_images_urls = await get_images(row)
                        if car_images_urls:
                            cars.append((row, car_images_urls))
                            car_vin = row["VIN"]
                            await methods.add_vins(session, car_id, car_vin)
                            if len(cars) >= count:
                                break
    return cars[:count]


# Функция подготовки альбома для отправки пользователю
async def make_media_group(car, first_name, number):
    year = car[0]["Year"]
    make = car[0]["Make"]
    model = car[0]["Model Detail"]
    color = (
        LEXICON_EN_RU["Color"][car[0]["Color"]]
        if car[0]["Color"] in LEXICON_EN_RU["Color"]
        else car[0]["Color"]
    )
    description = (
        LEXICON_EN_RU["Description"][car[0]["Damage Description"]]
        if car[0]["Damage Description"] in LEXICON_EN_RU["Description"]
        else car[0]["Damage Description"]
    )
    odometer = car[0]["Odometer"]
    engine = car[0]["Engine"]
    drive = (
        LEXICON_EN_RU["Drive"][car[0]["Drive"]]
        if car[0]["Drive"] in LEXICON_EN_RU["Drive"]
        else car[0]["Drive"]
    )
    transmission = (
        LEXICON_EN_RU["Transmission"][car[0]["Transmission"]]
        if car[0]["Transmission"] in LEXICON_EN_RU["Transmission"]
        else car[0]["Transmission"]
    )
    fuel_type = (
        LEXICON_EN_RU["Fuel Type"][car[0]["Fuel Type"]]
        if car[0]["Fuel Type"] in LEXICON_EN_RU["Fuel Type"]
        else car[0]["Fuel Type"]
    )
    sale_date = car[0]["Sale Date M/D/CY"]

    caption = LEXICON_CAPTION_RU["caption_text"](
        first_name,
        number,
        year,
        make,
        model,
        color,
        description,
        odometer,
        engine,
        drive,
        transmission,
        fuel_type,
        sale_date,
    )
    media_group = [InputMediaPhoto(media=car[1][0], caption=caption)]
    media_group.extend([InputMediaPhoto(media=file_id) for file_id in car[1][1:]])
    return media_group


# Функция подготовки альбома для рассылки пользователю
async def subscription_sender(sessionmaker: AsyncSession, bot: Bot):
    async with sessionmaker() as session:
        cars_subs = await methods.get_subs_cars_id(session)
        for sub in cars_subs:
            try:
                tg_id, tg_name = await methods.get_subs_user_id(session, sub.tg_id)
                data = await get_subscription_data(session=session, data=sub)
            except Exception:
                continue
            if len(data) > 0:
                data_buttons = []
                number = 1

            for car in data:
                media_group = await make_media_group(car, tg_name, number)
                try:
                    await bot.send_media_group(tg_id, media=media_group)
                    data_buttons.append(
                        (
                            f"✅ Авто № {number}",
                            f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                        )
                    )
                    number += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    await bot.send_media_group(tg_id, media=media_group)
                    data_buttons.append(
                        (
                            f"✅ Авто № {number}",
                            f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                        )
                    )
                    number += 1
                except TelegramForbiddenError:
                    await methods.delete_user(session, tg_id)
                    continue
                except TelegramBadRequest:
                    continue
                else:
                    await asyncio.sleep(1)

            if len(data) > 0:
                try:
                    await bot.send_message(
                        tg_id,
                        text=LEXICON_RU["positive_result_sender_text"],
                        reply_markup=create_sub_auto_keyboard(data_buttons),
                    )
                except TelegramForbiddenError:
                    await methods.delete_user(session, tg_id)
                    continue
                except TelegramBadRequest:
                    continue
            else:
                try:
                    await bot.send_message(
                        tg_id,
                        text=LEXICON_RU["negative_result_sender_text"](
                            sub.date.date(), sub.car_make, sub.car_model
                        ),
                    )
                except TelegramForbiddenError:
                    await methods.delete_user(session, tg_id)
                    continue
                except TelegramBadRequest:
                    continue


# Функция загрузки данных в csv
async def download_csv(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            filepath = "core/data/csv/salesdata.csv"
            async with aiofiles.open(filepath, "wb") as f:
                while chunk := await response.content.read(1024):
                    await f.write(chunk)


# Функция формирования url для битрикса
async def make_bitrix_url(tg_login: str, tg_id: int, data: dict, method: str) -> str:
    if method == "advice":
        # URL-кодируем поля для корректной передачи спецсимволов
        name = quote(data.get("name", ""), safe="")
        year = quote(str(data.get("year", "")), safe="")
        budjet = quote(str(data.get("budjet", "")), safe="")
        car_type = quote(str(data.get("type", "")), safe="")
        buytime = quote(str(data.get("buytime", "")), safe="")

        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]=Консультация (TgBot)&"
            f"FIELDS[NAME]={name}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
            f"FIELDS[COMMENTS]=Год: {year} | "
            f"Бюджет: {budjet} | "
            f"Тип: {car_type} | "
            f"Сроки: {buytime}"
        )

    elif method == "unbroken":
        # URL-кодируем поля для корректной передачи спецсимволов
        name = quote(data.get("name", ""), safe="")
        model = quote(data.get("model", ""), safe="")
        year = quote(str(data.get("year", "")), safe="")

        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]={model} (TgBot)&"
            f"FIELDS[NAME]={name}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
            f"FIELDS[COMMENTS]=Год: {year} | "
            f"Модель: {model}"
        )

    elif method == "damaged":
        lot_description = data.get("lot").split("-")
        lot_number = lot_description[0][7:]
        make = lot_description[1]
        model = lot_description[2]

        # URL-кодируем поля для корректной передачи спецсимволов
        name = quote(data.get("name", ""), safe="")
        title = quote(f"{make} {model} (TgBot)", safe="")

        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]={title}&"
            f"FIELDS[NAME]={name}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
            f"FIELDS[COMMENTS]=Лот №: {lot_number} | "
            f"https://www.copart.com/lot/{lot_number}/"
        )

    elif method == "general":
        # URL-кодируем сообщение для корректной передачи переносов строк и спецсимволов
        name = quote(data.get("name", ""), safe="")
        encoded_message = quote(data.get("message", ""), safe="")
        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]=Сообщение TgBot (A4E)&"
            f"FIELDS[NAME]={name}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
            f"FIELDS[COMMENTS]=Сообщение: {encoded_message}"
        )

    return url


# Функция отправки лидов в битрикс
async def bitrix_send_data(tg_login: str, tg_id: int, data: dict, method: str) -> None:
    url = await make_bitrix_url(tg_login, tg_id, data, method)
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as resp:
            response = await resp.text()
            return response
