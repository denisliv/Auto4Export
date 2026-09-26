from datetime import datetime

from sqlalchemy import (ARRAY, BigInteger, Column, DateTime, Float, ForeignKey,
                        Index, Integer, String)
from sqlalchemy.orm import relationship

from core.db.base import Base


# Инициализация модели таблицы users
class User(Base):
    __tablename__ = 'users'

    tg_id = Column(BigInteger, primary_key=True)
    tg_login = Column(String, nullable=True)
    tg_name = Column(String, nullable=False)
    registration_date = Column(DateTime, default=datetime.now, nullable=False)
    status = Column(String, default='member', nullable=False)
    active_car_count = Column(Integer, default=0)
    last_update_date = Column(DateTime, default=datetime.now, nullable=False)
    advice_car = relationship('AdviceCarOrder', backref='user', lazy=True, cascade='all, delete-orphan')
    unbroken_car = relationship('UnbrokenCarOrders', backref='user', lazy=True, cascade='all, delete-orphan')
    damaged_car = relationship('DamagedCarOrders', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return str(self.tg_id)


# Инициализация модели таблицы advice_car_order
class AdviceCarOrder(Base):
    __tablename__ = 'advice_car_order'

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.now, nullable=False)
    car_year = Column(String, nullable=False)
    car_budjet = Column(String, nullable=False)
    car_type = Column(String, nullable=False)
    car_buytime = Column(String, nullable=False)

    def __repr__(self):
        return str(self.name)


# Инициализация модели таблицы unbroken_car_orders
class UnbrokenCarOrders(Base):
    __tablename__ = 'unbroken_car_orders'

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.now, nullable=False)
    car_year = Column(String, nullable=False)
    car_model = Column(String, nullable=False)

    def __repr__(self):
        return str(self.name)


# Инициализация модели таблицы damaged_car_orders
class DamagedCarOrders(Base):
    __tablename__ = 'damaged_car_orders'

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=False)
    date = Column(DateTime, default=datetime.now, nullable=False)
    car_make = Column(String, nullable=False)
    car_model = Column(String, nullable=False)
    car_year = Column(String, nullable=False)
    car_odometer = Column(String, nullable=False)
    car_damage_description = Column(String, nullable=False)
    subscription_status = Column(String, default='not_active', nullable=False)
    subscription_vins = Column(ARRAY(String), nullable=True)

    def __repr__(self):
        return str(self.tg_id)


# Снимок инвентаря Copart. Раньше каждый поиск читал весь CSV (~90 МБ) в память
# целиком; теперь выборка идёт запросом, и в процесс попадают только кандидаты.
class SalesLot(Base):
    __tablename__ = 'sales_lot'

    id = Column(Integer, primary_key=True)
    # Значения CSV дословно: подпись к фото печатает год, пробег и дату торгов
    # как есть и режет строку двигателя, так что разобранное число изменило бы
    # то, что видит клиент.
    make = Column(String)
    model_group = Column(String)
    model_detail = Column(String)
    year_text = Column(String)
    odometer_text = Column(String)
    sale_date = Column(String)
    lot_number = Column(String)
    vin = Column(String)
    color = Column(String)
    engine = Column(String)
    drive = Column(String)
    transmission = Column(String)
    fuel_type = Column(String)
    damage_description = Column(String)
    image_url = Column(String)
    # Разобранные значения — только для фильтрации, наружу не уходят.
    make_norm = Column(String, nullable=False)
    model_norm = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    odometer = Column(Float)

    __table_args__ = (Index('idx_sales_lot_make_model', 'make_norm', 'model_norm'),)


class AdminTable(Base):
    __tablename__ = 'admin_table'

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, nullable=False)
    status = Column(String, default='waiting', nullable=False)
    description = Column(String, nullable=True)

    def __repr__(self):
        return str(self.tg_id)
