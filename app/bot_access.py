from __future__ import annotations

from aiogram.types import Message

from app.config import Settings


def is_admin(message: Message, settings: Settings) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_id_set)

