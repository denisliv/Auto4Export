import asyncio
import csv
import logging
import os
import re
from collections.abc import AsyncIterator, Iterator
from itertools import islice
from pathlib import Path
from typing import List, Tuple
from urllib.parse import quote

import aiofiles
import aiohttp
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InputMediaPhoto
from aiohttp.client_exceptions import ContentTypeError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Query

from core.config_data.config import load_config
from core.db import methods, sales_lots
from core.keyboards.keyboard_inline import create_sub_auto_keyboard
from core.lexicon.lexicon_ru import (
    LEXICON_CAPTION_RU,
    LEXICON_EN_RU,
    LEXICON_RU,
    LEXICON_RU_CSV,
)

logger = logging.getLogger(__name__)

# Файл фида на томе csv_data: переживает пересоздание контейнера, поэтому из
# него восстанавливается снимок, если база пуста, а Copart недоступен.
CSV_PATH = Path("core/data/csv/salesdata.csv")
CSV_ENCODING = "utf-8"
# Размер куска при записи ответа Copart на диск.
DOWNLOAD_CHUNK_BYTES = 1024
# Предел на всю загрузку фида. Столько же aiohttp ставит по умолчанию; значение
# вынесено явно, чтобы зависший CDN не держал задачу планировщика вечно.
DOWNLOAD_TIMEOUT_SECONDS = 300
# Сколько строк CSV разбирается за один заход в рабочем потоке при загрузке.
SNAPSHOT_BATCH_ROWS = 5000
# Сколько кандидатов подгружается из базы за раз, пока ищем лоты с фото.
IMAGE_LOOKUP_CHUNK = 12
# Так normalize_string записывает кнопку «все модели».
ALL_MODELS_NORM = "ALLMODELS"

HTTP_OK = 200

# Входящий вебхук Bitrix24 для создания лидов. Секрет: живёт только в .env,
# в код и в git не попадает. Хвостовой слэш допускается — так Bitrix его и
# показывает при выпуске вебхука.
BITRIX_LEAD_ADD_URL = (
    f"{load_config().tg_bot.bitrix_webhook_url.rstrip('/')}/crm.lead.add.json"
)


class FeedDownloadError(Exception):
    """The Copart feed answered with something that is not a usable snapshot."""


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
            # Итерируем по фактическому массиву lotImages, а не по imgCount,
            # т.к. imgCount может быть больше длины lotImages (несогласованность API)
            lot_images = response.get("lotImages", [])
            for image_data in lot_images:
                links = image_data.get("link", [])
                if not isinstance(links, list):
                    links = [links] if links else []
                for link in links:
                    if isinstance(link, dict) and link.get("isHdImage") is True:
                        url_str = link.get("url", "").strip()
                        if url_str:
                            urls.append(url_str)
        except (ContentTypeError, KeyError, IndexError):
            print(f"Изображения не найдены: {url}")
    return urls[0:9]


# Фильтры поиска из заявки клиента, в том виде, в каком их понимает снимок
def _search_filters(order) -> dict:
    """Translate one damaged-car order into snapshot filters.

    Make and model are compared after `normalize_string`, the same function
    that normalised the snapshot when it was loaded, so "FISKER" still finds
    "FISKER AUTOMOTIVE". The "all models" button normalises to ALLMODELS and
    lifts the model filter altogether.

    Args:
        order: A `DamagedCarOrders` row.

    Returns:
        Keyword arguments for `sales_lots.candidate_ids`.
    """
    model_norm = normalize_string(order.car_model)
    odometer = LEXICON_RU_CSV[order.car_odometer] if order.car_odometer else None
    description = (
        LEXICON_RU_CSV[order.car_damage_description]
        if order.car_damage_description
        else None
    )
    return {
        "make_norm": normalize_string(order.car_make),
        "model_norm": None if model_norm == ALL_MODELS_NORM else model_norm,
        # None — «год не имеет значения»: проверяется только дата торгов.
        "years": LEXICON_RU_CSV[order.car_year],
        "odometer": odometer or None,
        "description": description or None,
    }


# Кандидаты в случайном порядке, у которых нашлись фото
async def _iter_cars_with_images(
    session: AsyncSession, order, exclude_vins=()
) -> AsyncIterator[Tuple[dict, list]]:
    """Yield matching lots that have photos, in random order.

    The same draw as before: every match in random order, checked for photos
    one by one until the caller has enough. Only the ids of the matches are
    held; rows are fetched a few at a time as the check reaches them.

    Args:
        session: Session to query through.
        order: A `DamagedCarOrders` row.
        exclude_vins: VINs this subscriber has already been sent.

    Yields:
        Pairs of row and its HD image URLs.
    """
    ids = await sales_lots.candidate_ids(
        session, **_search_filters(order), exclude_vins=exclude_vins
    )
    for start in range(0, len(ids), IMAGE_LOOKUP_CHUNK):
        rows = await sales_lots.rows_by_ids(
            session, ids[start : start + IMAGE_LOOKUP_CHUNK]
        )
        for row in rows:
            car_images_urls = await get_images(row)
            if car_images_urls:
                yield row, car_images_urls


# Функция получения данных из снимка Copart для показа
async def get_data(session: AsyncSession, tg_id: int, count: int = 6) -> List[Tuple]:
    data = await methods.get_damaged_car(session, tg_id)
    cars = []
    async for car in _iter_cars_with_images(session, data):
        cars.append(car)
        if len(cars) >= count:
            break
    return cars[:count]


# Функция получения данных из снимка Copart для рассылки
async def get_subscription_data(
    session: AsyncSession, data: Query = None, count: int = 3
) -> List[Tuple]:
    car_id = data.id
    car_vins = data.subscription_vins if data.subscription_vins else []

    cars = []
    # add_vins коммитит после каждого VIN; открытого курсора здесь нет, так что
    # коммит посреди перебора ничему не мешает.
    async for row, car_images_urls in _iter_cars_with_images(
        session, data, exclude_vins=car_vins
    ):
        cars.append((row, car_images_urls))
        await methods.add_vins(session, car_id, row["VIN"])
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
                except TelegramNetworkError:
                    await asyncio.sleep(5)
                    try:
                        await bot.send_media_group(tg_id, media=media_group)
                        data_buttons.append(
                            (
                                f"✅ Авто № {number}",
                                f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
                            )
                        )
                        number += 1
                    except Exception:
                        continue
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


# Функция проверки файла фида перед тем, как ему поверить
def validate_snapshot_file(path: Path) -> None:
    """Check that a file looks like the Copart feed before it is trusted.

    Reads the header and one data row rather than the whole file: an error
    page, an empty answer or a renamed column all show in the first two lines.

    Args:
        path: The file to check.

    Raises:
        FeedDownloadError: When the file is empty, carries no data rows, or
            lacks a column the bot reads.
    """
    with path.open("r", encoding=CSV_ENCODING) as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader, None)
        if not header:
            raise FeedDownloadError("Copart feed is empty")
        missing = [name for name in sales_lots.CSV_COLUMNS if name not in header]
        if missing:
            raise FeedDownloadError(f"Copart feed lacks columns: {missing}")
        if next(reader, None) is None:
            raise FeedDownloadError("Copart feed has no data rows")


def _parse_year(row: dict) -> int:
    # Как прежний фильтр: год через float, нечитаемый — 0, и такой лот не
    # попадает ни в один диапазон лет.
    try:
        return int(float(row["Year"])) if row.get("Year") else 0
    except (ValueError, TypeError):
        return 0


def _parse_odometer(row: dict) -> float | None:
    # Нечитаемый пробег раньше ронял весь поиск через float(); теперь такой лот
    # просто не проходит фильтр по пробегу.
    try:
        return float(row["Odometer"])
    except (KeyError, TypeError, ValueError):
        return None


def to_snapshot_record(row: dict) -> tuple:
    """Turn one CSV row into the tuple the snapshot table is loaded with.

    The CSV text goes in verbatim. The values after it are computed exactly as
    the old in-Python filter computed them, with the same `normalize_string`,
    so a search matches the lots it matched before.

    Args:
        row: One row as csv.DictReader produced it.

    Returns:
        Values in `sales_lots.COPY_COLUMNS` order.
    """
    text = tuple(row.get(name) for name in sales_lots.CSV_COLUMNS)
    return text + (
        normalize_string(row.get("Make")),
        normalize_string(row.get("Model Group")),
        _parse_year(row),
        _parse_odometer(row),
    )


def _read_snapshot_batch(reader: Iterator[dict], size: int) -> list:
    """Parse the next `size` rows. Runs in a worker thread."""
    return [to_snapshot_record(row) for row in islice(reader, size)]


async def _iter_snapshot_batches(reader: Iterator[dict]) -> AsyncIterator[list]:
    """Yield batches of records, parsing each batch off the event loop."""
    while True:
        batch = await asyncio.to_thread(
            _read_snapshot_batch, reader, SNAPSHOT_BATCH_ROWS
        )
        if not batch:
            return
        yield batch


# Функция загрузки файла фида в снимок в базе
async def load_snapshot(engine: AsyncEngine, path: Path) -> int:
    """Replace the snapshot in the database with the contents of this CSV.

    Args:
        engine: Engine to load through.
        path: A feed file that already passed `validate_snapshot_file`.

    Returns:
        How many rows the snapshot now holds.
    """
    with path.open("r", encoding=CSV_ENCODING) as csvfile:
        reader = csv.DictReader(csvfile)
        async with engine.begin() as conn:
            loaded = await sales_lots.replace_snapshot(
                conn, _iter_snapshot_batches(reader)
            )
    logger.info("Снимок Copart загружен в базу: %d строк", loaded)
    return loaded


# Функция восстановления снимка из файла, если база пуста
async def ensure_snapshot_loaded(engine: AsyncEngine) -> None:
    """Rebuild the snapshot from the feed file when the table is empty.

    The file lives on the csv_data volume and outlives the container, so a
    restart while Copart is unreachable still leaves customers something to
    search instead of an empty catalogue until the next download.

    Args:
        engine: Engine to load through.
    """
    async with engine.connect() as conn:
        if await sales_lots.count_snapshot(conn) > 0:
            return

    if not CSV_PATH.exists():
        logger.warning(
            "Снимок Copart пуст, а файла фида нет: поиск заработает после загрузки"
        )
        return

    await asyncio.to_thread(validate_snapshot_file, CSV_PATH)
    logger.info("Снимок Copart пуст, восстанавливаем из файла на томе")
    await load_snapshot(engine, CSV_PATH)


# Функция загрузки фида Copart и обновления снимка
async def download_csv(url: str, engine: AsyncEngine) -> None:
    """Download the Copart feed and make it the current snapshot.

    Written to a temporary file and checked before it replaces anything: an
    error page or an empty answer must not take the place of a good feed.
    Customers keep searching the previous snapshot until the new one commits.

    Args:
        url: Feed URL. It carries the Copart access key, so it never goes into
            a log line or an exception message.
        engine: Engine the snapshot is loaded through.

    Raises:
        FeedDownloadError: When Copart answers with an error or the file is not
            a usable feed. The previous file and snapshot stay in place.
    """
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CSV_PATH.with_name(f"{CSV_PATH.name}.tmp")
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != HTTP_OK:
                    message = f"Copart feed answered HTTP {response.status}"
                    raise FeedDownloadError(message)
                async with aiofiles.open(tmp_path, "wb") as f:
                    while chunk := await response.content.read(DOWNLOAD_CHUNK_BYTES):
                        await f.write(chunk)
        await asyncio.to_thread(validate_snapshot_file, tmp_path)
        os.replace(tmp_path, CSV_PATH)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    await load_snapshot(engine, CSV_PATH)


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
            f"{BITRIX_LEAD_ADD_URL}?"
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
            f"{BITRIX_LEAD_ADD_URL}?"
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
            f"{BITRIX_LEAD_ADD_URL}?"
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
            f"{BITRIX_LEAD_ADD_URL}?"
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
