# NZ Telegram Status Bot

Отдельный Telegram-бот для мониторинга рабочих ботов и сервера.

## MVP

- `/status` - общая сводка по ботам и серверу.
- `/bots` - список ботов.
- `/bot_rememberme` - детальная проверка `tg_bot/new_architecture`.
- `/bot_incubator` - детальная проверка `tg_bot_inkubator`.
- `/server` - CPU, RAM, диск, uptime.
- `/errors` - последние ошибки мониторов.
- `/refresh` - принудительное обновление статуса.
- `/history` - история статусов за 24 часа.
- `/report` - краткий отчёт за 24 часа.
- `/report7d` - краткий отчёт за 7 дней.
- `/top` - top процессов, доступных из окружения статус-бота.
- `/disk` - диск и inode.
- `/backups` - возраст и размер backup-файлов.
- `/logs` - размер логов.
- `/containers` - Docker containers, если явно подключён Docker API.
- `/restart_status_bot` - перезапуск только статус-бота с подтверждением.
- `/restart_rememberme` - запрос перезапуска RememberMe, если целевой endpoint настроен.
- `/restart_incubator` - запрос перезапуска Инкубатора, если целевой endpoint настроен.

Фоновая проверка и регулярная сводка по умолчанию запускаются раз в 2 часа:

- `CHECK_INTERVAL_SECONDS=7200`
- `SUMMARY_INTERVAL_SECONDS=7200`
- `SEND_PERIODIC_SUMMARY=true`

## Локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполнить `.env`, затем:

```powershell
python -m app.main
```

Токены не хранятся в репозитории. `.env` добавлен в `.gitignore`.

## Безопасный список контейнеров

Команда `/containers` по умолчанию читает JSON snapshot из `CONTAINERS_SNAPSHOT_PATH`.
Так статус-боту не нужен доступ к `/var/run/docker.sock`.

На VPS можно обновлять snapshot cron-задачей:

```bash
/opt/nz_tg_status_bot/scripts/write-container-snapshot.sh /opt/nz_tg_status_bot/data/container-status.json
```

## VPS deploy

Деплой из GitHub Actions изолирован в отдельный каталог и отдельный Docker Compose project name: `nz_tg_status_bot`.

Нужно добавить GitHub Secrets:

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_KEY`
- `VPS_PORT` - опционально, по умолчанию `22`
- `VPS_APP_DIR` - опционально, по умолчанию `/opt/nz_tg_status_bot`
- `BOT_TOKEN`
- `ADMIN_IDS`
- `REMEMBERME_API_BASE_URL`
- `REMEMBERME_ADMIN_TOKEN`
- `INCUBATOR_DATABASE_PATH`
- `INCUBATOR_PID_FILE`

Если этот ПК уже имеет SSH-ключи для других репозиториев, не используйте их автоматически. Для деплоя лучше создать отдельный VPS deploy key:

```powershell
.\scripts\create-vps-deploy-key.ps1
```

Публичный ключ из вывода нужно добавить на VPS в `~/.ssh/authorized_keys` пользователя деплоя. После этого:

```powershell
.\scripts\setup-github-secrets.ps1
```

Если ключ ещё не создан, можно одной командой:

```powershell
.\scripts\setup-github-secrets.ps1 -GenerateDeployKey
```

Скрипт использует `%USERPROFILE%\.ssh\nz_tg_status_bot_deploy_ed25519`, кладёт приватный ключ в `VPS_SSH_KEY` и интерактивно запрашивает остальные secrets. В репозиторий секреты не записываются.

Workflow не выполняет `docker system prune`, не останавливает чужие контейнеры и работает только с compose-проектом `nz_tg_status_bot`.

Если `gh` не установлен:

```powershell
winget install --id GitHub.cli
gh auth login
```
