from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

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


def status_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Проверить всё", callback_data="refresh:all"),
            ],
            [
                InlineKeyboardButton(text="RememberMe", callback_data="refresh:rememberme"),
                InlineKeyboardButton(text="Инкубатор", callback_data="refresh:incubator"),
            ],
            [
                InlineKeyboardButton(text="Сервер", callback_data="refresh:server"),
                InlineKeyboardButton(text="Ошибки", callback_data="refresh:errors"),
            ],
        ]
    )


@router.message(Command("start"))
async def start(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer("Статус-бот запущен.", reply_markup=main_keyboard())
    await message.answer("Быстрая проверка:", reply_markup=status_inline_keyboard())


@router.message(Command("status"))
@router.message(F.text == "Статус")
async def status(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.latest()
    await message.answer(format_status_summary(snapshot.bots, snapshot.server), reply_markup=status_inline_keyboard())


@router.message(Command("refresh"))
async def refresh(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    await message.answer(format_status_summary(snapshot.bots, snapshot.server), reply_markup=status_inline_keyboard())


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
    await message.answer("\n".join(lines), reply_markup=status_inline_keyboard())


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
    await message.answer(format_bot_details(snapshot.rememberme), reply_markup=status_inline_keyboard())


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
    await message.answer(format_bot_details(snapshot.incubator), reply_markup=status_inline_keyboard())


@router.message(Command("server"))
@router.message(F.text == "Сервер")
async def server(message: Message, settings: Settings, status_manager: StatusManager) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    snapshot = await status_manager.refresh(force=True)
    await message.answer(format_server_details(snapshot.server), reply_markup=status_inline_keyboard())


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
    await message.answer(format_errors(storage.recent_errors(), incubator_errors), reply_markup=status_inline_keyboard())

@router.callback_query(F.data.startswith("refresh:"))
async def refresh_callback(
    callback: CallbackQuery,
    settings: Settings,
    status_manager: StatusManager,
    storage: StatusStorage,
) -> None:
    if not callback.from_user or callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    action = (callback.data or "").split(":", 1)[1]
    await callback.answer("Проверяю...")
    snapshot = await status_manager.refresh(force=True)
    if action == "rememberme":
        text = format_bot_details(snapshot.rememberme) if snapshot.rememberme else "RememberMe monitor failed."
    elif action == "incubator":
        text = format_bot_details(snapshot.incubator) if snapshot.incubator else "Incubator monitor failed."
    elif action == "server":
        text = format_server_details(snapshot.server)
    elif action == "errors":
        incubator_errors = snapshot.incubator.metrics.get("critical_errors_recent") if snapshot.incubator else None
        text = format_errors(storage.recent_errors(), incubator_errors)
    else:
        text = format_status_summary(snapshot.bots, snapshot.server)
    if callback.message:
        await callback.message.answer(text, reply_markup=status_inline_keyboard())


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer()
