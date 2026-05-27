# ТЗ для RememberMe: безопасный перезапуск из статус-бота

## Цель

Добавить в RememberMe read-only/controlled admin API, чтобы статус-бот мог:

- видеть heartbeat `api`, `bot`, `worker`;
- отправлять запрос на перезапуск только RememberMe;
- не получать доступ к Docker socket, VPS, VPN, MTProxy и другим ботам.

## Уже есть

`GET /admin/service-status`

Header:

```http
X-Admin-Token: <ADMIN_TOKEN>
```

Статус-бот уже использует этот endpoint. Его нужно сохранить совместимым.

## Нужно добавить

### 1. POST /admin/restart

Header:

```http
X-Admin-Token: <ADMIN_TOKEN>
Content-Type: application/json
```

Request:

```json
{
  "target": "all",
  "confirm": "restart:rememberme",
  "requested_by": "telegram:123456789",
  "reason": "manual restart from status bot"
}
```

Allowed `target`:

- `bot`
- `worker`
- `all`

Если `confirm != "restart:rememberme"`, вернуть `400`.

Response `202 Accepted`:

```json
{
  "status": "accepted",
  "operation_id": "rm-20260527-001",
  "target": "all",
  "message": "restart scheduled"
}
```

## Требования безопасности

- Endpoint доступен только по `X-Admin-Token`.
- Токен брать только из окружения, в логи не писать.
- Не принимать shell-команды, имена контейнеров, пути, systemd units из request.
- `target` строго из allowlist.
- Перезапуск выполнять после отправки ответа, с задержкой 1-3 секунды.
- Логировать только факт операции: `operation_id`, `target`, `requested_by`, время.
- Не трогать VPN, MTProxy, Инкубатор и статус-бот.

## Рекомендованная логика

- Если RememberMe работает под Docker/systemd с `restart: unless-stopped` или `Restart=always`, допустимо завершить нужный процесс кодом `0` после ответа.
- Если `api`, `bot`, `worker` разнесены по контейнерам, API не должен получать Docker socket. Вместо этого лучше сделать внутренний restart-файл/очередь, которую читает локальный supervisor RememberMe.
- Если безопасного supervisor пока нет, endpoint должен возвращать `501` и текст `"restart is not supported by this deployment"`.

## Что статус-бот будет ожидать

В `.env` статус-бота после реализации нужно добавить:

```env
REMEMBERME_RESTART_URL=http://rememberme_bot-api:8000/admin/restart
REMEMBERME_RESTART_TOKEN=<ADMIN_TOKEN>
REMEMBERME_RESTART_TARGET=all
```

