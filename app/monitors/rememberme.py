from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.monitors.process_checks import check_docker_containers
from app.status import BotStatus, ComponentStatus, Status, combine_status


class RememberMeMonitor:
    key = "rememberme"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check(self, *, force: bool = False) -> BotStatus:
        if not self.settings.rememberme_enabled:
            component = ComponentStatus("enabled", Status.UNKNOWN, "Monitor is disabled", required=False)
            return BotStatus(self.key, self.settings.rememberme_name, Status.UNKNOWN, [component])

        base_url = self.settings.rememberme_api_base_url.rstrip("/")
        components: list[ComponentStatus] = []
        metrics: dict = {}
        timeout = httpx.Timeout(self.settings.rememberme_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            health = await self._get_json(client, f"{base_url}/health", "api health", required=True)
            components.append(health[0])
            if health[1]:
                metrics["version"] = health[1].get("version")
                metrics["service"] = health[1].get("service")

            ready = await self._get_json(client, f"{base_url}/health/ready", "api readiness", required=True)
            components.append(ready[0])
            if ready[1]:
                metrics["database"] = ready[1].get("database")
                metrics["uptime_seconds"] = ready[1].get("uptime_seconds")

            if self.settings.rememberme_admin_token:
                headers = {"X-Admin-Token": self.settings.rememberme_admin_token}
                stats = await self._get_json(client, f"{base_url}/admin/stats", "admin stats", headers=headers, required=False)
                components.append(stats[0])
                if stats[1]:
                    users = stats[1].get("users") or {}
                    metrics["users_total"] = users.get("total")
                    metrics["users_today"] = users.get("created_today")
                    metrics["users_week"] = users.get("created_week")
                    metrics["reminders"] = stats[1].get("reminders")

                activity = await self._get_json(
                    client,
                    f"{base_url}/admin/activity?days=1",
                    "activity 24h",
                    headers=headers,
                    required=False,
                )
                components.append(activity[0])
                if activity[1]:
                    metrics["events_24h"] = activity[1].get("events_24h")
                    metrics["active_users_24h"] = activity[1].get("active_other_users_24h")
            else:
                components.append(
                    ComponentStatus("admin api", Status.UNKNOWN, "REMEMBERME_ADMIN_TOKEN is not configured", required=False)
                )

        components.append(
            check_docker_containers(
                self.settings.rememberme_container_list,
                enabled=self.settings.docker_check_enabled,
            )
        )
        return BotStatus(
            key=self.key,
            name=self.settings.rememberme_name,
            status=combine_status(components),
            components=components,
            metrics=metrics,
            checked_at=datetime.now(timezone.utc),
        )

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        name: str,
        *,
        headers: dict[str, str] | None = None,
        required: bool,
    ) -> tuple[ComponentStatus, dict | None]:
        try:
            response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ComponentStatus(name, Status.DOWN, f"Timeout: {url}", required=required), None
        except Exception as exc:
            return ComponentStatus(name, Status.DOWN, f"Request failed: {exc}", required=required), None

        if response.status_code >= 500:
            return ComponentStatus(name, Status.DOWN, f"HTTP {response.status_code}", required=required), None
        if response.status_code >= 400:
            return ComponentStatus(name, Status.DEGRADED, f"HTTP {response.status_code}", required=required), None
        try:
            payload = response.json()
        except ValueError:
            return ComponentStatus(name, Status.DEGRADED, "Response is not JSON", required=required), None

        payload_status = str(payload.get("status", "ok")).lower()
        status = Status.OK if payload_status == "ok" else Status.DEGRADED
        return ComponentStatus(name, status, payload_status, payload, required=required), payload

