# Инструкция для агента RememberMe: включить restart queue на VPS

## Цель

Нужно включить уже реализованный `POST /admin/restart` в рабочем деплое RememberMe.
Код endpoint уже есть. Сейчас на VPS он должен возвращать `501`, потому что для API не задан `RESTART_REQUEST_DIR`.

Статус-бот уже подготовлен:

- будет отправлять `POST http://rememberme_bot-api:8000/admin/restart`;
- будет использовать существующий `REMEMBERME_ADMIN_TOKEN`;
- host-side processor читает `/opt/bots/rememberme/restart-requests`;
- processor перезапускает только allowlist контейнеры `rememberme_bot-bot`, `rememberme_bot-worker`, `rememberme_bot-api`.

## Что нужно сделать в RememberMe на VPS

1. Создать host-каталог очереди:

```bash
mkdir -p /opt/bots/rememberme/restart-requests
chmod 700 /opt/bots/rememberme/restart-requests
```

2. Добавить в `/opt/bots/rememberme/.env`:

```env
RESTART_REQUEST_DIR=/app/restart-requests
```

3. Пересоздать только контейнер `rememberme_bot-api`, добавив volume:

```bash
-v /opt/bots/rememberme/restart-requests:/app/restart-requests
```

Контейнеры `rememberme_bot-bot`, `rememberme_bot-worker`, `rememberme_bot-postgres`, VPN, MTProxy и другие сервисы не трогать.

4. После пересоздания API проверить безопасный отрицательный сценарий:

```bash
curl -sS -o /tmp/rm_restart_bad_confirm.json -w '%{http_code}\n' \
  -X POST \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"target":"all","confirm":"probe","requested_by":"manual-check"}' \
  http://127.0.0.1:8000/admin/restart
```

Ожидается `400`.

5. Проверить поддерживаемость queue без реального restart можно временно отправить target `api` только если готовность к перезапуску API подтверждена. Валидный запрос уже создаст настоящую заявку:

```json
{
  "target": "api",
  "confirm": "restart:rememberme",
  "requested_by": "manual-check",
  "reason": "queue smoke test"
}
```

Ожидается `202`, после чего статус-ботовский cron перезапустит `rememberme_bot-api`.

## Критерии готовности

- `GET /admin/service-status` возвращает `200`;
- `POST /admin/restart` с неверным `confirm` возвращает `400`;
- `POST /admin/restart` с валидным `confirm` больше не возвращает `501`;
- в `/opt/bots/rememberme/restart-requests` появляются JSON-заявки;
- после обработки заявки файл переносится в `processed`;
- перезапускаются только контейнеры RememberMe из allowlist.
