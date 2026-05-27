from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot_access import is_admin
from app.config import Settings
from app.diagnostics import (
    format_backups,
    format_containers,
    format_disk_details,
    format_log_tail,
    format_logs,
    format_restart_history,
    format_top_processes,
)
from app.formatters import (
    format_bot_details,
    format_errors,
    format_history,
    format_report,
    format_server_details,
    format_status_summary,
)
from app.restarts import RestartService
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
                InlineKeyboardButton(text="Отчёт 24ч", callback_data="refresh:report"),
                InlineKeyboardButton(text="Отчёт 7д", callback_data="refresh:report7d"),
            ],
            [
                InlineKeyboardButton(text="Перезапустить RememberMe", callback_data="restart_ask:rememberme"),
                InlineKeyboardButton(text="История перезапусков", callback_data="refresh:restart_history"),
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
        await message.answer("Мониторинг RememberMe не получил данные.")
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
        await message.answer("Мониторинг Инкубатора не получил данные.")
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


@router.message(Command("report7d"))
async def report_7d(message: Message, settings: Settings, storage: StatusStorage) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(_report_text(storage, hours=24 * 7), reply_markup=status_inline_keyboard())


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


@router.message(Command("restart_history"))
async def restart_history(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_restart_history(settings), reply_markup=status_inline_keyboard())


@router.message(Command("logs"))
async def logs(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_logs(settings))


@router.message(Command("logs_status"))
async def logs_status(message: Message, settings: Settings) -> None:
    await _send_log_tail(message, settings, "status")


@router.message(Command("logs_rememberme"))
async def logs_rememberme(message: Message, settings: Settings) -> None:
    await _send_log_tail(message, settings, "rememberme")


@router.message(Command("logs_incubator"))
async def logs_incubator(message: Message, settings: Settings) -> None:
    await _send_log_tail(message, settings, "incubator")


@router.message(Command("restart_status_bot"))
async def restart_status_bot(message: Message, settings: Settings) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, перезапустить статус-бота", callback_data="restart:confirm"),
                InlineKeyboardButton(text="Отмена", callback_data="restart:cancel"),
            ]
        ]
    )
    await message.answer(
        "Перезапустить только статус-бота?\nДругие контейнеры и сервисы затронуты не будут.",
        reply_markup=keyboard,
    )


@router.message(Command("restart_rememberme"))
async def restart_rememberme(message: Message, settings: Settings) -> None:
    await _ask_target_restart(message, settings, "rememberme", "RememberMe")


@router.message(Command("restart_incubator"))
async def restart_incubator(message: Message, settings: Settings) -> None:
    await _ask_target_restart(message, settings, "incubator", "Инкубатор")


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
        text = format_bot_details(snapshot.rememberme) if snapshot.rememberme else "Мониторинг RememberMe не получил данные."
    elif action == "incubator":
        text = format_bot_details(snapshot.incubator) if snapshot.incubator else "Мониторинг Инкубатора не получил данные."
    elif action == "server":
        text = format_server_details(snapshot.server)
    elif action == "errors":
        incubator_errors = snapshot.incubator.metrics.get("critical_errors_recent") if snapshot.incubator else None
        text = format_errors(storage.recent_errors(), incubator_errors)
    elif action == "history":
        text = _history_text(storage)
    elif action == "report":
        text = _report_text(storage)
    elif action == "report7d":
        text = _report_text(storage, hours=24 * 7)
    elif action == "restart_history":
        text = format_restart_history(settings)
    else:
        text = format_status_summary(snapshot.bots, snapshot.server)
    if callback.message:
        await callback.message.answer(text, reply_markup=status_inline_keyboard())


@router.callback_query(F.data.startswith("restart:"))
async def restart_callback(callback: CallbackQuery, settings: Settings) -> None:
    if not callback.from_user or callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    action = (callback.data or "").split(":", 1)[1]
    if action == "cancel":
        await callback.answer("Отменено.")
        if callback.message:
            await callback.message.answer("Перезапуск отменён.")
        return
    if action == "confirm":
        await callback.answer("Перезапускаю статус-бота...")
        if callback.message:
            await callback.message.answer("Статус-бот перезапускается. Через несколько секунд он снова будет доступен.")
        asyncio.create_task(_exit_for_restart())


@router.callback_query(F.data.startswith("restart_target:"))
async def restart_target_callback(callback: CallbackQuery, settings: Settings) -> None:
    if not callback.from_user or callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, bot_key, action = parts
    target_name = {"rememberme": "RememberMe", "incubator": "Инкубатор"}.get(bot_key, bot_key)
    if action == "cancel":
        await callback.answer("Отменено.")
        if callback.message:
            await callback.message.answer(f"Перезапуск {target_name} отменён.")
        return
    if action != "confirm":
        await callback.answer()
        return
    await callback.answer(f"Отправляю запрос на перезапуск {target_name}...")
    result = await RestartService(settings).request_restart(bot_key, callback.from_user.id)
    if callback.message:
        await callback.message.answer(result.message)


@router.callback_query(F.data.startswith("restart_ask:"))
async def restart_ask_callback(callback: CallbackQuery, settings: Settings) -> None:
    if not callback.from_user or callback.from_user.id not in settings.admin_id_set:
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    bot_key = (callback.data or "").split(":", 1)[1]
    target_name = {"rememberme": "RememberMe", "incubator": "Инкубатор"}.get(bot_key, bot_key)
    await callback.answer()
    if callback.message:
        await _send_target_restart_prompt(callback.message, settings, bot_key, target_name)


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


async def _ask_target_restart(message: Message, settings: Settings, bot_key: str, title: str) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await _send_target_restart_prompt(message, settings, bot_key, title)


async def _send_target_restart_prompt(message: Message, settings: Settings, bot_key: str, title: str) -> None:
    restart_target = RestartService(settings).target_for(bot_key)
    if not restart_target or not restart_target.url:
        await message.answer(
            f"{title}: перезапуск пока не подключён.\n"
            "Нужно, чтобы целевой бот реализовал POST /admin/restart и чтобы URL был добавлен в .env статус-бота."
        )
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"Да, перезапустить {title}", callback_data=f"restart_target:{bot_key}:confirm"),
                InlineKeyboardButton(text="Отмена", callback_data=f"restart_target:{bot_key}:cancel"),
            ]
        ]
    )
    await message.answer(
        f"Перезапустить {title}?\n"
        "Команда будет отправлена только в сервис перезапуска этого бота. Другие сервисы статус-бот не трогает.",
        reply_markup=keyboard,
    )


async def _send_log_tail(message: Message, settings: Settings, source: str) -> None:
    if not is_admin(message, settings):
        await message.answer("Доступ запрещен.")
        return
    await message.answer(format_log_tail(settings, source))


def _report_text(storage: StatusStorage, *, hours: int = 24) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return format_report(
        {
            "rememberme": storage.snapshots_since("rememberme", since),
            "incubator": storage.snapshots_since("incubator", since),
            "server": storage.snapshots_since("server", since),
        },
        hours=hours,
    )


async def _exit_for_restart() -> None:
    await asyncio.sleep(1.5)
    os._exit(0)
