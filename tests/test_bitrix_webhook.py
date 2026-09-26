"""The Bitrix webhook comes from the environment and never from the code.

The repository is public, and a webhook token written in the source was
readable by anyone together with the customers' leads it gives access to.
"""

import os
import re
from pathlib import Path

import pytest
from environs import EnvError

from core.config_data.config import load_config
from core.services import services

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Адрес вебхука Bitrix с токеном: /rest/<id пользователя>/<токен>
WEBHOOK_WITH_TOKEN = re.compile(r"bitrix24\.[a-z]+/rest/\d+/[A-Za-z0-9]{8,}")

LEAD = {
    "name": "Тест Тестов",
    "phone": "+375000000000",
    "year": "2020",
    "budjet": "10000",
    "type": "sedan",
    "buytime": "month",
    "model": "CAMRY",
    "lot": "Лот №: 12345678-TOYOTA-CAMRY",
    "message": "проверка",
}


@pytest.mark.parametrize("method", ["advice", "unbroken", "damaged", "general"])
async def test_every_lead_goes_to_the_webhook_from_the_environment(method):
    # Хвостовой слэш в .env не должен давать двойной слэш в адресе
    configured = os.environ["BITRIX_WEBHOOK_URL"].rstrip("/")

    url = await services.make_bitrix_url("login", 1, LEAD, method)

    assert url.startswith(f"{configured}/crm.lead.add.json?")


def test_no_webhook_token_is_written_in_the_code():
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in PROJECT_ROOT.rglob("*.py")
        if ".venv" not in path.parts
        and WEBHOOK_WITH_TOKEN.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []


def test_bot_refuses_to_start_without_the_webhook(tmp_path, monkeypatch):
    # Лучше не подняться на старте, чем молча терять заявки клиентов
    monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")

    with pytest.raises(EnvError):
        load_config(str(empty_env))
