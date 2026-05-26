# ТЗ: Telegram-бот мониторинга статуса ботов

## 1. Назначение

Создать отдельного Telegram-бота, который показывает администратору актуальное состояние рабочих ботов, сервера и ключевых метрик пользователей.

Первый этап охватывает только два существующих проекта:

- `D:\проекты qwen\tg_bot\new_architecture`
- `D:\проекты qwen\tg_bot_inkubator`

Эти два проекта считаются источниками только для чтения. Статус-бот не должен менять их код, базу данных, `.env`, логи или файлы деплоя без отдельного решения.

## 2. Текущее состояние проектов

### 2.1. `tg_bot\new_architecture`

Стек:

- Python 3.11+
- `python-telegram-bot`
- FastAPI
- PostgreSQL
- SQLAlchemy async
- Alembic
- Docker Compose

Сервисы:

- Telegram bot: `python -m src.main bot`
- FastAPI API: `python -m src.main api`
- reminder worker: `python -m src.main worker`
- общий запуск: `python -m src.main all`

Уже есть полезные точки интеграции:

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /admin/stats`, нужен заголовок `X-Admin-Token`
- `GET /admin/activity`, нужен заголовок `X-Admin-Token`
- Docker Compose сервисы: `postgres`, `init-db`, `bot`, `api`, `worker`

База:

- PostgreSQL через `DATABASE_URL`
- таблица `users`
- таблица `bot_activity_events` для агрегированной активности
- админская статистика уже считает пользователей, списки, напоминания, активность и due reminders

Важное замечание:

- `/health/ready` проверяет API и базу, но не доказывает напрямую, что polling-бот и worker живы. Для них нужен дополнительный контроль через Docker/systemd/процессы или будущий heartbeat.

### 2.2. `tg_bot_inkubator`

Стек:

- Python
- `aiogram`
- SQLite
- собственные миграции
- Docker Compose
- systemd-шаблоны для VPS

Запуск:

- локально: `python main.py`
- production Docker Compose: сервис `bot`
- systemd unit: `tg-bot-inkubator.service`

Уже есть полезные точки интеграции:

- SQLite база из `DATABASE_PATH`
- таблица `users` с `is_active`, `last_seen_at`
- таблица `analytics_events`
- таблица `critical_errors`
- `scripts/status-bot.ps1` проверяет PID для локального запуска
- `scripts/check_disk.py` используется как Docker healthcheck
- `/admin` внутри самого бота показывает пользователям, активные сущности, ошибки уведомлений и свободное место на диске

Ограничение:

- HTTP health endpoint отсутствует.
- Для мониторинга без изменения проекта можно читать SQLite и проверять процесс/container/systemd.
- Для более точного мониторинга позже стоит добавить отдельный read-only probe или heartbeat.

## 3. Цели MVP

MVP должен уметь:

1. Показывать общий статус двух ботов одной командой `/status`.
2. Показывать детальный статус каждого бота.
3. Показывать количество пользователей:
   - всего;
   - активных за последние 24 часа, где это возможно;
   - активных по внутреннему флагу `is_active`, где это есть.
4. Показывать состояние сервера:
   - uptime;
   - CPU;
   - RAM;
   - свободное место на диске;
   - состояние Docker-контейнеров или systemd-сервисов, если настроено.
5. Уведомлять администратора, если бот/сервис стал недоступен.
6. Не ломать и не блокировать существующие боты.

## 4. Пользователи статус-бота

Статус-бот предназначен только для владельца/администраторов.

Доступ:

- список Telegram ID администраторов хранится в `.env`;
- все команды проверяют `from_user.id`;
- неизвестным пользователям бот отвечает коротко: доступ запрещен.

## 5. Основные команды

### `/start`

Показывает главное меню:

- Статус всех ботов
- RememberMe
- Инкубатор
- Сервер
- Ошибки
- Настройки мониторинга

### `/status`

Краткая сводка:

```text
Общий статус: OK / DEGRADED / DOWN

RememberMe: OK
API: OK
DB: OK
Bot process: OK/unknown
Worker: OK/unknown
Users: 123 total, 12 active 24h

Инкубатор: OK
Process: OK
DB: OK
Users: 45 total, 38 active
Critical errors: 0 recent

Server:
CPU: 8%
RAM: 41%
Disk: 62 GB free
Uptime: 12d 04h
```

### `/bots`

Список подключенных ботов с кнопками:

- RememberMe
- Инкубатор
- Обновить

### `/bot_rememberme`

Детальный статус `tg_bot\new_architecture`:

- HTTP `/health`
- HTTP `/health/ready`
- версия из health response
- состояние PostgreSQL из readiness
- админская статистика `/admin/stats`
- активность `/admin/activity`
- состояние Docker/systemd, если включено
- последние ошибки, если будет настроен источник логов

### `/bot_incubator`

Детальный статус `tg_bot_inkubator`:

- наличие SQLite базы
- возможность открыть базу read-only
- количество пользователей
- количество активных пользователей
- последние `critical_errors`
- количество ошибок уведомлений
- свободное место на диске каталога данных
- состояние PID/systemd/Docker, если включено

### `/server`

Показывает:

- hostname;
- OS;
- uptime;
- CPU load;
- RAM usage;
- disk usage по заданным путям;
- Docker containers, если Docker доступен;
- systemd units, если запуск на Linux/VPS.

### `/errors`

Показывает последние ошибки:

- `tg_bot_inkubator`: из таблицы `critical_errors`;
- `new_architecture`: на MVP либо "не настроено", либо чтение логов/будущий источник ошибок;
- ошибки самого статус-бота.

### `/refresh`

Принудительно обновляет состояние и сбрасывает кеш.

## 6. Архитектура статус-бота

Рекомендуемый стек:

- Python 3.11+
- `aiogram` 3.x
- `pydantic-settings`
- `httpx`
- `aiosqlite`
- `asyncpg` или HTTP admin API для PostgreSQL-бота
- `psutil`
- `APScheduler` или простой async loop для периодических проверок

Предлагаемая структура:

```text
tg_status_bot/
  app/
    main.py
    config.py
    bot/
      handlers.py
      keyboards.py
      access.py
    monitors/
      base.py
      rememberme.py
      incubator.py
      server.py
    services/
      alerts.py
      status_cache.py
      formatters.py
    storage/
      database.py
      models.py
  tests/
  docs/
    STATUS_BOT_TZ.md
  .env.example
  README.md
  requirements.txt
  Dockerfile
  docker-compose.yml
```

## 7. Источники данных

### 7.1. RememberMe / `new_architecture`

Предпочтительный путь MVP:

- проверять `REMEMBERME_API_BASE_URL/health`;
- проверять `REMEMBERME_API_BASE_URL/health/ready`;
- читать `REMEMBERME_API_BASE_URL/admin/stats` с `X-Admin-Token`;
- читать `REMEMBERME_API_BASE_URL/admin/activity?days=1` с `X-Admin-Token`.

Конфиг:

```env
REMEMBERME_ENABLED=true
REMEMBERME_NAME=RememberMe
REMEMBERME_API_BASE_URL=http://127.0.0.1:8000
REMEMBERME_ADMIN_TOKEN=...
REMEMBERME_DOCKER_CONTAINERS=rememberme_bot-api,rememberme_bot-bot,rememberme_bot-worker,rememberme_bot-postgres
```

Если API недоступен:

- статус API = `DOWN`;
- статус DB = `unknown`;
- пользовательские метрики = `unknown`;
- статус контейнеров/процессов всё равно проверяется отдельно, если включен.

### 7.2. Инкубатор / `tg_bot_inkubator`

Предпочтительный путь MVP без изменения проекта:

- читать SQLite базу в read-only режиме;
- считать пользователей из `users`;
- считать последние критические ошибки из `critical_errors`;
- считать ошибки уведомлений из соответствующей таблицы notification log, если она есть;
- проверять процесс через Docker/systemd/PID.

Конфиг:

```env
INCUBATOR_ENABLED=true
INCUBATOR_NAME=Инкубатор
INCUBATOR_PROJECT_PATH=D:\проекты qwen\tg_bot_inkubator
INCUBATOR_DATABASE_PATH=D:\проекты qwen\tg_bot_inkubator\data\incubator_dev.db
INCUBATOR_PID_FILE=D:\проекты qwen\tg_bot_inkubator\bot.pid
INCUBATOR_DOCKER_CONTAINER=tg_bot_inkubator-bot-1
INCUBATOR_SYSTEMD_UNIT=tg-bot-inkubator.service
```

SQLite должен открываться так:

```text
file:<path>?mode=ro
```

Статус базы:

- `OK`, если файл существует и `SELECT 1` проходит;
- `DOWN`, если файл не найден или база не открывается;
- `DEGRADED`, если база открывается, но часть ожидаемых таблиц отсутствует.

## 8. Определение статусов

Статусы:

- `OK` - проверка прошла;
- `DEGRADED` - сервис частично работает, но есть проблемы;
- `DOWN` - сервис недоступен;
- `UNKNOWN` - источник данных не настроен или не может быть проверен.

Правила для общего статуса:

- если хотя бы один обязательный компонент `DOWN`, общий статус `DOWN`;
- если есть `DEGRADED` или `UNKNOWN`, общий статус `DEGRADED`;
- если всё `OK`, общий статус `OK`.

Для MVP обязательные компоненты:

- сам статус-бот;
- RememberMe API health;
- RememberMe DB readiness;
- Инкубатор DB;
- Инкубатор process/container/systemd, если задан источник проверки.

## 9. Алерты

Статус-бот должен выполнять периодические проверки, например раз в 60 секунд.

Уведомления отправляются администраторам при переходах:

- `OK -> DEGRADED`
- `OK -> DOWN`
- `DEGRADED -> DOWN`
- `DOWN -> OK`

Антиспам:

- не отправлять одинаковый алерт чаще одного раза в 10 минут;
- хранить последнее состояние в локальной базе статус-бота;
- в сообщении указывать, что именно изменилось.

Пример:

```text
RememberMe стал DOWN
API /health не отвечает 30 секунд.
Последняя успешная проверка: 2026-05-27 14:22:10 Europe/Moscow
```

## 10. Локальное хранилище статус-бота

Статус-бот должен иметь свою отдельную SQLite базу.

Минимальные таблицы:

- `status_snapshots`
  - `id`
  - `bot_key`
  - `overall_status`
  - `payload_json`
  - `created_at`
- `alert_events`
  - `id`
  - `bot_key`
  - `old_status`
  - `new_status`
  - `message`
  - `sent_at`
- `monitor_errors`
  - `id`
  - `source`
  - `message`
  - `traceback`
  - `created_at`

## 11. Безопасность

Обязательные требования:

- не хранить Telegram bot token и admin tokens в коде;
- не коммитить `.env`;
- не показывать токены в Telegram-сообщениях;
- не отправлять приватные данные пользователей;
- не читать текстовые сообщения пользователей из БД, если это не требуется для мониторинга;
- не менять базы существующих ботов;
- SQLite существующих ботов открывать только read-only;
- HTTP admin token передавать только на локальный адрес или через защищенный канал.

## 12. Что не входит в MVP

Не делать на первом этапе:

- web dashboard;
- изменение существующих двух ботов;
- полноценный Prometheus/Grafana;
- автоперезапуск упавших сервисов;
- управление деплоем;
- просмотр приватных пользовательских данных;
- массовые рассылки из статус-бота.

## 13. Что желательно добавить после MVP

Следующий этап:

- heartbeat endpoint/table для каждого бота;
- отдельный lightweight probe для `tg_bot_inkubator`;
- unified `/metrics` endpoint;
- просмотр версий и git commit;
- история доступности за 24 часа / 7 дней;
- графики в виде текстовых sparkline;
- кнопка "перезапустить сервис" только после отдельного подтверждения и отдельной настройки прав;
- экспорт отчёта;
- интеграция с Docker health/status;
- интеграция с systemd на VPS.

## 14. Критерии готовности MVP

MVP считается готовым, если:

1. Создан отдельный проект `tg_status_bot`.
2. Есть `.env.example` без секретов.
3. Бот запускается локально.
4. `/status` показывает оба бота.
5. RememberMe проверяется через HTTP health/admin API.
6. Инкубатор проверяется через read-only SQLite и process/container/systemd source.
7. `/server` показывает базовые метрики сервера.
8. Периодические проверки отправляют алерты при смене статуса.
9. Существующие проекты не изменены.
10. Есть тесты форматирования статуса и логики определения `OK/DEGRADED/DOWN`.

## 15. Рекомендованный план разработки

Этап 1:

- создать каркас `tg_status_bot`;
- добавить конфигурацию;
- добавить доступ только для админов;
- реализовать `/start`, `/status`, `/server`.

Этап 2:

- реализовать монитор RememberMe через HTTP;
- реализовать монитор Инкубатора через SQLite read-only;
- добавить форматирование детальных карточек.

Этап 3:

- добавить периодический polling;
- добавить историю статусов;
- добавить алерты на изменение состояния.

Этап 4:

- добавить Docker/systemd/process checks;
- добавить тесты;
- подготовить README и инструкции запуска.
