from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot_access import is_admin
from app.config import Settings
from app.formatters import format_bot_details, format_errors, format_server_details, format_status_summary
from app.status_manager import StatusManager
from app.storage import StatusStorage


router = Router()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Статус"), KeyboardButton(text="Боты")],
            [KeyboardButton(text="RememberMe"), KeyboardButton(text="Инкубатор")],
            [KeyboardButton(text="Сервер"), KeyboardButton(text="Ошибки")],
        ],
        resize_keyboard=True,
    )


@router.message(Command("start"))
async def start(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer("Статус-бот запущен.", reply_markup=main_keyboard())


@router.message(Command("status"))
@router.message(F.text == "Статус")
async def status(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.latest()
    await message.answer(format_status_summary(snapshot.bots, snapshot.server))


@router.message(Command("refresh"))
async def refresh(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    await message.answer(format_status_summary(snapshot.bots, snapshot.server))


@router.message(Command("bots"))
@router.message(F.text == "Боты")
async def bots(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.latest()
    lines = ["Боты:"]
    for item in snapshot.bots:
        lines.append(f"- {item.name}: {item.status.value}")
    await message.answer("\n".join(lines))


@router.message(Command("bot_rememberme"))
@router.message(F.text == "RememberMe")
async def bot_rememberme(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    if not snapshot.rememberme:
        await message.answer("RememberMe monitor failed.")
        return
    await message.answer(format_bot_details(snapshot.rememberme))


@router.message(Command("bot_incubator"))
@router.message(F.text == "Инкубатор")
async def bot_incubator(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    if not snapshot.incubator:
        await message.answer("Incubator monitor failed.")
        return
    await message.answer(format_bot_details(snapshot.incubator))


@router.message(Command("server"))
@router.message(F.text == "Сервер")
async def server(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    await message.answer(format_server_details(snapshot.server))


@router.message(Command("errors"))
@router.message(F.text == "Ошибки")
async def errors(message: Message, settings: Settings, status_manager: StatusManager, storage: StatusStorage) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.latest()
    incubator_errors = None
    if snapshot.incubator:
        incubator_errors = snapshot.incubator.metrics.get("critical_errors_recent")
    await message.answer(format_errors(storage.recent_errors(), incubator_errors))

@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer()

