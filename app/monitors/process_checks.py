from __future__ import annotations

import subprocess
from pathlib import Path

import psutil

from app.status import ComponentStatus, Status


def check_pid_file(path: Path | None, *, required: bool) -> ComponentStatus:
    if not path:
        return ComponentStatus("pid", Status.UNKNOWN, "PID file is not configured", required=False)
    if not path.exists():
        return ComponentStatus("pid", Status.UNKNOWN, f"PID file not found: {path}", required=required)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception as exc:
        return ComponentStatus("pid", Status.DEGRADED, f"Cannot read PID file: {exc}", required=required)

    if psutil.pid_exists(pid):
        return ComponentStatus("pid", Status.OK, f"Process is running, PID {pid}", {"pid": pid}, required=required)
    return ComponentStatus("pid", Status.DOWN, f"Process from PID file is not running, PID {pid}", {"pid": pid}, required=required)


def check_docker_container(name: str, *, enabled: bool) -> ComponentStatus:
    if not enabled or not name:
        return ComponentStatus("docker", Status.UNKNOWN, "Docker check is disabled", required=False)
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return ComponentStatus("docker", Status.UNKNOWN, f"Docker check failed: {exc}", required=False)
    if result.returncode != 0:
        return ComponentStatus("docker", Status.DOWN, result.stderr.strip() or f"Container {name} not found", required=False)
    state = result.stdout.strip()
    status = Status.OK if state == "running" else Status.DOWN
    return ComponentStatus("docker", status, f"{name}: {state}", {"container": name, "state": state}, required=False)


def check_docker_containers(names: list[str], *, enabled: bool) -> ComponentStatus:
    if not enabled or not names:
        return ComponentStatus("docker", Status.UNKNOWN, "Docker check is disabled", required=False)
    states: dict[str, str] = {}
    down: list[str] = []
    for name in names:
        item = check_docker_container(name, enabled=True)
        states[name] = item.details.get("state", item.status.value)
        if item.status == Status.DOWN:
            down.append(name)
    if down:
        return ComponentStatus("docker", Status.DEGRADED, f"Containers not running: {', '.join(down)}", states, required=False)
    return ComponentStatus("docker", Status.OK, "All configured containers are running", states, required=False)


def check_systemd_unit(unit: str, *, enabled: bool) -> ComponentStatus:
    if not enabled or not unit:
        return ComponentStatus("systemd", Status.UNKNOWN, "systemd check is disabled", required=False)
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return ComponentStatus("systemd", Status.UNKNOWN, f"systemd check failed: {exc}", required=False)
    state = result.stdout.strip() or result.stderr.strip()
    status = Status.OK if state == "active" else Status.DOWN
    return ComponentStatus("systemd", status, f"{unit}: {state}", {"unit": unit, "state": state}, required=False)

