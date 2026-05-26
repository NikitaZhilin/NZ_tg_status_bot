from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot

from app.config import Settings
from app.formatters import format_alert
from app.monitors.incubator import IncubatorMonitor
from app.monitors.rememberme import RememberMeMonitor
from app.monitors.server import ServerMonitor
from app.status import BotStatus
from app.storage import StatusStorage

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    rememberme: BotStatus | None
    incubator: BotStatus | None
    server: BotStatus

    @property
    def bots(self) -> list[BotStatus]:
        return [item for item in [self.rememberme, self.incubator] if item is not None]


class StatusManager:
    def __init__(self, settings: Settings, storage: StatusStorage) -> None:
        self.settings = settings
        self.storage = storage
        self.rememberme = RememberMeMonitor(settings)
        self.incubator = IncubatorMonitor(settings)
        self.server = ServerMonitor(settings)
        self._latest: Snapshot | None = None
        self._lock = asyncio.Lock()

    async def refresh(self, *, force: bool = False) -> Snapshot:
        async with self._lock:
            results = await asyncio.gather(
                self._safe_check("rememberme", self.rememberme.check(force=force)),
                self._safe_check("incubator", self.incubator.check(force=force)),
                self._safe_check("server", self.server.check(force=force)),
            )
            snapshot = Snapshot(
                rememberme=results[0],
                incubator=results[1],
                server=results[2],
            )
            for item in snapshot.bots + [snapshot.server]:
                if item:
                    self.storage.save_snapshot(item.key, item.status.value, item.to_payload())
            self._latest = snapshot
            return snapshot

    async def latest(self) -> Snapshot:
        if self._latest is None:
            return await self.refresh()
        return self._latest

    async def check_alerts(self, bot: Bot) -> None:
        async with self._lock:
            results = await asyncio.gather(
                self._safe_check("rememberme", self.rememberme.check()),
                self._safe_check("incubator", self.incubator.check()),
                self._safe_check("server", self.server.check()),
            )
            snapshot = Snapshot(
                rememberme=results[0],
                incubator=results[1],
                server=results[2],
            )
            for item in snapshot.bots + [snapshot.server]:
                old_status = self.storage.last_status(item.key)
                new_status = item.status.value
                if old_status and old_status != new_status:
                    await self._send_transition_alert(bot, item, old_status, new_status)
                self.storage.save_snapshot(item.key, item.status.value, item.to_payload())
            self._latest = snapshot

    async def _send_transition_alert(self, bot: Bot, item: BotStatus, old_status: str, new_status: str) -> None:
        if not self.storage.should_alert(
            item.key,
            old_status,
            new_status,
            self.settings.alert_cooldown_seconds,
        ):
            return
        message = format_alert(item.name, old_status, new_status, item)
        for admin_id in self.settings.admin_id_set:
            try:
                await bot.send_message(admin_id, message)
            except Exception:
                logger.exception("Failed to send alert to admin %s", admin_id)
        self.storage.record_alert(item.key, old_status, new_status, message)

    async def _safe_check(self, source: str, awaitable) -> BotStatus | None:
        try:
            return await awaitable
        except Exception as exc:
            logger.exception("Monitor %s failed", source)
            self.storage.record_error(source, exc)
            return None
