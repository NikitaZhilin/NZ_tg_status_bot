from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot_access import is_admin
from app.config import Settings
from app.diagnostics import format_backups, format_containers, format_disk_details, format_logs, format_top_processes
from app.formatters import (
    format_bot_details,
    format_errors,
    format_history,
    format_report,
    format_server_details,
    format_status_summary,
)
from app.status_manager import StatusManager
from app.storage import StatusStorage


router = Router()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Статус"), KeyboardButton(text="Боты")],
            [KeyboardButton(text="RememberMe"), KeyboardButton(text="Инкубатор")],
            [KeyboardButton(text="Сервер"), KeyboardButton(text="Ошибки")],
            [KeyboardButton(text="История"), KeyboardButton(text="Отчёт")],
        ],
        resize_keyboard=True,
    )


def status_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить всё", callback_data="refresh:all")],
            [
                InlineKeyboardButton(text="RememberMe", callback_data="refresh:rememberme"),
                InlineKeyboardButton(text="Инкубатор", callback_data="refresh:incubator"),
            ],
            [
                InlineKeyboardButton(text="Сервер", callback_data="refresh:server"),
                InlineKeyboardButton(text="Ошибки", callback_data="refresh:errors"),
            ],
            [
                InlineKeyboardButton(text="История", callback_data="refresh:history"),
                InlineKeyboardButton(text="Отчёт", callback_data="refresh:report"),
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
    incubator_errors = snapshot.incubator.metrics.get("critical_errors_recent") if snapshot.incubator else None
    await message.answer(format_errors(storage.recent_errors(), incubator_errors), reply_markup=status_inline_keyboard())


@router.message(Command("history"))
@router.message(F.text == "История")
async def history(message: Message, settings: Settings, storage: StatusStorage) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(_history_text(storage), reply_markup=status_inline_keyboard())


@router.message(Command("report"))
@router.message(F.text == "Отчёт")
async def report(message: Message, settings: Settings, storage: StatusStorage) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(_report_text(storage), reply_markup=status_inline_keyboard())


@router.message(Command("top"))
async def top(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_top_processes())


@router.message(Command("disk"))
async def disk(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_disk_details(settings))


@router.message(Command("backups"))
async def backups(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_backups(settings))


@router.message(Command("containers"))
async def containers(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_containers(settings))


@router.message(Command("logs"))
async def logs(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_logs(settings))


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
    elif action == "history":
        text = _history_text(storage)
    elif action == "report":
        text = _report_text(storage)
    else:
        text = format_status_summary(snapshot.bots, snapshot.server)
    if callback.message:
        await callback.message.answer(text, reply_markup=status_inline_keyboard())


@router.callback_query(F.data.startswith("alert:"))
async def alert_callback(
    callback: CallbackQuery,
    settings: Settings,
    status_manager: StatusManager,
    storage: StatusStorage,
) -> None:
    if not callback.from_user or callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, action, bot_key = parts
    if action == "mute":
        storage.mute_alerts(bot_key, 6 * 3600, reason=f"muted by {callback.from_user.id}")
        await callback.answer("Алерты приглушены на 6 часов.", show_alert=True)
        return
    if action == "recheck":
        await callback.answer("Проверяю...")
        snapshot = await status_manager.refresh(force=True)
        item = {
            "rememberme": snapshot.rememberme,
            "incubator": snapshot.incubator,
            "server": snapshot.server,
        }.get(bot_key)
        if item is None:
            text = "Нет данных."
        elif bot_key == "server":
            text = format_server_details(item)
        else:
            text = format_bot_details(item)
        if callback.message:
            await callback.message.answer(text, reply_markup=status_inline_keyboard())


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer()


def _history_text(storage: StatusStorage) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return "\n".join(
        [
            format_history("rememberme", storage.snapshots_since("rememberme", since), hours=24),
            "",
            format_history("incubator", storage.snapshots_since("incubator", since), hours=24),
            "",
            format_history("server", storage.snapshots_since("server", since), hours=24),
        ]
    )


def _report_text(storage: StatusStorage) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return format_report(
        {
            "rememberme": storage.snapshots_since("rememberme", since),
            "incubator": storage.snapshots_since("incubator", since),
            "server": storage.snapshots_since("server", since),
        },
        hours=24,
    )
