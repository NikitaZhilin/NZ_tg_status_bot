from __future__ import annotations

import json
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil

from app.config import Settings


def format_top_processes(limit: int = 8) -> str:
    rows = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline"]):
        try:
            info = proc.info
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "-",
                    "cpu": float(info.get("cpu_percent") or 0),
                    "mem": float(info.get("memory_percent") or 0),
                    "cmd": " ".join(info.get("cmdline") or [])[:80],
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda item: (item["mem"], item["cpu"]), reverse=True)
    lines = ["Top процессов по памяти:"]
    if not rows:
        return "Top процессов: нет данных."
    for row in rows[:limit]:
        title = row["cmd"] or row["name"]
        lines.append(
            f"- PID {row['pid']}: RAM {row['mem']:.1f}%, CPU {row['cpu']:.1f}% - {title}"
        )
    lines.append("")
    lines.append("Примечание: если бот запущен в Docker без host PID namespace, список ограничен видимостью контейнера.")
    return "\n".join(lines)


def format_disk_details(settings: Settings) -> str:
    paths = settings.disk_path_list or [Path(".")]
    lines = ["Диски и inode:"]
    for path in paths:
        try:
            usage = psutil.disk_usage(str(path))
            stat = os.statvfs(str(path))
            total_inodes = stat.f_files
            free_inodes = stat.f_ffree
            inode_used = None
            if total_inodes:
                inode_used = round(((total_inodes - free_inodes) / total_inodes) * 100, 1)
            lines.append(
                f"- {path}: занято {usage.percent}%, свободно {usage.free // 1024 // 1024} MB, "
                f"inode занято {inode_used if inode_used is not None else '-'}%"
            )
        except Exception as exc:
            lines.append(f"- {path}: ошибка чтения - {exc}")
    return "\n".join(lines)


def format_backups(settings: Settings) -> str:
    paths = settings.backup_path_list
    if not paths:
        return "Резервные копии: пути не настроены. Укажи BACKUP_PATHS в .env статус-бота."

    lines = ["Резервные копии:"]
    now = datetime.now(timezone.utc)
    for path in paths:
        if not path.exists():
            lines.append(f"- {path}: путь не найден")
            continue
        files = [item for item in path.rglob("*") if item.is_file()]
        if not files:
            lines.append(f"- {path}: файлов нет")
            continue
        newest = max(files, key=lambda item: item.stat().st_mtime)
        newest_dt = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
        age_hours = round((now - newest_dt).total_seconds() / 3600, 1)
        total_mb = sum(item.stat().st_size for item in files) // 1024 // 1024
        lines.append(
            f"- {path}: файлов {len(files)}, размер {total_mb} MB, "
            f"последний {newest.name}, возраст {age_hours} ч."
        )
    return "\n".join(lines)


def format_logs(settings: Settings) -> str:
    paths = settings.log_path_list
    if not paths:
        return "Логи: пути не настроены. Укажи LOG_PATHS в .env статус-бота."
    lines = ["Размер логов:"]
    for path in paths:
        if not path.exists():
            lines.append(f"- {path}: путь не найден")
            continue
        files = [item for item in path.rglob("*") if item.is_file()]
        total_mb = sum(item.stat().st_size for item in files) // 1024 // 1024
        newest = max(files, key=lambda item: item.stat().st_mtime) if files else None
        if newest:
            newest_dt = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc)
            age_hours = round((datetime.now(timezone.utc) - newest_dt).total_seconds() / 3600, 1)
            lines.append(f"- {path}: файлов {len(files)}, размер {total_mb} MB, последний {newest.name}, возраст {age_hours} ч.")
        else:
            lines.append(f"- {path}: файлов нет")
    return "\n".join(lines)


def format_log_tail(settings: Settings, source: str) -> str:
    source_title = {
        "status": "статус-бота",
        "rememberme": "RememberMe",
        "incubator": "Инкубатора",
    }.get(source, source)
    base_path = _log_path_for_source(settings, source)
    if base_path is None:
        return f"Логи {source_title}: путь не настроен."
    if not base_path.exists():
        return f"Логи {source_title}: путь не найден - {base_path}"

    files = [item for item in base_path.rglob("*") if item.is_file()]
    if not files:
        return f"Логи {source_title}: файлов нет."
    newest = max(files, key=lambda item: item.stat().st_mtime)
    text = _read_tail(newest, settings.log_tail_bytes)
    lines = _mask_secrets(text).splitlines()[-settings.log_tail_lines :]
    if not lines:
        return f"Логи {source_title}: файл {newest.name} пуст."
    result = [
        f"Последние строки логов {source_title}:",
        f"Файл: {newest.name}",
        f"Строк: {len(lines)}",
        "",
        *lines,
    ]
    return _telegram_safe_text("\n".join(result))


def format_containers(settings: Settings) -> str:
    snapshot_path = settings.containers_snapshot_path
    if snapshot_path.exists():
        try:
            return _format_container_snapshot(snapshot_path, settings)
        except Exception as exc:
            return f"Контейнеры Docker: ошибка чтения snapshot-файла - {exc}"

    socket_path = settings.docker_socket_path
    if not socket_path.exists():
        return (
            "Контейнеры Docker: источник не подключён.\n\n"
            f"Безопасный вариант: писать read-only snapshot в {snapshot_path} "
            "через scripts/write-container-snapshot.sh на VPS. "
            "Подключать /var/run/docker.sock небезопасно, потому что он даёт контейнеру широкие права управления Docker."
        )
    try:
        payload = _docker_get(socket_path, "/containers/json?all=1")
    except Exception as exc:
        return f"Контейнеры Docker: ошибка чтения Docker API - {exc}"

    rows = json.loads(payload.decode("utf-8"))
    lines = ["Контейнеры Docker:"]
    for row in rows:
        names = ", ".join(name.lstrip("/") for name in row.get("Names", [])) or row.get("Id", "")[:12]
        state = row.get("State", "-")
        status = row.get("Status", "-")
        lines.append(f"- {names}: {state}, {status}")
    return "\n".join(lines)


def format_restart_history(settings: Settings) -> str:
    paths = settings.restart_request_path_list
    if not paths:
        return "История перезапусков: пути не настроены. Укажи RESTART_REQUEST_PATHS в .env статус-бота."

    entries = []
    missing_paths = []
    for path in paths:
        bot_name = _restart_bot_name(path)
        if not path.exists():
            missing_paths.append(str(path))
            continue
        entries.extend(_restart_entries(path, bot_name, "в очереди", "*.json"))
        entries.extend(_restart_entries(path / "processed", bot_name, "обработано", "*.json"))
        entries.extend(_restart_entries(path / "failed", bot_name, "ошибка", "*.json"))

    entries.sort(key=lambda item: item["mtime"], reverse=True)
    lines = ["История перезапусков:"]
    if missing_paths:
        lines.append("Недоступные каталоги:")
        for path in missing_paths[:4]:
            lines.append(f"- {path}")
    if not entries:
        lines.append("- записей нет")
        return "\n".join(lines)

    for entry in entries[: max(settings.restart_history_limit, 1)]:
        payload = entry["payload"]
        created_at = _parse_dt(
            payload.get("requested_at")
            or payload.get("created_at")
            or payload.get("processed_at")
            or payload.get("failed_at")
        )
        if created_at is None:
            created_at = datetime.fromtimestamp(entry["mtime"], timezone.utc)
        display_timezone = _display_timezone(getattr(settings, "bot_timezone", "Europe/Moscow"))
        operation_id = payload.get("operation_id") or _clean_restart_operation_id(entry["path"].stem)
        target = payload.get("target") or "-"
        requested_by = _restart_requested_by_label(str(payload.get("requested_by") or "-"))
        reason = payload.get("reason") or ""
        lines.append(
            f"- {created_at.astimezone(display_timezone).strftime('%d.%m.%Y %H:%M:%S')} "
            f"{entry['bot']}: {entry['state']}, цель: {_restart_target_label(str(target))}, "
            f"заявка: {operation_id}, инициатор: {requested_by}"
        )
        if reason:
            lines.append(f"  причина: {_restart_reason_label(str(reason))}")
    return _telegram_safe_text("\n".join(lines))


def _log_path_for_source(settings: Settings, source: str) -> Path | None:
    paths = settings.log_path_list
    if source == "status":
        return next((path for path in paths if str(path).endswith("/app/logs") or str(path) == "/app/logs"), None)
    if source == "rememberme":
        return next((path for path in paths if "rememberme" in str(path).lower()), None)
    if source == "incubator":
        return next((path for path in paths if "incubator" in str(path).lower()), None)
    return None


def _restart_entries(path: Path, bot_name: str, state: str, pattern: str) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for item in path.glob(pattern):
        if not item.is_file():
            continue
        try:
            payload = json.loads(item.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        entries.append(
            {
                "bot": bot_name,
                "state": state,
                "path": item,
                "mtime": item.stat().st_mtime,
                "payload": payload,
            }
        )
    return entries


def _restart_bot_name(path: Path) -> str:
    value = str(path).lower()
    if "rememberme" in value:
        return "RememberMe"
    if "incubator" in value:
        return "Инкубатор"
    return path.name


def _clean_restart_operation_id(value: str) -> str:
    parts = value.split("-", 2)
    if len(parts) == 3 and parts[0].isdigit():
        return parts[2]
    return value


def _display_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _read_tail(path: Path, max_bytes: int) -> str:
    size = path.stat().st_size
    with path.open("rb") as file:
        if size > max_bytes:
            file.seek(-max_bytes, os.SEEK_END)
        data = file.read()
    return data.decode("utf-8", errors="replace")


def _mask_secrets(text: str) -> str:
    masked = re.sub(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b", "<telegram-token>", text)
    masked = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <secret>", masked)
    masked = re.sub(
        r"(?i)\b(token|secret|password|api[_-]?key|authorization|x-admin-token)(\s*[:=]\s*)([^\s,;]+)",
        lambda match: f"{match.group(1)}{match.group(2)}<secret>",
        masked,
    )
    return masked


def _telegram_safe_text(text: str, limit: int = 3800) -> str:
    if len(text) <= limit:
        return text
    return "...\n" + text[-limit:]


def _format_container_snapshot(path: Path, settings: Settings) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    generated_at_raw = payload.get("generated_at")
    generated_at = _parse_dt(generated_at_raw)
    lines = ["Контейнеры Docker:"]
    if generated_at:
        age_minutes = round((datetime.now(timezone.utc) - generated_at).total_seconds() / 60, 1)
        stale = age_minutes > settings.containers_snapshot_max_age_minutes
        suffix = " (устарел)" if stale else ""
        lines.append(f"Снимок: {generated_at.astimezone().strftime('%d.%m.%Y %H:%M:%S')}, возраст {age_minutes} мин.{suffix}")
    else:
        lines.append("Снимок: время неизвестно")

    rows = payload.get("containers") or []
    if not rows:
        lines.append("- контейнеров нет")
        return "\n".join(lines)

    for row in rows:
        name = row.get("Names") or row.get("Name") or row.get("ID") or row.get("Id") or "-"
        if isinstance(name, list):
            name = ", ".join(str(item).lstrip("/") for item in name)
        state = row.get("State") or row.get("Status") or "-"
        status = row.get("Status") or row.get("RunningFor") or "-"
        image = row.get("Image") or "-"
        lines.append(f"- {name}: {state}, {status}, образ {image}")
    return "\n".join(lines)


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _restart_target_label(target: str) -> str:
    return {
        "all": "все компоненты",
        "api": "API",
        "bot": "Telegram-бот",
        "worker": "фоновый обработчик",
        "web": "web-сервис",
    }.get(target.strip().lower(), target)


def _restart_requested_by_label(value: str) -> str:
    if value.startswith("telegram:"):
        return f"Telegram ID {value.split(':', 1)[1]}"
    if value == "-":
        return "не указан"
    return value


def _restart_reason_label(value: str) -> str:
    normalized = value.strip().lower()
    return {
        "manual restart from status bot": "ручной перезапуск из статус-бота",
    }.get(normalized, value)


def _docker_get(socket_path: Path, path: str) -> bytes:
    request = f"GET {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n".encode("ascii")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(socket_path))
        client.sendall(request)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    response = b"".join(chunks)
    _, _, body = response.partition(b"\r\n\r\n")
    return body
