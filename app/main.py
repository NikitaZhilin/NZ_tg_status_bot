from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Settings, setup_logging
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
    try:
        await dispatcher.start_polling(bot)
    finally:
        loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await loop_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

