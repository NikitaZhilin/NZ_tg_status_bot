from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Settings, setup_logging
from app.formatters import format_status_summary
from app.handlers import router
from app.status_manager import StatusManager
from app.storage import StatusStorage


logger = logging.getLogger(__name__)


async def alert_loop(bot: Bot, manager: StatusManager, settings: Settings) -> None:
    while True:
        try:
            await manager.check_alerts(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alert loop failed")
        await asyncio.sleep(settings.check_interval_seconds)


async def summary_loop(bot: Bot, manager: StatusManager, settings: Settings) -> None:
    if not settings.send_periodic_summary:
        logger.info("Periodic summary is disabled")
        return
    if not settings.admin_id_set:
        logger.warning("Periodic summary is enabled, but ADMIN_IDS is empty")
        return

    if settings.summary_on_startup:
        await _send_summary(bot, manager, settings)

    while True:
        await asyncio.sleep(settings.summary_interval_seconds)
        try:
            await _send_summary(bot, manager, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic summary loop failed")


async def _send_summary(bot: Bot, manager: StatusManager, settings: Settings) -> None:
    snapshot = await manager.refresh(force=True)
    text = format_status_summary(snapshot.bots, snapshot.server)
    for admin_id in settings.admin_id_set:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Failed to send periodic summary to admin %s", admin_id)


async def main() -> None:
    settings = Settings()
    setup_logging(settings)
    storage = StatusStorage(settings.status_db_path)
    storage.initialize()
    manager = StatusManager(settings, storage)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher["settings"] = settings
    dispatcher["storage"] = storage
    dispatcher["status_manager"] = manager
    dispatcher.include_router(router)

    loop_task = asyncio.create_task(alert_loop(bot, manager, settings))
    summary_task = asyncio.create_task(summary_loop(bot, manager, settings))
    try:
        await dispatcher.start_polling(bot)
    finally:
        for task in (loop_task, summary_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
