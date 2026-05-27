# ТЗ для Инкубатора: heartbeat, статус и безопасный перезапуск

## Цель

Добавить в Инкубатор минимальный admin API, чтобы статус-бот мог точнее понимать состояние polling/worker и отправлять контролируемый запрос на перезапуск только Инкубатора.

Статус-бот не должен получать доступ к Docker socket, VPS shell, VPN, MTProxy или другим ботам.

## Нужно добавить

### 1. Heartbeat

Каждый обязательный процесс должен писать heartbeat:

- `bot` - Telegram polling;
- `worker` - фоновые задачи, если есть;
- `scheduler` или `notification_runner` - отправка уведомлений, если есть.

Хранить можно в SQLite в таблице, например:

```sql
CREATE TABLE IF NOT EXISTS service_heartbeat (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ok',
    last_seen_at TEXT NOT NULL,
    last_error TEXT,
    updated_at TEXT NOT NULL
);
```

Процесс обновляет запись каждые 30-60 секунд.

### 2. GET /admin/service-status

Header:

```http
X-Admin-Token: <ADMIN_TOKEN>
```

Response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "heartbeat_down_after_seconds": 120,
  "last_errors_count": 0,
  "services": {
    "bot": {
      "status": "ok",
      "last_seen_at": "2026-05-27T09:00:00Z",
      "last_error": null
    },
    "worker": {
      "status": "ok",
      "last_seen_at": "2026-05-27T09:00:00Z",
      "last_error": null
    }
  }
}
```

Логика:

- `DOWN`: обязательный сервис не писал heartbeat дольше 120 секунд.
- `DEGRADED`: есть `last_error`, сервис сам сообщил `degraded`, есть свежие critical errors, либо БД не `ok`.
- `OK`: все обязательные heartbeat свежие, БД `ok`, свежих ошибок нет.

### 3. POST /admin/restart

Header:

```http
X-Admin-Token: <ADMIN_TOKEN>
Content-Type: application/json
```

Request:

```json
{
  "target": "all",
  "confirm": "restart:incubator",
  "requested_by": "telegram:123456789",
  "reason": "manual restart from status bot"
}
```

Allowed `target`:

- `bot`
- `worker`
- `all`

Если `confirm != "restart:incubator"`, вернуть `400`.

Response `202 Accepted`:

```json
{
  "status": "accepted",
  "operation_id": "inc-20260527-001",
  "target": "all",
  "message": "restart scheduled"
}
```

## Требования безопасности

- Endpoint доступен только по `X-Admin-Token`.
- Токен брать из окружения, в логи не выводить.
- Не принимать shell-команды, пути, container names или systemd units из request.
- `target` строго из allowlist.
- Перезапуск выполнять после ответа, с задержкой 1-3 секунды.
- Логировать только `operation_id`, `target`, `requested_by`, время.
- Если Инкубатор не запущен под supervisor/Docker/systemd, который поднимет процесс заново, endpoint должен вернуть `501`.

## Что статус-бот будет ожидать

После реализации добавить в `.env` статус-бота:

```env
INCUBATOR_API_BASE_URL=http://<incubator-api-host>:<port>
INCUBATOR_ADMIN_TOKEN=<ADMIN_TOKEN>
INCUBATOR_RESTART_URL=http://<incubator-api-host>:<port>/admin/restart
INCUBATOR_RESTART_TOKEN=<ADMIN_TOKEN>
INCUBATOR_RESTART_TARGET=all
```

После этого статус-бот начнёт использовать `GET /admin/service-status` Инкубатора и разрешит команду `/restart_incubator`.

