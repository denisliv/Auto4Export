"""Queries over the Copart inventory snapshot.

The snapshot used to be read from the CSV on every search: the whole ~90 MB
file as a list of lines, copied and shuffled, once per call. Concurrent
searches each held their own copy while they waited on Copart for photos, and
the process never gave that memory back. Here the filtering is SQL and only
the candidates reach Python.

Rows leave this module keyed by CSV column name and carrying the CSV text
verbatim, so the caption and the buttons read them exactly as before.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from core.db.models import SalesLot

# Колонки CSV, которые читает бот, и текстовые колонки таблицы под них.
# Порядок задаёт и COPY при загрузке, и SELECT при чтении.
COLUMN_MAP: tuple[tuple[str, str], ...] = (
    ("Make", "make"),
    ("Model Group", "model_group"),
    ("Model Detail", "model_detail"),
    ("Year", "year_text"),
    ("Odometer", "odometer_text"),
    ("Sale Date M/D/CY", "sale_date"),
    ("Lot number", "lot_number"),
    ("VIN", "vin"),
    ("Color", "color"),
    ("Engine", "engine"),
    ("Drive", "drive"),
    ("Transmission", "transmission"),
    ("Fuel Type", "fuel_type"),
    ("Damage Description", "damage_description"),
    ("Image URL", "image_url"),
)

CSV_COLUMNS: tuple[str, ...] = tuple(csv_name for csv_name, _ in COLUMN_MAP)
TEXT_COLUMNS: tuple[str, ...] = tuple(db_name for _, db_name in COLUMN_MAP)
# Разобранные значения идут после текста — в этом порядке их отдаёт загрузка.
PARSED_COLUMNS: tuple[str, ...] = ("make_norm", "model_norm", "year", "odometer")
COPY_COLUMNS: tuple[str, ...] = TEXT_COLUMNS + PARSED_COLUMNS

# Значение "Sale Date M/D/CY" у лота, который уже не продаётся.
SALE_DATE_ABSENT = "0"

_TEXT_ATTRS = [getattr(SalesLot, name) for name in TEXT_COLUMNS]


async def replace_snapshot(
    conn: AsyncConnection,
    batches: AsyncIterator[Sequence[Sequence[Any]]],
) -> int:
    """Replace the whole snapshot with the rows of these batches.

    DELETE rather than TRUNCATE: customers keep searching while a new feed
    loads, and TRUNCATE would make every search wait for the load to finish.
    DELETE leaves the previous snapshot visible to them until the caller's
    transaction commits, and a load that fails half-way leaves it untouched.

    Args:
        conn: Connection whose transaction the caller owns.
        batches: Groups of records in COPY_COLUMNS order.

    Returns:
        How many rows the snapshot now holds.
    """
    await conn.execute(delete(SalesLot))
    driver = (await conn.get_raw_connection()).driver_connection
    loaded = 0
    async for batch in batches:
        await driver.copy_records_to_table(
            SalesLot.__tablename__,
            columns=list(COPY_COLUMNS),
            records=batch,
        )
        loaded += len(batch)
    return loaded


async def count_snapshot(conn: AsyncConnection) -> int:
    """Return how many rows the snapshot holds."""
    result = await conn.execute(select(func.count()).select_from(SalesLot))
    return result.scalar_one()


async def candidate_ids(
    session: AsyncSession,
    *,
    make_norm: str,
    model_norm: str | None,
    years: Sequence[int] | None,
    odometer: Sequence[float] | None,
    description: str | None,
    exclude_vins: Sequence[str] = (),
) -> list[int]:
    """Return the ids of every matching lot, in random order.

    Ids rather than rows: a search keeps drawing candidates until enough of
    them have photos, which can mean all of them, and for a popular make that
    is sixteen thousand lots. Their ids are a fraction of a megabyte; the rows
    are fetched a few at a time by `rows_by_ids`.

    Args:
        session: Session to query through.
        make_norm: Make as `normalize_string` renders it.
        model_norm: Model as `normalize_string` renders it, or None for any.
        years: Model years to accept, or None to accept any year.
        odometer: Inclusive mileage range, or None to accept any mileage.
        description: Damage description to require, or None for any.
        exclude_vins: VINs already sent to this subscriber.

    Returns:
        Matching ids in random order.
    """
    # IS DISTINCT FROM повторяет прежнее сравнение строк в Python: пустая дата
    # и отсутствующая дата проходят, не проходит только "0".
    conditions = [
        SalesLot.make_norm == make_norm,
        SalesLot.sale_date.is_distinct_from(SALE_DATE_ABSENT),
    ]
    if model_norm is not None:
        conditions.append(SalesLot.model_norm == model_norm)
    if years is not None:
        conditions.append(SalesLot.year.in_(list(years)))
    if odometer is not None:
        conditions.append(SalesLot.odometer.between(odometer[0], odometer[1]))
    if description is not None:
        conditions.append(SalesLot.damage_description == description)
    if exclude_vins:
        conditions.append(
            or_(SalesLot.vin.is_(None), SalesLot.vin.not_in(list(exclude_vins)))
        )

    result = await session.execute(
        select(SalesLot.id).where(*conditions).order_by(func.random())
    )
    return list(result.scalars())


async def rows_by_ids(session: AsyncSession, ids: Sequence[int]) -> list[dict[str, Any]]:
    """Return the rows behind these ids, in the order given, keyed by CSV column.

    An id that is gone — the snapshot was reloaded while a search was running
    — is skipped: the search returns what it found rather than failing.

    Args:
        session: Session to query through.
        ids: Ids from `candidate_ids`.

    Returns:
        One dict per surviving id, in the order of `ids`.
    """
    result = await session.execute(
        select(SalesLot.id, *_TEXT_ATTRS).where(SalesLot.id.in_(list(ids)))
    )
    by_id = {record[0]: dict(zip(CSV_COLUMNS, record[1:])) for record in result}
    return [by_id[lot_id] for lot_id in ids if lot_id in by_id]
