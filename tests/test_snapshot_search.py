"""Search rules over the Copart snapshot, now that they run in SQL.

Each rule here is one the old in-Python filter enforced on the CSV. The point
of these tests is that moving the filter into the database changed where it
runs, not which lots a customer is offered.
"""

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from core.db import sales_lots
from core.services import services
from core.services.services import _search_filters, to_snapshot_record

ANY_YEAR = "Не имеет значения"


def _row(**overrides) -> dict:
    """Build a CSV-shaped row with sane defaults for every column the bot reads."""
    row = {
        "Make": "TOYOTA",
        "Model Group": "CAMRY",
        "Model Detail": "CAMRY SE",
        "Year": "2022",
        "Odometer": "20000.0",
        "Sale Date M/D/CY": "20260901",
        "Lot number": "11111111",
        "VIN": "VIN0000000000001",
        "Color": "WHITE",
        "Engine": "2.5L 4",
        "Drive": "Front-wheel Drive",
        "Transmission": "AUTOMATIC",
        "Fuel Type": "GAS",
        "Damage Description": "FRONT END",
        "Image URL": "https://example.invalid/lot/11111111",
    }
    row.update(overrides)
    return row


def _order(**overrides) -> SimpleNamespace:
    """Build what a DamagedCarOrders row offers to the search."""
    order = {
        "car_make": "TOYOTA",
        "car_model": "CAMRY",
        "car_year": ANY_YEAR,
        "car_odometer": ANY_YEAR,
        "car_damage_description": ANY_YEAR,
    }
    order.update(overrides)
    return SimpleNamespace(**order)


async def _load(engine, *rows: dict) -> None:
    async def batches():
        yield [to_snapshot_record(row) for row in rows]

    async with engine.begin() as conn:
        await sales_lots.replace_snapshot(conn, batches())


async def _found(engine, order, exclude_vins=()) -> list[str]:
    """Return the lot numbers the search would draw for this order."""
    async with AsyncSession(engine) as session:
        ids = await sales_lots.candidate_ids(
            session, **_search_filters(order), exclude_vins=exclude_vins
        )
        rows = await sales_lots.rows_by_ids(session, ids)
    return sorted(row["Lot number"] for row in rows)


# --- марка и модель ---------------------------------------------------------


async def test_make_is_compared_after_normalisation(engine):
    # Copart пишет «FISKER AUTOMOTIVE», а на кнопке «FISKER»: normalize_string
    # выбрасывает AUTOMOTIVE, и это должно работать и в базе
    await _load(engine, _row(**{"Make": "FISKER AUTOMOTIVE", "Model Group": "OCEAN"}))

    assert await _found(engine, _order(car_make="Fisker", car_model="Ocean")) == ["11111111"]


async def test_model_punctuation_and_case_do_not_matter(engine):
    await _load(engine, _row(**{"Model Group": "C-HR"}))

    assert await _found(engine, _order(car_model="c hr")) == ["11111111"]


async def test_other_model_of_the_same_make_is_not_offered(engine):
    await _load(engine, _row(**{"Model Group": "COROLLA"}))

    assert await _found(engine, _order()) == []


async def test_all_models_button_lifts_the_model_filter(engine):
    await _load(
        engine,
        _row(**{"Model Group": "COROLLA", "Lot number": "1"}),
        _row(**{"Model Group": "RAV4", "Lot number": "2"}),
        _row(**{"Make": "HONDA", "Lot number": "3"}),
    )

    # Оба написания кнопки нормализуются в ALLMODELS; марка по-прежнему важна
    for button in ("ALL MODELS", "ALL_MODELS"):
        assert await _found(engine, _order(car_model=button)) == ["1", "2"]


# --- год и дата торгов --------------------------------------------------------


async def test_year_range_keeps_only_those_years(engine):
    await _load(
        engine,
        _row(**{"Year": "2019", "Lot number": "old"}),
        _row(**{"Year": "2022", "Lot number": "fits"}),
        _row(**{"Year": "2022.0", "Lot number": "float-year"}),
    )

    found = await _found(engine, _order(car_year="2021 - 2023"))
    # Год разбирается через float, как в прежнем фильтре
    assert found == ["fits", "float-year"]


async def test_unreadable_year_falls_out_of_every_range(engine):
    await _load(engine, _row(**{"Year": "N/A"}))

    assert await _found(engine, _order(car_year="2021 - 2023")) == []
    # «Год не имеет значения» такой лот по-прежнему показывает
    assert await _found(engine, _order(car_year=ANY_YEAR)) == ["11111111"]


async def test_lot_that_left_the_auction_is_never_offered(engine):
    await _load(
        engine,
        _row(**{"Sale Date M/D/CY": "0", "Lot number": "gone"}),
        _row(**{"Sale Date M/D/CY": "", "Lot number": "no-date-yet"}),
    )

    # Прежний фильтр отбрасывал только "0"; пустая дата проходила
    assert await _found(engine, _order()) == ["no-date-yet"]
    assert await _found(engine, _order(car_year="2021 - 2023")) == ["no-date-yet"]


# --- пробег и повреждение ---------------------------------------------------


async def test_mileage_band_is_inclusive_at_both_ends(engine):
    await _load(
        engine,
        _row(**{"Odometer": "0.0", "Lot number": "low-edge"}),
        _row(**{"Odometer": "31068.0", "Lot number": "high-edge"}),
        _row(**{"Odometer": "31069.0", "Lot number": "next-band"}),
    )

    found = await _found(engine, _order(car_odometer="до 50 тыс. км"))
    assert found == ["high-edge", "low-edge"]


async def test_unreadable_mileage_only_matters_when_mileage_is_filtered(engine):
    # Раньше float("N/A") ронял весь поиск; теперь такой лот просто не проходит
    # фильтр по пробегу и остаётся в поиске без него
    await _load(engine, _row(**{"Odometer": "N/A"}))

    assert await _found(engine, _order(car_odometer="до 50 тыс. км")) == []
    assert await _found(engine, _order(car_odometer=ANY_YEAR)) == ["11111111"]


async def test_damage_description_must_match_exactly(engine):
    await _load(
        engine,
        _row(**{"Damage Description": "FRONT END", "Lot number": "front"}),
        _row(**{"Damage Description": "REAR END", "Lot number": "rear"}),
    )

    assert await _found(engine, _order(car_damage_description="Переднее")) == ["front"]


# --- рассылка ---------------------------------------------------------------


async def test_lots_already_sent_to_a_subscriber_are_skipped(engine):
    await _load(
        engine,
        _row(**{"VIN": "SENT", "Lot number": "sent"}),
        _row(**{"VIN": "NEW", "Lot number": "new"}),
    )

    assert await _found(engine, _order(), exclude_vins=["SENT"]) == ["new"]


# --- что уходит наружу --------------------------------------------------------


async def test_row_comes_back_exactly_as_the_feed_wrote_it(engine):
    # Подпись к фото печатает год, пробег и дату торгов дословно и режет строку
    # двигателя; разобранное число изменило бы то, что видит клиент
    source = _row(**{"Year": "2022", "Odometer": "20000.0", "Engine": "2.5L 4"})
    await _load(engine, source)

    async with AsyncSession(engine) as session:
        ids = await sales_lots.candidate_ids(session, **_search_filters(_order()))
        (row,) = await sales_lots.rows_by_ids(session, ids)
    assert row == source


async def test_every_match_is_a_candidate_not_just_the_first_few(engine):
    # Прежний код мог перебрать все совпадения в поисках лотов с фото;
    # новый не должен молча урезать этот перебор
    await _load(engine, *(_row(**{"Lot number": str(n)}) for n in range(40)))

    assert len(await _found(engine, _order())) == 40


async def test_rows_keep_the_order_they_were_asked_in(engine):
    await _load(engine, *(_row(**{"Lot number": str(n)}) for n in range(5)))

    async with AsyncSession(engine) as session:
        ids = await sales_lots.candidate_ids(session, **_search_filters(_order()))
        rows = await sales_lots.rows_by_ids(session, list(reversed(ids)))
        by_id = await sales_lots.rows_by_ids(session, ids)
    assert [r["Lot number"] for r in rows] == [r["Lot number"] for r in reversed(by_id)]


async def test_a_reload_during_a_search_drops_the_gone_rows_quietly(engine):
    await _load(engine, _row(**{"Lot number": "before"}))
    async with AsyncSession(engine) as session:
        stale_ids = await sales_lots.candidate_ids(session, **_search_filters(_order()))

    await _load(engine, _row(**{"Lot number": "after"}))
    async with AsyncSession(engine) as session:
        assert await sales_lots.rows_by_ids(session, stale_ids) == []


async def test_loading_a_snapshot_replaces_the_previous_one(engine):
    await _load(engine, _row(**{"Lot number": "old"}))
    await _load(engine, _row(**{"Lot number": "new"}))

    assert await _found(engine, _order()) == ["new"]


# --- поиск целиком -----------------------------------------------------------


async def test_search_keeps_drawing_until_enough_lots_have_photos(engine, monkeypatch):
    # У Copart фото есть не у каждого лота: поиск перебирает кандидатов, пока
    # не наберёт нужное число лотов с фото
    with_photos = {"3", "17", "29"}
    await _load(engine, *(_row(**{"Lot number": str(n)}) for n in range(40)))

    async def fake_get_images(car):
        return ["https://img.invalid/1"] if car["Lot number"] in with_photos else []

    monkeypatch.setattr(services, "get_images", fake_get_images)

    async with AsyncSession(engine) as session:
        found = [row["Lot number"] async for row, _ in services._iter_cars_with_images(session, _order())]
    assert sorted(found) == sorted(with_photos)
