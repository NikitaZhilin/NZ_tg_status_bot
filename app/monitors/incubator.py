from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import httpx

from app.config import Settings
from app.monitors.process_checks import check_docker_container, check_pid_file, check_systemd_unit
from app.status import BotStatus, ComponentStatus, Status, combine_status


class IncubatorMonitor:
    key = "incubator"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check(self, *, force: bool = False) -> BotStatus:
        if not self.settings.incubator_enabled:
            component = ComponentStatus("enabled", Status.UNKNOWN, "Monitor is disabled", required=False)
            return BotStatus(self.key, self.settings.incubator_name, Status.UNKNOWN, [component])

        components: list[ComponentStatus] = []
        metrics: dict = {}
        if self.settings.incubator_api_base_url and self.settings.incubator_admin_token:
            service_component, service_metrics = await self._check_service_status()
            components.append(service_component)
            metrics.update(service_metrics)

        db_component, db_metrics = await self._check_database(self.settings.incubator_database_path)
        components.append(db_component)
        metrics.update(db_metrics)

        if self.settings.incubator_pid_file:
            components.append(check_pid_file(self.settings.incubator_pid_file, required=False))
        components.append(
            check_docker_container(
                self.settings.incubator_docker_container,
                enabled=self.settings.docker_check_enabled,
            )
        )
        components.append(
            check_systemd_unit(
                self.settings.incubator_systemd_unit,
                enabled=self.settings.systemd_check_enabled,
            )
        )

        return BotStatus(
            key=self.key,
            name=self.settings.incubator_name,
            status=combine_status(components),
            components=components,
            metrics=metrics,
            checked_at=datetime.now(timezone.utc),
        )

    async def _check_database(self, path: Path | None) -> tuple[ComponentStatus, dict]:
        if not path:
            return ComponentStatus("sqlite", Status.UNKNOWN, "INCUBATOR_DATABASE_PATH is not configured", required=True), {}
        if not path.exists():
            return ComponentStatus("sqlite", Status.DOWN, f"Database file not found: {path}", required=True), {}

        uri = f"{path.resolve().as_uri()}?mode=ro"
        try:
            async with aiosqlite.connect(uri, uri=True) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("SELECT 1")
                tables = await self._table_names(db)
                metrics = await self._read_metrics(db, tables)
        except Exception as exc:
            return ComponentStatus("sqlite", Status.DOWN, f"Cannot read database: {exc}", required=True), {}

        missing = {"users", "critical_errors"} - set(tables)
        if missing:
            return (
                ComponentStatus("sqlite", Status.DEGRADED, f"Missing tables: {', '.join(sorted(missing))}", {"tables": tables}, required=True),
                metrics,
            )
        return ComponentStatus("sqlite", Status.OK, "Database is readable", {"tables": tables}, required=True), metrics

    async def _check_service_status(self) -> tuple[ComponentStatus, dict]:
        url = f"{self.settings.incubator_api_base_url.rstrip('/')}/admin/service-status"
        headers = {"X-Admin-Token": self.settings.incubator_admin_token}
        timeout = httpx.Timeout(self.settings.incubator_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ComponentStatus("service status", Status.DOWN, "Timeout", required=True), {}
        except Exception as exc:
            return ComponentStatus("service status", Status.DOWN, f"Request failed: {exc}", required=True), {}

        if response.status_code >= 500:
            return ComponentStatus("service status", Status.DOWN, f"HTTP {response.status_code}", required=True), {}
        if response.status_code >= 400:
            return ComponentStatus("service status", Status.DEGRADED, f"HTTP {response.status_code}", required=True), {}
        try:
            payload = response.json()
        except ValueError:
            return ComponentStatus("service status", Status.DEGRADED, "Response is not JSON", required=True), {}

        raw_status = str(payload.get("status", "")).lower()
        if raw_status == "ok":
            status = Status.OK
        elif raw_status == "down":
            status = Status.DOWN
        elif raw_status == "degraded":
            status = Status.DEGRADED
        else:
            status = Status.UNKNOWN
        metrics = {
            "service_status": payload.get("status"),
            "service_status_version": payload.get("version"),
            "service_status_database": payload.get("db") or payload.get("database"),
            "heartbeat_down_after_seconds": payload.get("heartbeat_down_after_seconds"),
            "last_errors_count": payload.get("last_errors_count"),
            "services": payload.get("services"),
        }
        return ComponentStatus("service status", status, raw_status or "unknown", payload, required=True), metrics

    async def _table_names(self, db: aiosqlite.Connection) -> list[str]:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        rows = await cursor.fetchall()
        return [str(row["name"]) for row in rows]

    async def _read_metrics(self, db: aiosqlite.Connection, tables: list[str]) -> dict:
        metrics: dict = {}
        if "users" in tables:
            metrics["users_total"] = await self._scalar(db, "SELECT COUNT(*) FROM users")
            metrics["users_active"] = await self._scalar(db, "SELECT COUNT(*) FROM users WHERE is_active = 1")
            metrics["users_seen_24h"] = await self._scalar(
                db,
                "SELECT COUNT(*) FROM users WHERE last_seen_at >= datetime('now', '-1 day')",
            )
        if "critical_errors" in tables:
            metrics["critical_errors_total"] = await self._scalar(db, "SELECT COUNT(*) FROM critical_errors")
            metrics["critical_errors_recent"] = await self._rows(
                db,
                """
                SELECT source, message, created_at
                FROM critical_errors
                ORDER BY created_at DESC
                LIMIT 5
                """,
            )
        if "notification_log" in tables:
            metrics["notification_failures"] = await self._scalar(
                db,
                "SELECT COUNT(*) FROM notification_log WHERE status = 'failed'",
            )
        return metrics

    async def _scalar(self, db: aiosqlite.Connection, query: str) -> int:
        cursor = await db.execute(query)
        row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0

    async def _rows(self, db: aiosqlite.Connection, query: str) -> list[dict]:
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
