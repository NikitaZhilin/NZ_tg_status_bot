from __future__ import annotations

from datetime import datetime
from typing import Any

from app.status import BotStatus, Status, combine_bot_statuses


STATUS_ICON = {
    Status.OK: "OK",
    Status.DEGRADED: "DEGRADED",
    Status.DOWN: "DOWN",
    Status.UNKNOWN: "UNKNOWN",
}

STATUS_RU = {
    "OK": "работает",
    "DEGRADED": "работает с проблемами",
    "DOWN": "недоступен",
    "UNKNOWN": "неизвестно",
}


def format_status_summary(bots: list[BotStatus], server: BotStatus | None = None) -> str:
    items = list(bots)
    if server:
        items.append(server)
    overall = combine_bot_statuses(items)
    lines = [f"Общий статус: {STATUS_ICON[overall]}", ""]
    for item in bots:
        lines.extend(_format_bot_short(item))
        lines.append("")
    if server:
        lines.extend(_format_server_short(server))
    return "\n".join(lines).strip()


def format_bot_details(item: BotStatus) -> str:
    lines = [
        f"{item.name}: {STATUS_ICON[item.status]}",
        f"Проверено: {_format_dt(item.checked_at)}",
        "",
        "Компоненты:",
    ]
    for component in item.components:
        required = "required" if component.required else "optional"
        message = f" - {component.message}" if component.message else ""
        lines.append(f"- {component.name}: {STATUS_ICON[component.status]} ({required}){message}")
    if item.metrics:
        lines.extend(["", "Метрики:"])
        for key, value in item.metrics.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {len(value)}")
            elif isinstance(value, dict):
                lines.append(f"- {key}: {_compact_dict(value)}")
            else:
                lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def format_server_details(item: BotStatus) -> str:
    metrics = item.metrics
    lines = [
        f"Сервер: {STATUS_ICON[item.status]}",
        f"Host: {metrics.get('hostname', '-')}",
        f"OS: {metrics.get('os', '-')}",
        f"Uptime: {_format_duration(metrics.get('uptime_seconds'))}",
        f"CPU: {metrics.get('cpu_percent', '-')}%",
        f"RAM: {metrics.get('ram_percent', '-')}%",
        f"Сеть входящая: {_format_speed(metrics.get('net_recv_kbps'))}",
        f"Сеть исходящая: {_format_speed(metrics.get('net_sent_kbps'))}",
    ]
    disks = metrics.get("disks") or []
    if disks:
        lines.append("")
        lines.append("Диски:")
        for disk in disks:
            lines.append(
                f"- {disk.get('path')}: {disk.get('percent')}% used, "
                f"{disk.get('free_gb')} GB free"
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
        lines.extend(["", "Последние critical_errors Инкубатора:"])
        if incubator_errors:
            for row in incubator_errors[:5]:
                lines.append(f"- {row.get('created_at')} {row.get('source')}: {row.get('message')}")
        else:
            lines.append("- нет")
    return "\n".join(lines)


def format_alert(name: str, old_status: str, new_status: str, item: BotStatus) -> str:
    failed = [
        component
        for component in item.components
        if component.status in {Status.DOWN, Status.DEGRADED}
    ]
    recovered = new_status == Status.OK.value
    title = (
        f"{name}: восстановлен"
        if recovered
        else f"{name}: изменился статус"
    )
    lines = [
        title,
        "",
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
        lines.append("")
        lines.append("Проблемные компоненты:")
        for component in failed[:5]:
            lines.append(
                f"- {component.name}: "
                f"{STATUS_RU.get(component.status.value, component.status.value)} "
                f"({component.status.value})"
                f"{' - ' + component.message if component.message else ''}"
            )
    else:
        lines.extend(["", "Компоненты: критичных проблем не найдено."])
    return "\n".join(lines)


def _format_bot_short(item: BotStatus) -> list[str]:
    metrics = item.metrics
    lines = [f"{item.name}: {STATUS_ICON[item.status]}"]
    users = metrics.get("users_total")
    if users is not None:
        parts = [f"{users} total"]
        if metrics.get("active_users_24h") is not None:
            parts.append(f"{metrics['active_users_24h']} active 24h")
        if metrics.get("users_active") is not None:
            parts.append(f"{metrics['users_active']} active")
        if metrics.get("users_seen_24h") is not None:
            parts.append(f"{metrics['users_seen_24h']} seen 24h")
        lines.append("Users: " + ", ".join(parts))
    if metrics.get("version"):
        lines.append(f"Version: {metrics['version']}")
    if metrics.get("critical_errors_total") is not None:
        lines.append(f"Critical errors: {metrics['critical_errors_total']}")
    return lines


def _format_server_short(item: BotStatus) -> list[str]:
    metrics = item.metrics
    lines = [
        f"Server: {STATUS_ICON[item.status]}",
        f"CPU: {metrics.get('cpu_percent', '-')}%",
        f"RAM: {metrics.get('ram_percent', '-')}%",
        f"Net in/out: {_format_speed(metrics.get('net_recv_kbps'))} / {_format_speed(metrics.get('net_sent_kbps'))}",
        f"Uptime: {_format_duration(metrics.get('uptime_seconds'))}",
    ]
    disks = metrics.get("disks") or []
    if disks:
        first = disks[0]
        lines.append(f"Disk: {first.get('free_gb')} GB free, {first.get('percent')}% used")
    return lines


def _format_duration(seconds: Any) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _format_speed(kbps: Any) -> str:
    if kbps is None:
        return "будет после следующей проверки"
    value = float(kbps)
    if value >= 1000:
        return f"{round(value / 1000, 2)} Mbit/s"
    return f"{round(value, 2)} Kbit/s"


def _format_dt(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _compact_dict(value: dict[str, Any]) -> str:
    return ", ".join(f"{key}={item}" for key, item in list(value.items())[:6])


def _alert_reason(item: BotStatus, failed: list, recovered: bool) -> str:
    if recovered:
        return "обязательные проверки снова проходят успешно."
    required_failed = [component for component in failed if component.required]
    if required_failed:
        component = required_failed[0]
        return f"обязательный компонент `{component.name}` сообщил `{component.status.value}`."
    if failed:
        component = failed[0]
        return f"необязательный компонент `{component.name}` сообщил `{component.status.value}`."
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
            user_parts.append(f"активных за 24ч {metrics['active_users_24h']}")
        if metrics.get("users_active") is not None:
            user_parts.append(f"активных {metrics['users_active']}")
        if metrics.get("users_seen_24h") is not None:
            user_parts.append(f"видели за 24ч {metrics['users_seen_24h']}")
        lines.append("- пользователи: " + ", ".join(user_parts))
    if metrics.get("database"):
        lines.append(f"- база данных: {metrics['database']}")
    if metrics.get("uptime_seconds") is not None:
        lines.append(f"- uptime: {_format_duration(metrics['uptime_seconds'])}")
    if metrics.get("critical_errors_total") is not None:
        lines.append(f"- критические ошибки: {metrics['critical_errors_total']}")
    return lines[:6]
