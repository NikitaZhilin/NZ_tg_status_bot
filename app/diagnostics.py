from __future__ import annotations

import json
import os
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


def format_containers(settings: Settings) -> str:
    socket_path = settings.docker_socket_path
    if not socket_path.exists():
        return (
            "Docker containers: источник не подключён.\n\n"
            "Для read-only просмотра нужен доступ к Docker API. "
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
