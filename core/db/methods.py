from datetime import date, datetime
from typing import Optional

from sqlalchemy import MetaData, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Query
from sqlalchemy.sql import text

from core.config_data.config import Config, load_config
from core.db.base import Base
from core.db.models import (AdminTable, AdviceCarOrder, DamagedCarOrders,
                            UnbrokenCarOrders, User)

config: Config = load_config()
admin_ids: list = config.tg_bot.admin_ids


# Функция создания таблиц в БД
async def create_db_tables(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[AdviceCarOrder.__table__,
                                                              DamagedCarOrders.__table__,
                                                              UnbrokenCarOrders.__table__,
                                                              User.__table__])


# Функция записи пользователя в БД
async def add_user(session: AsyncSession, tg_id: int, tg_login: str, tg_name: str) -> None:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    if user is None:
        if tg_id in admin_ids:
            new_user = User(tg_id=tg_id, tg_login=tg_login, tg_name=tg_name, status='admin')
        else:
            new_user = User(tg_id=tg_id, tg_login=tg_login, tg_name=tg_name)
        session.add(new_user)
        await session.commit()


# Функция удаления пользователя в БД
async def delete_user(session: AsyncSession, tg_id: int):
    delete_advice_car_order = delete(AdviceCarOrder).where(AdviceCarOrder.tg_id == tg_id)
    await session.execute(delete_advice_car_order)
    delete_damaged_car_orders = delete(DamagedCarOrders).where(DamagedCarOrders.tg_id == tg_id)
    await session.execute(delete_damaged_car_orders)
    delete_unbroken_car_orders = delete(UnbrokenCarOrders).where(UnbrokenCarOrders.tg_id == tg_id)
    await session.execute(delete_unbroken_car_orders)
    delete_user = delete(User).where(User.tg_id == tg_id)
    await session.execute(delete_user)
    await session.commit()


# Функция записи данных пользователей с FSM advice
async def add_advice_car(session: AsyncSession, tg_id: int, state_report: dict) -> None:
    new_report = AdviceCarOrder(tg_id=tg_id,
                                name=state_report['name'],
                                phone=state_report['phone'],
                                car_year=state_report['year'],
                                car_budjet=state_report['budjet'],
                                car_type=state_report['type'],
                                car_buytime=state_report['buytime'],
                                )
    session.add(new_report)
    await session.commit()


# Функция записи данных пользователей с FSM unbroken
async def add_unbroken_car(session: AsyncSession, tg_id: int, state_report: dict) -> None:
    new_report = UnbrokenCarOrders(tg_id=tg_id,
                                   name=state_report['name'],
                                   phone=state_report['phone'],
                                   car_year=state_report['year'],
                                   car_model=state_report['model']
                                   )
    session.add(new_report)
    await session.commit()


# Функция записи данных пользователей с FSM damaged
async def add_damaged_car(session: AsyncSession, tg_id: int, state_report: dict) -> None:
    new_report = DamagedCarOrders(tg_id=tg_id,
                                  car_make=state_report['make'],
                                  car_model=state_report['model'],
                                  car_year=state_report['year'],
                                  car_odometer=state_report['odometer'],
                                  #car_damage_description=state_report['description']
                                  car_damage_description='Не имеет значения'
                                  )
    session.add(new_report)
    await session.commit()


# Функция записи последней активности пользователя в БД
async def set_last_update(session: AsyncSession, tg_id: int) -> None:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    user.last_update_date = datetime.now()
    await session.commit()


# Функция получения данных пользователя из БД
async def get_damaged_car(session: AsyncSession, tg_id: int) -> Query:
    data = await session.execute(select(DamagedCarOrders).
                                 filter(DamagedCarOrders.tg_id == tg_id).
                                 order_by(DamagedCarOrders.date.desc()))
    data = data.scalar()
    return data


# Функция получения количества подписок
async def get_user_subscription(session: AsyncSession, tg_id: int) -> int:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    return user.active_car_count


# Функция записи количества подписок
async def set_subscription(session: AsyncSession, tg_id: int, limit: int = 10) -> None:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    count = user.active_car_count
    if count != limit:
        data = await session.execute(select(DamagedCarOrders).
                                     filter(DamagedCarOrders.tg_id == tg_id).
                                     order_by(DamagedCarOrders.date.desc()))
        data = data.scalar()
        data.subscription_status = 'active'
        user.active_car_count += 1
        await session.commit()
    return count if count == limit else count + 1


# Функция получения подписок пользователя
async def user_active_car(session: AsyncSession, tg_id: int) -> Optional[list]:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    if user.active_car_count == 0:
        return None
    else:
        data = await session.execute(select(DamagedCarOrders).
                                     filter(DamagedCarOrders.tg_id == tg_id).
                                     filter(DamagedCarOrders.subscription_status == 'active').
                                     order_by(DamagedCarOrders.date))
        data = data.scalars()
        return [car for car in data]


# Функция получения описания подписки
async def user_car_description(session: AsyncSession, id: int) -> Optional[list]:
    car = await session.execute(select(DamagedCarOrders).filter(DamagedCarOrders.id == id))
    car = car.scalar()
    return car


# Функция получения удаления авто из подписки
async def user_car_edit_description(session: AsyncSession, tg_id: int, id: int) -> None:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    user.active_car_count -= 1
    car = await session.execute(select(DamagedCarOrders).filter(DamagedCarOrders.id == id))
    car = car.scalar()
    car.subscription_status = 'not_active'
    await session.commit()


# Функция получения списка авто для рассылки по подписке
async def get_subs_cars_id(session: AsyncSession) -> iter:
    cars = await session.execute(select(DamagedCarOrders).filter(DamagedCarOrders.subscription_status == 'active'))
    cars = cars.scalars()
    return (car for car in cars)


# Функция получения списка пользователей для рассылки по подписке
async def get_subs_user_id(session: AsyncSession, tg_id) -> int:
    user = await session.execute(select(User).filter(User.tg_id == tg_id))
    user = user.scalar()
    try:
        return user.tg_id, user.tg_name
    except Exception:
        return None


# Функция записи VIN по подписке
async def add_vins(session: AsyncSession, car_id: int, car_vin: str) -> None:
    car = await session.execute(select(DamagedCarOrders).filter(DamagedCarOrders.id == car_id))
    car = car.scalar()
    subscription_vins = car.subscription_vins or []
    subscription_vins.append(car_vin)
    car.subscription_vins = subscription_vins
    await session.execute(update(DamagedCarOrders).where(DamagedCarOrders.id == car_id).values(
        subscription_vins=subscription_vins))
    await session.commit()


# Функция получения статистик пользования ботом
async def get_user_statistics(session: AsyncSession) -> tuple[int, int, int, int, int]:

    user_count = await session.execute(text("""
                                            select count(tg_id)
                                            from users
                                            where status != 'admin';
                                            """))

    new_user_count = await session.execute(text("""
                                                select count(tg_id)
                                                from users
                                                where date_trunc('day', registration_date) = CURRENT_DATE and status != 'admin';
                                                """))

    active_user_count = await session.execute(text("""
                                                   select count(tg_id)
                                                   from users
                                                   where date_trunc('day', last_update_date) = CURRENT_DATE and status != 'admin';"""))

    subscription_count = await session.execute(text("""
                                                   select count(tg_id)
                                                   from users
                                                   where active_car_count > 0 and status != 'admin';
                                                    """))

    subs_car_count = await session.execute(text("""
                                                select sum(active_car_count)
                                                from users
                                                where status != 'admin';
                                                """))
    return (user_count.scalar(),
            new_user_count.scalar(),
            active_user_count.scalar(),
            subscription_count.scalar(),
            subs_car_count.scalar())


# Функция проверки существования временной таблицы для рассылки
async def admin_check_table(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        metadata = MetaData()
        await conn.run_sync(metadata.reflect)
        return 'admin_table' in metadata.tables


# Функция создания временной таблицы для рассылки
async def admin_create_table(engine: AsyncEngine, session: AsyncSession) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[AdminTable.__table__])
    users = await session.execute(select(User))
    users = users.scalars()
    for user in users:
        admin = AdminTable(tg_id=user.tg_id)
        session.add(admin)
    await session.commit()


# Функция удаления временной таблицы для рассылки
async def admin_delete_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(AdminTable.__table__.drop)


# Функция получения списка пользователей для рассылки
async def get_users(session: AsyncSession) -> iter:
    users = await session.execute(select(AdminTable).filter(AdminTable.status == 'waiting'))
    users = users.scalars()
    return (user.tg_id for user in users)


# Функция записи статуса пользователя в таблице рассылки
async def update_status(session: AsyncSession, tg_id: int, status: str, description: str) -> None:
    user = await session.execute(select(AdminTable).filter(AdminTable.tg_id == tg_id))
    user = user.scalar()
    user.status = status
    user.description = description
    await session.commit()
