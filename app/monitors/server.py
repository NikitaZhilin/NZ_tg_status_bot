from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

from app.config import Settings
from app.status import BotStatus, ComponentStatus, Status, combine_status


class ServerMonitor:
    key = "server"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_net_check: tuple[float, psutil._common.snetio] | None = None

    async def check(self, *, force: bool = False) -> BotStatus:
        net_metrics = self._network_metrics()
        components: list[ComponentStatus] = []
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram_percent = psutil.virtual_memory().percent
        metrics: dict = {
            "hostname": platform.node(),
            "os": platform.platform(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            **net_metrics,
        }
        components.append(
            ComponentStatus(
                "cpu",
                Status.DEGRADED if cpu_percent >= self.settings.server_cpu_warn_percent else Status.OK,
                f"{cpu_percent}% used",
                required=True,
            )
        )
        components.append(
            ComponentStatus(
                "ram",
                Status.DEGRADED if ram_percent >= self.settings.server_ram_warn_percent else Status.OK,
                f"{ram_percent}% used",
                required=True,
            )
        )
        if self.settings.telegram_api_check_enabled:
            components.append(await self._telegram_api_component())

        disk_metrics = []
        for path in self.settings.disk_path_list:
            try:
                usage = psutil.disk_usage(str(path))
            except Exception as exc:
                components.append(ComponentStatus(f"disk {path}", Status.DEGRADED, str(exc), required=True))
                continue
            disk_metrics.append(
                {
                    "path": str(path),
                    "total_gb": round(usage.total / 1024 / 1024 / 1024, 2),
                    "free_gb": round(usage.free / 1024 / 1024 / 1024, 2),
                    "percent": usage.percent,
                }
            )
            status = Status.OK if usage.percent < self.settings.server_disk_warn_percent else Status.DEGRADED
            components.append(ComponentStatus(f"disk {path}", status, f"{usage.percent}% used", required=True))

        metrics["disks"] = disk_metrics
        backup_metrics, backup_components = self._backup_components()
        log_metrics, log_components = self._log_components()
        if backup_metrics:
            metrics["backups"] = backup_metrics
        if log_metrics:
            metrics["logs"] = log_metrics
        components.extend(backup_components)
        components.extend(log_components)
        components.append(ComponentStatus("server", Status.OK, "Server metrics collected", required=True))
        return BotStatus(
            key=self.key,
            name="Server",
            status=combine_status(components),
            components=components,
            metrics=metrics,
            checked_at=datetime.now(timezone.utc),
        )

    def _network_metrics(self) -> dict:
        now = time.monotonic()
        counters = psutil.net_io_counters()
        metrics = {
            "net_bytes_sent_total": counters.bytes_sent,
            "net_bytes_recv_total": counters.bytes_recv,
            "net_sent_kbps": None,
            "net_recv_kbps": None,
            "net_interval_seconds": None,
        }
        if self._last_net_check is not None:
            previous_time, previous = self._last_net_check
            elapsed = max(now - previous_time, 0.001)
            sent_delta = max(counters.bytes_sent - previous.bytes_sent, 0)
            recv_delta = max(counters.bytes_recv - previous.bytes_recv, 0)
            metrics.update(
                {
                    "net_sent_kbps": round((sent_delta * 8) / elapsed / 1000, 2),
                    "net_recv_kbps": round((recv_delta * 8) / elapsed / 1000, 2),
                    "net_interval_seconds": round(elapsed, 1),
                }
            )
        self._last_net_check = (now, counters)
        return metrics

    async def _telegram_api_component(self) -> ComponentStatus:
        try:
            timeout = httpx.Timeout(self.settings.telegram_api_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get("https://api.telegram.org")
            if response.status_code >= 500:
                return ComponentStatus(
                    "telegram api",
                    Status.DEGRADED,
                    f"Telegram API returned HTTP {response.status_code}",
                    required=True,
                )
            return ComponentStatus("telegram api", Status.OK, "reachable", required=True)
        except httpx.TimeoutException:
            return ComponentStatus("telegram api", Status.DEGRADED, "timeout", required=True)
        except Exception as exc:
            return ComponentStatus("telegram api", Status.DEGRADED, str(exc), required=True)

    def _backup_components(self) -> tuple[list[dict], list[ComponentStatus]]:
        metrics: list[dict] = []
        components: list[ComponentStatus] = []
        now = datetime.now(timezone.utc)
        for path in self.settings.backup_path_list:
            if not path.exists():
                components.append(ComponentStatus(f"backup {path}", Status.DEGRADED, "path not found", required=True))
                metrics.append({"path": str(path), "status": "missing"})
                continue
            files = [item for item in path.rglob("*") if item.is_file()]
            if not files:
                components.append(ComponentStatus(f"backup {path}", Status.DEGRADED, "no backup files", required=True))
                metrics.append({"path": str(path), "status": "empty"})
                continue
            newest = max(files, key=lambda item: item.stat().st_mtime)
            newest_dt = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
            age_hours = round((now - newest_dt).total_seconds() / 3600, 1)
            total_mb = sum(item.stat().st_size for item in files) // 1024 // 1024
            status = Status.OK if age_hours <= self.settings.backup_warn_age_hours else Status.DEGRADED
            components.append(
                ComponentStatus(
                    f"backup {path}",
                    status,
                    f"newest {age_hours}h ago, total {total_mb} MB",
                    required=True,
                )
            )
            metrics.append(
                {
                    "path": str(path),
                    "files": len(files),
                    "total_mb": total_mb,
                    "newest": newest.name,
                    "age_hours": age_hours,
                }
            )
        return metrics, components

    def _log_components(self) -> tuple[list[dict], list[ComponentStatus]]:
        metrics: list[dict] = []
        components: list[ComponentStatus] = []
        for path in self.settings.log_path_list:
            if not path.exists():
                components.append(ComponentStatus(f"logs {path}", Status.DEGRADED, "path not found", required=True))
                metrics.append({"path": str(path), "status": "missing"})
                continue
            files = [item for item in path.rglob("*") if item.is_file()]
            total_mb = sum(_safe_size(item) for item in files) // 1024 // 1024
            status = Status.OK if total_mb <= self.settings.log_warn_total_mb else Status.DEGRADED
            components.append(
                ComponentStatus(
                    f"logs {path}",
                    status,
                    f"total {total_mb} MB",
                    required=True,
                )
            )
            metrics.append({"path": str(path), "files": len(files), "total_mb": total_mb})
        return metrics, components


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
