"""Downloading the Copart feed and turning it into the snapshot."""

import logging

import pytest
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import sales_lots
from core.services import services
from core.services.services import (
    FeedDownloadError,
    to_snapshot_record,
    validate_snapshot_file,
)

SECRET = "SUPERSECRETAUTHKEY"
HEADER = ",".join(f'"{name}"' for name in sales_lots.CSV_COLUMNS)


def _csv(*lots: str) -> str:
    lines = [HEADER]
    for lot in lots:
        values = {name: "" for name in sales_lots.CSV_COLUMNS}
        values.update(
            {
                "Make": "TOYOTA",
                "Model Group": "CAMRY",
                "Year": "2022",
                "Odometer": "1.0",
                "Sale Date M/D/CY": "20260901",
                "Lot number": lot,
            }
        )
        lines.append(",".join(f'"{values[name]}"' for name in sales_lots.CSV_COLUMNS))
    return "\n".join(lines) + "\n"


# --- проверка файла ---------------------------------------------------------


def test_empty_file_is_not_a_feed(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(FeedDownloadError, match="empty"):
        validate_snapshot_file(path)


def test_error_page_is_not_a_feed(tmp_path):
    # Copart на отказ отвечает HTML-страницей, а не CSV
    path = tmp_path / "feed.csv"
    path.write_text("<html><body>Access denied</body></html>\n", encoding="utf-8")

    with pytest.raises(FeedDownloadError, match="lacks columns"):
        validate_snapshot_file(path)


def test_header_without_rows_is_not_a_feed(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text(HEADER + "\n", encoding="utf-8")

    with pytest.raises(FeedDownloadError, match="no data rows"):
        validate_snapshot_file(path)


def test_well_formed_feed_passes(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text(_csv("1"), encoding="utf-8")

    validate_snapshot_file(path)


# --- разбор строки ------------------------------------------------------------


def test_snapshot_record_keeps_the_text_and_parses_like_the_old_filter():
    row = {name: "" for name in sales_lots.CSV_COLUMNS}
    row.update({"Make": "Fisker Automotive", "Model Group": "C-HR", "Year": "2022.0", "Odometer": "20000.0"})

    record = to_snapshot_record(row)
    text, parsed = record[: len(sales_lots.CSV_COLUMNS)], record[len(sales_lots.CSV_COLUMNS) :]

    assert text[sales_lots.CSV_COLUMNS.index("Year")] == "2022.0"
    assert parsed == ("FISKER", "CHR", 2022, 20000.0)


def test_unreadable_year_and_mileage_do_not_break_the_load():
    row = {name: "" for name in sales_lots.CSV_COLUMNS}
    row.update({"Year": "N/A", "Odometer": "N/A"})

    assert to_snapshot_record(row)[-2:] == (0, None)


# --- загрузка фида ------------------------------------------------------------


@pytest.fixture
async def feed_server():
    """A local stand-in for Copart whose answer the test sets."""
    answer = {"status": 200, "body": b""}

    async def handler(request):
        return web.Response(status=answer["status"], body=answer["body"])

    app = web.Application()
    app.router.add_get("/salesdata.cgi", handler)
    # Журнал запросов у заглушки выключен: иначе в caplog попадёт адрес с ключом
    # из лога самого сервера, и проверка «ключ не утекает» станет проверять его
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield answer, f"http://127.0.0.1:{port}/salesdata.cgi?authKey={SECRET}"
    await runner.cleanup()


async def _lots(engine) -> list[str]:
    async with AsyncSession(engine) as session:
        ids = await sales_lots.candidate_ids(
            session,
            make_norm="TOYOTA",
            model_norm=None,
            years=None,
            odometer=None,
            description=None,
        )
        return sorted(r["Lot number"] for r in await sales_lots.rows_by_ids(session, ids))


async def test_good_feed_replaces_the_file_and_the_snapshot(engine, feed_server, tmp_path, monkeypatch):
    answer, url = feed_server
    monkeypatch.setattr(services, "CSV_PATH", tmp_path / "salesdata.csv")
    answer["body"] = _csv("1", "2").encode()

    await services.download_csv(url, engine)

    assert await _lots(engine) == ["1", "2"]
    assert not list(tmp_path.glob("*.tmp"))


async def test_failed_download_keeps_the_previous_feed_and_snapshot(
    engine, feed_server, tmp_path, monkeypatch, caplog
):
    answer, url = feed_server
    feed_file = tmp_path / "salesdata.csv"
    monkeypatch.setattr(services, "CSV_PATH", feed_file)

    answer["body"] = _csv("good").encode()
    await services.download_csv(url, engine)

    # Copart отказал: ни файл, ни снимок в базе не должны пострадать
    answer["status"] = 403
    answer["body"] = b"<html>Forbidden</html>"
    with caplog.at_level(logging.DEBUG), pytest.raises(FeedDownloadError) as error:
        await services.download_csv(url, engine)

    assert await _lots(engine) == ["good"]
    assert '"good"' in feed_file.read_text(encoding="utf-8")
    # В адресе фида едет ключ доступа Copart: он не должен попасть ни в текст
    # ошибки, ни в лог — оба уходят в stdout контейнера
    assert SECRET not in str(error.value)
    assert SECRET not in caplog.text


async def test_broken_feed_does_not_replace_the_snapshot(engine, feed_server, tmp_path, monkeypatch):
    answer, url = feed_server
    monkeypatch.setattr(services, "CSV_PATH", tmp_path / "salesdata.csv")

    answer["body"] = _csv("good").encode()
    await services.download_csv(url, engine)

    answer["body"] = b"not,a,feed\n"
    with pytest.raises(FeedDownloadError):
        await services.download_csv(url, engine)

    assert await _lots(engine) == ["good"]


async def test_empty_snapshot_is_rebuilt_from_the_file_on_the_volume(engine, tmp_path, monkeypatch):
    # Перезапуск при недоступном Copart: файл на томе есть, а таблица пуста
    feed_file = tmp_path / "salesdata.csv"
    feed_file.write_text(_csv("from-volume"), encoding="utf-8")
    monkeypatch.setattr(services, "CSV_PATH", feed_file)

    await services.ensure_snapshot_loaded(engine)

    assert await _lots(engine) == ["from-volume"]


async def test_filled_snapshot_is_not_reloaded_on_start(engine, tmp_path, monkeypatch):
    feed_file = tmp_path / "salesdata.csv"
    feed_file.write_text(_csv("in-db"), encoding="utf-8")
    monkeypatch.setattr(services, "CSV_PATH", feed_file)
    await services.ensure_snapshot_loaded(engine)

    feed_file.write_text(_csv("newer-file"), encoding="utf-8")
    await services.ensure_snapshot_loaded(engine)

    assert await _lots(engine) == ["in-db"]
