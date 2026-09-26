"""The two callers of the snapshot, run against real rows in the database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import sales_lots
from core.db.models import DamagedCarOrders, User
from core.services import services
from core.services.services import to_snapshot_record

TG_ID = 100500


def _row(lot: str, vin: str) -> dict:
    return {
        "Make": "TOYOTA",
        "Model Group": "CAMRY",
        "Model Detail": "CAMRY SE",
        "Year": "2022",
        "Odometer": "20000.0",
        "Sale Date M/D/CY": "20260901",
        "Lot number": lot,
        "VIN": vin,
        "Color": "WHITE",
        "Engine": "2.5L 4",
        "Drive": "Front-wheel Drive",
        "Transmission": "AUTOMATIC",
        "Fuel Type": "GAS",
        "Damage Description": "FRONT END",
        "Image URL": f"https://example.invalid/lot/{lot}",
    }


async def _load(engine, *rows: dict) -> None:
    async def batches():
        yield [to_snapshot_record(row) for row in rows]

    async with engine.begin() as conn:
        await sales_lots.replace_snapshot(conn, batches())


async def _order(engine, subscription_vins=None) -> int:
    """Store a customer and one damaged-car order, return the order id."""
    # expire_on_commit=False, как у сессий бота: иначе order.id после коммита
    # перечитывается ленивой загрузкой вне async-контекста
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(User(tg_id=TG_ID, tg_name="Тестовый клиент"))
        order = DamagedCarOrders(
            tg_id=TG_ID,
            car_make="TOYOTA",
            car_model="CAMRY",
            car_year="Не имеет значения",
            car_odometer="Не имеет значения",
            car_damage_description="Не имеет значения",
            subscription_status="active",
            subscription_vins=subscription_vins,
        )
        session.add(order)
        await session.commit()
        return order.id


def _every_lot_has_photos(monkeypatch) -> None:
    async def fake_get_images(car):
        return [f"https://img.invalid/{car['Lot number']}"]

    monkeypatch.setattr(services, "get_images", fake_get_images)


async def test_search_offers_at_most_the_requested_number_of_cars(engine, monkeypatch):
    _every_lot_has_photos(monkeypatch)
    await _load(engine, *(_row(str(n), f"VIN{n}") for n in range(10)))
    await _order(engine)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        cars = await services.get_data(session=session, tg_id=TG_ID, count=6)

    assert len(cars) == 6
    # Пара «строка, фото» — в том виде, в каком её ждёт make_media_group
    row, images = cars[0]
    assert images == [f"https://img.invalid/{row['Lot number']}"]


async def test_newsletter_skips_cars_already_sent_and_remembers_new_ones(
    engine, monkeypatch
):
    _every_lot_has_photos(monkeypatch)
    await _load(
        engine,
        _row("1", "VIN-SENT-A"),
        _row("2", "VIN-SENT-B"),
        _row("3", "VIN-NEW"),
    )
    order_id = await _order(engine, subscription_vins=["VIN-SENT-A", "VIN-SENT-B"])

    async with AsyncSession(engine, expire_on_commit=False) as session:
        order = await session.get(DamagedCarOrders, order_id)
        cars = await services.get_subscription_data(session=session, data=order, count=3)

    # Уже отправленные авто не повторяются
    assert [row["VIN"] for row, _ in cars] == ["VIN-NEW"]

    # А новое запоминается, чтобы завтра не прийти снова
    async with AsyncSession(engine) as session:
        stored = await session.scalar(
            select(DamagedCarOrders.subscription_vins).where(DamagedCarOrders.id == order_id)
        )
    assert stored == ["VIN-SENT-A", "VIN-SENT-B", "VIN-NEW"]
