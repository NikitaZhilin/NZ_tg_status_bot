from __future__ import annotations

import json
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

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
        return "Backups: пути не настроены. Укажи BACKUP_PATHS в .env статус-бота."

    lines = ["Backups:"]
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
            return f"Docker containers: ошибка чтения snapshot-файла - {exc}"

    socket_path = settings.docker_socket_path
    if not socket_path.exists():
        return (
            "Docker containers: источник не подключён.\n\n"
            f"Безопасный вариант: писать read-only snapshot в {snapshot_path} "
            "через scripts/write-container-snapshot.sh на VPS. "
            "Подключать /var/run/docker.sock небезопасно, потому что он даёт контейнеру широкие права управления Docker."
        )
    try:
        payload = _docker_get(socket_path, "/containers/json?all=1")
    except Exception as exc:
        return f"Docker containers: ошибка чтения Docker API - {exc}"

    rows = json.loads(payload.decode("utf-8"))
    lines = ["Docker containers:"]
    for row in rows:
        names = ", ".join(name.lstrip("/") for name in row.get("Names", [])) or row.get("Id", "")[:12]
        state = row.get("State", "-")
        status = row.get("Status", "-")
        lines.append(f"- {names}: {state}, {status}")
    return "\n".join(lines)


def _log_path_for_source(settings: Settings, source: str) -> Path | None:
    paths = settings.log_path_list
    if source == "status":
        return next((path for path in paths if str(path).endswith("/app/logs") or str(path) == "/app/logs"), None)
    if source == "rememberme":
        return next((path for path in paths if "rememberme" in str(path).lower()), None)
    if source == "incubator":
        return next((path for path in paths if "incubator" in str(path).lower()), None)
    return None


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
    lines = ["Docker containers:"]
    if generated_at:
        age_minutes = round((datetime.now(timezone.utc) - generated_at).total_seconds() / 60, 1)
        stale = age_minutes > settings.containers_snapshot_max_age_minutes
        suffix = " (устарел)" if stale else ""
        lines.append(f"Snapshot: {generated_at.astimezone().strftime('%d.%m.%Y %H:%M:%S')}, возраст {age_minutes} мин.{suffix}")
    else:
        lines.append("Snapshot: время неизвестно")

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
        lines.append(f"- {name}: {state}, {status}, image {image}")
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
