from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings


@dataclass(frozen=True)
class RestartResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class RestartTarget:
    name: str
    url: str
    token: str
    target: str


class RestartService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def target_for(self, bot_key: str) -> RestartTarget | None:
        if bot_key == "rememberme":
            url = self.settings.rememberme_restart_url
            token = self.settings.rememberme_restart_token or self.settings.rememberme_admin_token
            return RestartTarget("RememberMe", url, token, self.settings.rememberme_restart_target)
        if bot_key == "incubator":
            url = self.settings.incubator_restart_url
            token = self.settings.incubator_restart_token or self.settings.incubator_admin_token
            return RestartTarget("Инкубатор", url, token, self.settings.incubator_restart_target)
        return None

    async def request_restart(self, bot_key: str, requested_by: int) -> RestartResult:
        target = self.target_for(bot_key)
        if target is None:
            return RestartResult(False, "Неизвестный бот.")
        if not target.url:
            return RestartResult(
                False,
                f"{target.name}: адрес для перезапуска не настроен. Нужен URL в .env статус-бота.",
            )
        if not target.token:
            return RestartResult(
                False,
                f"{target.name}: токен перезапуска не настроен. Нужен admin token в .env статус-бота.",
            )

        payload = {
            "target": target.target,
            "confirm": f"restart:{bot_key}",
            "requested_by": f"telegram:{requested_by}",
            "reason": "ручной перезапуск из статус-бота",
        }
        headers = {"X-Admin-Token": target.token}
        timeout = httpx.Timeout(self.settings.restart_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(target.url, json=payload, headers=headers)
        except httpx.TimeoutException:
            return RestartResult(False, f"{target.name}: таймаут запроса перезапуска.")
        except Exception as exc:
            return RestartResult(False, f"{target.name}: запрос перезапуска не выполнен - {exc}")

        if response.status_code not in {200, 202}:
            return RestartResult(False, f"{target.name}: сервис перезапуска вернул HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError:
            data = {}
        status = _restart_status_label(str(data.get("status") or "accepted"))
        operation_id = data.get("operation_id")
        suffix = f", заявка: {operation_id}" if operation_id else ""
        return RestartResult(True, f"{target.name}: запрос на перезапуск {status}{suffix}.")


def _restart_status_label(status: str) -> str:
    return {
        "accepted": "принят",
        "queued": "поставлен в очередь",
        "scheduled": "запланирован",
    }.get(status.strip().lower(), status)
