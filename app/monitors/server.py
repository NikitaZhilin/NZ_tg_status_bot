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
        self._last_net_check: tuple[float, psutil._common.snetio] | None = None

    async def check(self, *, force: bool = False) -> BotStatus:
        net_metrics = self._network_metrics()
        components: list[ComponentStatus] = []
        metrics: dict = {
            "hostname": platform.node(),
            "os": platform.platform(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            **net_metrics,
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
