from __future__ import annotations

import platform
import time
from datetime import datetime, timezone

import psutil

from app.config import Settings
from app.status import BotStatus, ComponentStatus, Status, combine_status


class ServerMonitor:
    key = "server"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check(self, *, force: bool = False) -> BotStatus:
        components: list[ComponentStatus] = []
        metrics: dict = {
            "hostname": platform.node(),
            "os": platform.platform(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
        }

        disk_metrics = []
        for path in self.settings.disk_path_list:
            try:
                usage = psutil.disk_usage(str(path))
            except Exception as exc:
                components.append(ComponentStatus(f"disk {path}", Status.DEGRADED, str(exc), required=False))
                continue
            disk_metrics.append(
                {
                    "path": str(path),
                    "total_gb": round(usage.total / 1024 / 1024 / 1024, 2),
                    "free_gb": round(usage.free / 1024 / 1024 / 1024, 2),
                    "percent": usage.percent,
                }
            )
            status = Status.OK if usage.percent < 90 else Status.DEGRADED
            components.append(ComponentStatus(f"disk {path}", status, f"{usage.percent}% used", required=False))

        metrics["disks"] = disk_metrics
        components.append(ComponentStatus("server", Status.OK, "Server metrics collected", required=True))
        return BotStatus(
            key=self.key,
            name="Server",
            status=combine_status(components),
            components=components,
            metrics=metrics,
            checked_at=datetime.now(timezone.utc),
        )

