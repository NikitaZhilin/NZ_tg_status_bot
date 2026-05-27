from __future__ import annotations

from datetime import datetime
from typing import Any

from app.status import BotStatus, Status, combine_bot_statuses


STATUS_RU = {
    Status.OK.value: "работает",
    Status.DEGRADED.value: "работает с проблемами",
    Status.DOWN.value: "недоступен",
    Status.UNKNOWN.value: "неизвестно",
}

COMPONENT_RU = {
    "api health": "API: базовая проверка",
    "api readiness": "API: готовность и база",
    "admin stats": "админ-статистика",
    "activity 24h": "активность за 24 часа",
    "service status": "статус сервисов",
    "cpu": "процессор",
    "ram": "оперативная память",
    "docker": "Docker",
    "telegram api": "Telegram API",
    "sqlite": "SQLite база",
    "pid": "PID-процесс",
    "systemd": "systemd-сервис",
    "server": "сервер",
}

METRIC_RU = {
    "version": "версия",
    "service": "сервис",
    "database": "база данных",
    "uptime_seconds": "uptime",
    "users_total": "пользователей всего",
    "users_today": "новых пользователей сегодня",
    "users_week": "новых пользователей за 7 дней",
    "users_active": "активных пользователей",
    "users_seen_24h": "пользователей за 24 часа",
    "active_users_24h": "активных пользователей за 24 часа",
    "events_24h": "событий за 24 часа",
    "critical_errors_total": "критических ошибок всего",
    "critical_errors_recent": "последние критические ошибки",
    "notification_failures": "ошибок уведомлений",
    "reminders": "напоминания",
    "service_status": "статус сервисов",
    "service_status_version": "версия сервисов",
    "service_status_database": "база данных сервисов",
    "heartbeat_down_after_seconds": "таймаут heartbeat",
    "last_errors_count": "последние ошибки",
    "services": "сервисы",
}


def format_status_summary(bots: list[BotStatus], server: BotStatus | None = None) -> str:
    items = list(bots)
    if server:
        items.append(server)
    overall = combine_bot_statuses(items)
    lines = [f"Общий статус: {_status_label(overall)}", ""]
    for item in bots:
        lines.extend(_format_bot_short(item))
        lines.append("")
    if server:
        lines.extend(_format_server_short(server))
    return "\n".join(lines).strip()


def format_bot_details(item: BotStatus) -> str:
    lines = [
        f"{_bot_name_ru(item.name)}: {_status_label(item.status)}",
        f"Проверено: {_format_dt(item.checked_at)}",
        "",
        "Компоненты:",
    ]
    visible_components = [
        component
        for component in item.components
        if component.required or component.status != Status.UNKNOWN
    ]
    if visible_components:
        for component in visible_components:
            required = "обязательный" if component.required else "дополнительный"
            message = f" - {_message_ru(component.message)}" if component.message else ""
            lines.append(
                f"- {_component_name_ru(component.name)}: "
                f"{_status_label(component.status)} ({required}){message}"
            )
    else:
        lines.append("- нет настроенных проверок")

    metric_lines = [_format_metric(key, value) for key, value in item.metrics.items()]
    metric_lines = [line for line in metric_lines if line]
    if metric_lines:
        lines.extend(["", "Метрики:", *metric_lines])
    return "\n".join(lines)


def format_server_details(item: BotStatus) -> str:
    metrics = item.metrics
    lines = [
        f"Сервер: {_status_label(item.status)}",
        f"Хост: {metrics.get('hostname', '-')}",
        f"ОС: {metrics.get('os', '-')}",
        f"Время работы: {_format_duration(metrics.get('uptime_seconds'))}",
        f"Процессор: {metrics.get('cpu_percent', '-')}%",
        f"Оперативная память: {metrics.get('ram_percent', '-')}%",
        f"Сеть входящая: {_format_speed(metrics.get('net_recv_kbps'))}",
        f"Сеть исходящая: {_format_speed(metrics.get('net_sent_kbps'))}",
    ]
    if item.components:
        lines.extend(["", "Проверки:"])
        for component in item.components:
            message = f" - {_message_ru(component.message)}" if component.message else ""
            lines.append(f"- {_component_name_ru(component.name)}: {_status_label(component.status)}{message}")
    disks = metrics.get("disks") or []
    if disks:
        lines.extend(["", "Диски:"])
        for disk in disks:
            lines.append(
                f"- {disk.get('path')}: занято {disk.get('percent')}%, "
                f"свободно {disk.get('free_gb')} GB"
            )
    return "\n".join(lines)


def format_errors(errors: list[dict[str, Any]], incubator_errors: list[dict[str, Any]] | None = None) -> str:
    lines = ["Ошибки мониторинга:"]
    if errors:
        for row in errors[:10]:
            lines.append(f"- {row.get('created_at')} {row.get('source')}: {row.get('message')}")
    else:
        lines.append("- нет")

    if incubator_errors is not None:
        lines.extend(["", "Последние критические ошибки Инкубатора:"])
        if incubator_errors:
            for row in incubator_errors[:5]:
                lines.append(f"- {row.get('created_at')} {row.get('source')}: {row.get('message')}")
        else:
            lines.append("- нет")
    return "\n".join(lines)


def format_history(bot_key: str, snapshots: list[dict[str, Any]], hours: int = 24) -> str:
    title = _history_name(bot_key)
    if not snapshots:
        return f"{title}: истории за {hours} ч. пока нет."
    total = len(snapshots)
    ok_count = sum(1 for item in snapshots if item["overall_status"] == Status.OK.value)
    uptime = round((ok_count / total) * 100, 1) if total else 0
    transitions = _transitions(snapshots)
    down_count = sum(1 for item in transitions if item["new"] == Status.DOWN.value)
    recovery_minutes = _average_recovery_minutes(snapshots)
    spark = " ".join(_short_status(item["overall_status"]) for item in snapshots[-12:])
    lines = [
        f"{title}: история за {hours} ч.",
        f"Проверок: {total}",
        f"Uptime по проверкам: {uptime}%",
        f"Переходов в DOWN: {down_count}",
        f"Среднее восстановление: {_format_recovery_minutes(recovery_minutes)}",
        f"График: {spark}",
        "",
        "Последние смены статуса:",
    ]
    if transitions:
        for item in transitions[-10:]:
            lines.append(f"- {item['created_at']}: {item['old']} -> {item['new']}")
    else:
        lines.append("- не было")
    return "\n".join(lines)


def format_report(history_by_bot: dict[str, list[dict[str, Any]]], hours: int = 24) -> str:
    lines = [f"Отчёт за {hours} ч."]
    for bot_key, snapshots in history_by_bot.items():
        if not snapshots:
            lines.append(f"- {_history_name(bot_key)}: нет данных")
            continue
        total = len(snapshots)
        ok_count = sum(1 for item in snapshots if item["overall_status"] == Status.OK.value)
        uptime = round((ok_count / total) * 100, 1) if total else 0
        transitions = _transitions(snapshots)
        down_count = sum(1 for item in transitions if item["new"] == Status.DOWN.value)
        recovery_minutes = _average_recovery_minutes(snapshots)
        current = snapshots[-1]["overall_status"]
        lines.append(
            f"- {_history_name(bot_key)}: сейчас {STATUS_RU.get(current, current)} ({current}), "
            f"uptime {uptime}%, DOWN {down_count}, "
            f"среднее восстановление {_format_recovery_minutes(recovery_minutes)}, проверок {total}"
        )
    return "\n".join(lines)


def format_alert(name: str, old_status: str, new_status: str, item: BotStatus) -> str:
    failed = [
        component
        for component in item.components
        if component.status in {Status.DOWN, Status.DEGRADED}
    ]
    recovered = new_status == Status.OK.value
    title = f"{_bot_name_ru(name)}: восстановлен" if recovered else f"{_bot_name_ru(name)}: изменился статус"
    lines = [
        title,
        "",
        f"Уровень: {_alert_level(new_status)}",
        f"Было: {STATUS_RU.get(old_status, old_status)} ({old_status})",
        f"Стало: {STATUS_RU.get(new_status, new_status)} ({new_status})",
        f"Проверено: {_format_dt(item.checked_at)}",
    ]

    reason = _alert_reason(item, failed, recovered)
    if reason:
        lines.extend(["", f"Причина: {reason}"])

    metric_lines = _format_alert_metrics(item)
    if metric_lines:
        lines.extend(["", "Метрики:", *metric_lines])

    if failed:
        lines.extend(["", "Проблемные компоненты:"])
        for component in failed[:5]:
            message = f" - {_message_ru(component.message)}" if component.message else ""
            lines.append(
                f"- {_component_name_ru(component.name)}: "
                f"{_status_label(component.status)}{message}"
            )
    else:
        lines.extend(["", "Компоненты: критичных проблем не найдено."])
    return "\n".join(lines)


def _format_bot_short(item: BotStatus) -> list[str]:
    metrics = item.metrics
    lines = [f"{_bot_name_ru(item.name)}: {_status_label(item.status)}"]
    users = metrics.get("users_total")
    if users is not None:
        parts = [f"всего {users}"]
        if metrics.get("active_users_24h") is not None:
            parts.append(f"активных за 24 часа {metrics['active_users_24h']}")
        if metrics.get("users_active") is not None:
            parts.append(f"активных {metrics['users_active']}")
        if metrics.get("users_seen_24h") is not None:
            parts.append(f"были за 24 часа {metrics['users_seen_24h']}")
        lines.append("Пользователи: " + ", ".join(parts))
    if metrics.get("version"):
        lines.append(f"Версия: {metrics['version']}")
    if metrics.get("critical_errors_total") is not None:
        lines.append(f"Критические ошибки: {metrics['critical_errors_total']}")
    return lines


def _history_name(bot_key: str) -> str:
    return {
        "rememberme": "RememberMe",
        "incubator": "Инкубатор",
        "server": "Сервер",
    }.get(bot_key, bot_key)


def _short_status(status: str) -> str:
    return {
        "OK": "OK",
        "DEGRADED": "WARN",
        "DOWN": "DOWN",
        "UNKNOWN": "UNK",
    }.get(status, status)


def _transitions(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    previous = None
    for item in snapshots:
        current = item["overall_status"]
        if previous is not None and current != previous:
            result.append({"old": previous, "new": current, "created_at": item["created_at"]})
        previous = current
    return result


def _average_recovery_minutes(snapshots: list[dict[str, Any]]) -> float | None:
    problem_started_at: datetime | None = None
    durations: list[float] = []
    for item in snapshots:
        created_at = _parse_snapshot_dt(item.get("created_at"))
        if created_at is None:
            continue
        status = item["overall_status"]
        if status in {Status.DOWN.value, Status.DEGRADED.value} and problem_started_at is None:
            problem_started_at = created_at
        elif status == Status.OK.value and problem_started_at is not None:
            durations.append((created_at - problem_started_at).total_seconds() / 60)
            problem_started_at = None
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def _parse_snapshot_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_recovery_minutes(value: float | None) -> str:
    if value is None:
        return "нет данных"
    if value < 60:
        return f"{value} мин."
    hours = int(value // 60)
    minutes = int(value % 60)
    return f"{hours} ч. {minutes} мин."


def _alert_level(new_status: str) -> str:
    if new_status == Status.DOWN.value:
        return "critical"
    if new_status == Status.DEGRADED.value:
        return "warning"
    if new_status == Status.OK.value:
        return "info"
    return "unknown"


def _format_server_short(item: BotStatus) -> list[str]:
    metrics = item.metrics
    lines = [
        f"Сервер: {_status_label(item.status)}",
        f"Процессор: {metrics.get('cpu_percent', '-')}%",
        f"Оперативная память: {metrics.get('ram_percent', '-')}%",
        f"Сеть вход/выход: {_format_speed(metrics.get('net_recv_kbps'))} / {_format_speed(metrics.get('net_sent_kbps'))}",
        f"Время работы: {_format_duration(metrics.get('uptime_seconds'))}",
    ]
    disks = metrics.get("disks") or []
    if disks:
        first = disks[0]
        lines.append(f"Диск: свободно {first.get('free_gb')} GB, занято {first.get('percent')}%")
    return lines


def _status_label(status: Status) -> str:
    return f"{STATUS_RU.get(status.value, status.value)} ({status.value})"


def _component_name_ru(name: str) -> str:
    if name.startswith("backup "):
        return "backup " + name.removeprefix("backup ")
    if name.startswith("logs "):
        return "логи " + name.removeprefix("logs ")
    if name.startswith("disk "):
        return "диск " + name.removeprefix("disk ")
    return COMPONENT_RU.get(name, name)


def _bot_name_ru(name: str) -> str:
    if name.lower() == "incubator":
        return "Инкубатор"
    return name


def _message_ru(message: str) -> str:
    replacements = {
        "ok": "успешно",
        "Database is readable": "база доступна для чтения",
        "Docker check is disabled": "проверка Docker отключена",
        "systemd check is disabled": "проверка systemd отключена",
        "PID file is not configured": "PID-файл не настроен",
        "Cannot read PID file": "не удалось прочитать PID-файл",
        "Timeout": "таймаут",
        "Request failed": "запрос не выполнен",
        "Response is not JSON": "ответ не JSON",
        "reachable": "доступен",
        "timeout": "таймаут",
        "path not found": "путь не найден",
        "no backup files": "backup-файлов нет",
        "Server metrics collected": "метрики сервера собраны",
    }
    for source, target in replacements.items():
        if message == source:
            return target
        if message.startswith(source):
            return message.replace(source, target, 1)
    return message


def _format_metric(key: str, value: Any) -> str:
    label = METRIC_RU.get(key, key)
    if key == "uptime_seconds":
        return f"- {label}: {_format_duration(value)}"
    if key == "critical_errors_recent" and isinstance(value, list):
        return f"- {label}: {len(value)}"
    if isinstance(value, list):
        return f"- {label}: {len(value)}"
    if isinstance(value, dict):
        if key == "services":
            return _format_services_metric(value)
        return f"- {label}: {_compact_dict(value)}"
    return f"- {label}: {value}"


def _format_services_metric(value: dict[str, Any]) -> str:
    chunks: list[str] = []
    for service_name in ("api", "bot", "worker"):
        service = value.get(service_name)
        if not isinstance(service, dict):
            continue
        raw_status = str(service.get("status", "unknown")).upper()
        item = f"{_service_name_ru(service_name)}: {STATUS_RU.get(raw_status, raw_status)} ({raw_status})"
        last_seen = service.get("last_seen_at") or service.get("last_seen")
        if last_seen:
            item += f", heartbeat {last_seen}"
        if service.get("last_error"):
            item += ", есть ошибка"
        chunks.append(item)
    if not chunks:
        return "- сервисы: нет данных"
    return "- сервисы: " + "; ".join(chunks)


def _service_name_ru(name: str) -> str:
    return {
        "api": "API",
        "bot": "Telegram-бот",
        "worker": "фоновый обработчик",
    }.get(name, name)


def _format_duration(seconds: Any) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days} д. {hours} ч."
    if hours:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."


def _format_speed(kbps: Any) -> str:
    if kbps is None:
        return "будет после следующей проверки"
    value = float(kbps)
    if value >= 1000:
        return f"{round(value / 1000, 2)} Мбит/с"
    return f"{round(value, 2)} Кбит/с"


def _format_dt(value: datetime) -> str:
    return value.astimezone().strftime("%d.%m.%Y %H:%M:%S")


def _compact_dict(value: dict[str, Any]) -> str:
    return ", ".join(f"{METRIC_RU.get(key, key)}={item}" for key, item in list(value.items())[:8])


def _alert_reason(item: BotStatus, failed: list, recovered: bool) -> str:
    if recovered:
        return "обязательные проверки снова проходят успешно."
    required_failed = [component for component in failed if component.required]
    if required_failed:
        component = required_failed[0]
        return f"обязательный компонент `{_component_name_ru(component.name)}` сообщил `{component.status.value}`."
    if failed:
        component = failed[0]
        return f"дополнительный компонент `{_component_name_ru(component.name)}` сообщил `{component.status.value}`."
    if item.status == Status.UNKNOWN:
        return "нет достоверных данных от источников мониторинга."
    return ""


def _format_alert_metrics(item: BotStatus) -> list[str]:
    metrics = item.metrics
    lines: list[str] = []
    if metrics.get("version"):
        lines.append(f"- версия: {metrics['version']}")
    if metrics.get("users_total") is not None:
        user_parts = [f"всего {metrics['users_total']}"]
        if metrics.get("active_users_24h") is not None:
            user_parts.append(f"активных за 24 часа {metrics['active_users_24h']}")
        if metrics.get("users_active") is not None:
            user_parts.append(f"активных {metrics['users_active']}")
        if metrics.get("users_seen_24h") is not None:
            user_parts.append(f"были за 24 часа {metrics['users_seen_24h']}")
        lines.append("- пользователи: " + ", ".join(user_parts))
    if metrics.get("database"):
        lines.append(f"- база данных: {metrics['database']}")
    if metrics.get("uptime_seconds") is not None:
        lines.append(f"- uptime: {_format_duration(metrics['uptime_seconds'])}")
    if metrics.get("critical_errors_total") is not None:
        lines.append(f"- критические ошибки: {metrics['critical_errors_total']}")
    return lines[:6]
