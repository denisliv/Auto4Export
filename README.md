# Auto4Export

Telegram-бот для компании Auto4Export — подбор и доставка автомобилей из США (аукцион Copart). Помогает пользователям узнавать об авто из США, получать консультации, просматривать лоты с аукционов прямо в Telegram и подписываться на обновления по интересующим маркам/моделям.

## Цель проекта

- Помощь в поиске, покупке и доставке авто из США
- Просмотр реальных лотов Copart прямо в Telegram
- Бесплатная консультация по подбору авто
- Подписка на обновления по марке/модели с ежедневной рассылкой
- Отправка заявок (лидов) в Bitrix24 CRM

## Структура проекта

```
Auto4Export/
├── bot.py                 # Точка входа, инициализация бота
├── core/
│   ├── config_data/       # Конфигурация (переменные окружения)
│   │   └── config.py
│   ├── db/                # База данных
│   │   ├── base.py
│   │   ├── methods.py     # CRUD-операции
│   │   └── models.py     # Модели: User, DamagedCarOrders, AdviceCarOrder и др.
│   ├── filters/           # Кастомные фильтры для хендлеров
│   ├── handlers/          # Обработчики команд и callback
│   │   ├── admin.py       # Админ-панель
│   │   ├── advice_form.py # Форма консультации
│   │   ├── damaged_form.py # Форма подбора повреждённых авто
│   │   ├── unbroken_form.py # Форма подбора авто без повреждений
│   │   ├── user.py        # Пользовательские команды
│   │   └── other.py
│   ├── keyboards/         # Reply и inline клавиатуры
│   ├── lexicon/           # Тексты интерфейса (русский)
│   │   └── lexicon_ru.py
│   ├── middlewares/       # DbSession, Throttling, LimitAction, ChatAction
│   ├── services/          # Бизнес-логика
│   │   ├── services.py    # Загрузка CSV, рассылка подписок, Bitrix
│   │   └── admin_sevices.py
│   └── utils/             # FSM-состояния для форм
├── core/data/csv/         # Каталог для CSV Copart (volume в Docker)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Зависимости

- **Python 3.11**
- **aiogram 3.x** — Telegram Bot API
- **PostgreSQL + asyncpg** — хранение пользователей и заявок
- **Redis** — FSM-хранилище, троттлинг
- **APScheduler** — периодическая загрузка CSV (каждые 30 мин), рассылка подписок (ежедневно в 9:30 МСК)

## Запуск

### 1. Клонирование и настройка

```bash
# Скопировать пример конфигурации
cp .env.example .env

# Отредактировать .env:
# - BOT_TOKEN — токен бота от @BotFather
# - ADMIN_IDS — ID администраторов через запятую
# - COPART_URL — URL инвентаря Copart
# - POSTGRES_PASSWORD (для Docker)
# - DATABASE_URL и REDIS_URL (для локального запуска)
```

### 2. Запуск через Docker (рекомендуется)

```bash
docker-compose up -d
```

Запускаются сервисы:
- `bot` — бот
- `postgres` — PostgreSQL 16
- `redis` — Redis 7

При первом запуске можно загрузить дамп БД: раскомментировать строку с `init.sql` в `docker-compose.yml`, положить дамп в `backups/auto4export_dump_v2.sql`, затем снова закомментировать.

### 3. Локальный запуск (без Docker)

Убедитесь, что запущены PostgreSQL и Redis. Затем:

```bash
# Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate   # Windows

# Установить зависимости
pip install -r requirements.txt

# Создать каталог для CSV
mkdir -p core/data/csv

# Запустить бота
python bot.py
```

В `.env` для локального режима должны быть указаны:
- `DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/auto4export`
- `REDIS_URL=redis://localhost:6379/0`

## Функционал

| Функция | Описание |
|---------|----------|
| **Подобрать авто** | Формы для повреждённых и неповреждённых авто, поиск по марке/модели/году/пробегу |
| **Подписка** | Уведомления о новых лотах по выбранным марке и модели (ежедневно в 9:30) |
| **Консультация** | Форма заявки на консультацию → lead в Bitrix24 |
| **Важная информация** | Информация об авто из США, контакты компании |

## Переменные окружения

| Переменная | Описание | Обязательно |
|------------|----------|-------------|
| `BOT_TOKEN` | Токен Telegram-бота | Да |
| `ADMIN_IDS` | ID администраторов через запятую | Да |
| `COPART_URL` | URL инвентаря Copart (CSV) | Да |
| `DATABASE_URL` | PostgreSQL connection string | Да (локально) |
| `REDIS_URL` | Redis connection string | Да (локально) |
| `POSTGRES_USER` | Пользователь PostgreSQL (Docker) | Да (для Docker) |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | Да (для Docker) |
| `POSTGRES_DB` | Имя БД (по умолчанию `auto4export`) | Нет |

## Лицензия

Приватный проект Auto4Export.by.
