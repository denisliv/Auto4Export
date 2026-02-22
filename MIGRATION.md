# Миграция Auto4Export на новый сервер с Docker

## Кратко

1. **Структура БД:** Таблицы создаются автоматически при старте бота (`create_db_tables` в `core/db/models.py`).
2. **Docker:** bot, postgres, redis в контейнерах.
3. **CSV Copart:** Загружается при первом запуске и обновляется каждые 30 минут.

---

## 1. Создание дампа БД на старом сервере

На старом сервере (где сейчас работает проект без Docker):

```bash
# Если PostgreSQL установлен локально
pg_dump -U postgres -h localhost -d auto4export -F p -f auto4export_dump.sql

# Или с указанием пароля
PGPASSWORD=2064 pg_dump -U postgres -h localhost -d auto4export -F p -f auto4export_dump.sql
```

- `-F p` — дамп в формате plain SQL (удобно для переноса).
- Сохраните файл `auto4export_dump.sql` — он понадобится на новом сервере.

---

## 2. Загрузка дампа на новый сервер

```bash
# Через scp
scp auto4export_dump.sql user@new-server:/path/to/Auto4Export/backups/

# Или через rsync
rsync -avz auto4export_dump.sql user@new-server:/path/to/Auto4Export/backups/
```

---

## 3. Подготовка на новом сервере

### 3.1 Установить Docker и Docker Compose

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose-plugin -y
sudo systemctl enable docker
sudo usermod -aG docker $USER
# Перелогиниться для применения группы
```

### 3.2 Скопировать проект

```bash
# Клонировать или скопировать репозиторий
git clone <your-repo> Auto4Export
cd Auto4Export
# или scp/rsync всего каталога проекта
```

### 3.3 Создать .env

```bash
cp .env.example .env
nano .env  # Заполнить BOT_TOKEN, ADMIN_IDS, POSTGRES_PASSWORD и т.д.
```

Пример `.env` для Docker:

```env
BOT_TOKEN=5834392410:AAFem64QFor0iNul-QKiOgrRJnVBSVs_q1k
ADMIN_IDS=290098392,24524638,310964,593169700

POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=auto4export

COPART_URL=https://inventory.copart.io/FTPLSTDM/salesdata.cgi?authKey=YPYU91EI
```

> `DATABASE_URL` и `REDIS_URL` переопределяются в `docker-compose.yml` для контейнера бота.

---

## 4. Восстановление БД из дампа

### Вариант А: Восстановить до первого запуска бота

1. Положить дамп в `backups/`:

   ```bash
   mkdir -p backups
   # Скопировать сюда auto4export_dump.sql
   ```

2. Добавить volume в `docker-compose.yml` для postgres:

   ```yaml
   postgres:
     volumes:
       - postgres_data:/var/lib/postgresql/data
       - ./backups/auto4export_dump.sql:/docker-entrypoint-initdb.d/init.sql:ro
   ```

3. Запустить **один раз** без существующего volume:

   ```bash
   docker compose up -d postgres
   # Подождать, пока postgres инициализируется и применит init.sql
   docker compose logs -f postgres
   ```

4. Убрать mount с `init.sql` из `docker-compose.yml`, чтобы при следующих запусках PostgreSQL не пересоздавал базу.

5. Запустить всё:

   ```bash
   docker compose up -d
   ```

### Вариант Б: Восстановить после первого запуска

Если бот уже создал пустую БД:

```bash
# Остановить все сервисы
docker compose down

# Удалить volume с данными postgres (осторожно — удаляет данные)
docker volume rm auto4export_postgres_data 2>/dev/null || true

# Добавить volume с дампом в docker-compose (как в варианте А)
# Затем:
docker compose up -d postgres
# Подождать инициализации
docker compose up -d bot redis
```

### Вариант В: Восстановить в уже работающий контейнер postgres

```bash
# postgres уже запущен
docker compose exec postgres psql -U postgres -d auto4export -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

docker compose exec -T postgres psql -U postgres -d auto4export < backups/auto4export_dump.sql
```

---

## 5. Запуск

```bash
docker compose up -d
```

При первом запуске:

1. Postgres и Redis поднимутся и пройдут healthcheck.
2. Бот создаст таблицы (если их ещё нет).
3. Бот загрузит CSV с Copart и продолжит обновлять его каждые 30 минут.
4. Polling бота будет активен.

---

## 6. Полезные команды

```bash
# Логи
docker compose logs -f bot

# Пересборка образа бота
docker compose build --no-cache bot && docker compose up -d bot

# Остановка
docker compose down

# Остановка с удалением volumes (очистить всё, включая БД)
docker compose down -v
```

---

## 7. Схема таблиц (создаются автоматически)

| Таблица | Описание |
|---------|----------|
| `users` | Пользователи бота |
| `advice_car_order` | Заявки на консультацию |
| `unbroken_car_orders` | Заявки на целые авто |
| `damaged_car_orders` | Заявки на битые авто (Copart) |
| `admin_table` | Временная таблица рассылки (создаётся при необходимости) |
