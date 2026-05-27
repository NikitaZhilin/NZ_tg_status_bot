from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
                    await self._handle_transition(bot, item, old_status, new_status)
                elif old_status == new_status and new_status in {"DOWN", "DEGRADED"}:
                    await self._handle_repeated_problem(bot, item, new_status)
                self.storage.save_snapshot(item.key, item.status.value, item.to_payload())
            self._latest = snapshot

    async def _handle_transition(self, bot: Bot, item: BotStatus, old_status: str, new_status: str) -> None:
        if new_status == "OK":
            self.storage.clear_pending_alert(item.key)
            await self._send_transition_alert(bot, item, old_status, new_status)
            return
        confirmations = max(self.settings.alert_failure_confirmations, 1)
        count = self.storage.upsert_pending_alert(item.key, old_status, new_status)
        if count >= confirmations:
            await self._send_transition_alert(bot, item, old_status, new_status)
            self.storage.clear_pending_alert(item.key)

    async def _handle_repeated_problem(self, bot: Bot, item: BotStatus, status: str) -> None:
        pending = self.storage.pending_alert(item.key)
        if not pending or pending.get("target_status") != status:
            return
        count = self.storage.upsert_pending_alert(item.key, pending["old_status"], status)
        if count >= max(self.settings.alert_failure_confirmations, 1):
            await self._send_transition_alert(bot, item, pending["old_status"], status)
            self.storage.clear_pending_alert(item.key)

    async def _send_transition_alert(self, bot: Bot, item: BotStatus, old_status: str, new_status: str) -> None:
        if self.storage.muted_until(item.key) or self.storage.muted_until("all"):
            return
        if self._quiet_hours_active() and new_status != "OK":
            return
        if not self.storage.should_alert(
            item.key,
            old_status,
            new_status,
            self.settings.alert_cooldown_seconds,
        ):
            return
        message = format_alert(item.name, old_status, new_status, item)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Проверить снова", callback_data=f"alert:recheck:{item.key}"),
                    InlineKeyboardButton(text="Тише на 6 часов", callback_data=f"alert:mute:{item.key}"),
                ]
            ]
        )
        for admin_id in self.settings.admin_id_set:
            try:
                await bot.send_message(admin_id, message, reply_markup=keyboard)
            except Exception:
                logger.exception("Failed to send alert to admin %s", admin_id)
        self.storage.record_alert(item.key, old_status, new_status, message)

    def _quiet_hours_active(self) -> bool:
        if not self.settings.quiet_hours_enabled:
            return False
        try:
            now_hour = datetime.now(ZoneInfo(self.settings.bot_timezone)).hour
        except Exception:
            now_hour = datetime.now().hour
        start = self.settings.quiet_hours_start
        end = self.settings.quiet_hours_end
        if start == end:
            return False
        if start < end:
            return start <= now_hour < end
        return now_hour >= start or now_hour < end

    async def _safe_check(self, source: str, awaitable) -> BotStatus | None:
        try:
            return await awaitable
        except Exception as exc:
            logger.exception("Monitor %s failed", source)
            self.storage.record_error(source, exc)
            return None
