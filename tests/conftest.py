import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# core.db.methods читает конфигурацию прямо при импорте. Фиктивные значения
# ставятся до любого импорта из core, чтобы настоящий .env с боевым токеном
# для этих ключей не прочитался: environs не перезаписывает заданные переменные.
os.environ.setdefault("BOT_TOKEN", "000000:test-token-not-real")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")
os.environ.setdefault("COPART_URL", "https://feed.invalid/salesdata.cgi?authKey=test")
os.environ.setdefault("BITRIX_WEBHOOK_URL", "https://portal.invalid/rest/1/not-a-real-token/")

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from core.db.base import Base  # noqa: E402
from core.db.models import DamagedCarOrders, SalesLot, User  # noqa: E402

# Правила поиска живут в SQL, поэтому проверяются на настоящем PostgreSQL:
# подделка соединения проверила бы текст запроса, а не его смысл. Без адреса
# базы такие тесты пропускаются.
TEST_DATABASE_ENV = "AUTO4EXPORT_TEST_DATABASE_URL"

_TABLES = [User.__table__, DamagedCarOrders.__table__, SalesLot.__table__]


@pytest.fixture
async def engine():
    """Give an engine over empty users, orders and snapshot tables."""
    url = os.environ.get(TEST_DATABASE_ENV)
    if not url:
        pytest.skip(f"{TEST_DATABASE_ENV} is not set")

    test_engine = create_async_engine(url)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_TABLES)
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    yield test_engine
    await test_engine.dispose()
