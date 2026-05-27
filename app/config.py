from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    bot_timezone: str = Field(default="Europe/Moscow", alias="BOT_TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    check_interval_seconds: int = Field(default=7200, alias="CHECK_INTERVAL_SECONDS")
    summary_interval_seconds: int = Field(default=7200, alias="SUMMARY_INTERVAL_SECONDS")
    send_periodic_summary: bool = Field(default=True, alias="SEND_PERIODIC_SUMMARY")
    summary_on_startup: bool = Field(default=True, alias="SUMMARY_ON_STARTUP")
    alert_cooldown_seconds: int = Field(default=600, alias="ALERT_COOLDOWN_SECONDS")
    alert_failure_confirmations: int = Field(default=2, alias="ALERT_FAILURE_CONFIRMATIONS")
    quiet_hours_enabled: bool = Field(default=False, alias="QUIET_HOURS_ENABLED")
    quiet_hours_start: int = Field(default=23, alias="QUIET_HOURS_START")
    quiet_hours_end: int = Field(default=8, alias="QUIET_HOURS_END")
    status_db_path: Path = Field(default=Path("data/status_bot.db"), alias="STATUS_DB_PATH")

    rememberme_enabled: bool = Field(default=True, alias="REMEMBERME_ENABLED")
    rememberme_name: str = Field(default="RememberMe", alias="REMEMBERME_NAME")
    rememberme_api_base_url: str = Field(default="http://127.0.0.1:8000", alias="REMEMBERME_API_BASE_URL")
    rememberme_admin_token: str = Field(default="", alias="REMEMBERME_ADMIN_TOKEN")
    rememberme_timeout_seconds: float = Field(default=5.0, alias="REMEMBERME_TIMEOUT_SECONDS")
    rememberme_required: bool = Field(default=True, alias="REMEMBERME_REQUIRED")
    rememberme_docker_containers: str = Field(default="", alias="REMEMBERME_DOCKER_CONTAINERS")
    rememberme_restart_url: str = Field(default="", alias="REMEMBERME_RESTART_URL")
    rememberme_restart_token: str = Field(default="", alias="REMEMBERME_RESTART_TOKEN")
    rememberme_restart_target: str = Field(default="all", alias="REMEMBERME_RESTART_TARGET")

    incubator_enabled: bool = Field(default=True, alias="INCUBATOR_ENABLED")
    incubator_name: str = Field(default="Инкубатор", alias="INCUBATOR_NAME")
    incubator_api_base_url: str = Field(default="", alias="INCUBATOR_API_BASE_URL")
    incubator_admin_token: str = Field(default="", alias="INCUBATOR_ADMIN_TOKEN")
    incubator_timeout_seconds: float = Field(default=5.0, alias="INCUBATOR_TIMEOUT_SECONDS")
    incubator_project_path: Path | None = Field(default=None, alias="INCUBATOR_PROJECT_PATH")
    incubator_database_path: Path | None = Field(default=None, alias="INCUBATOR_DATABASE_PATH")
    incubator_pid_file: Path | None = Field(default=None, alias="INCUBATOR_PID_FILE")
    incubator_required: bool = Field(default=True, alias="INCUBATOR_REQUIRED")
    incubator_docker_container: str = Field(default="", alias="INCUBATOR_DOCKER_CONTAINER")
    incubator_systemd_unit: str = Field(default="", alias="INCUBATOR_SYSTEMD_UNIT")
    incubator_restart_url: str = Field(default="", alias="INCUBATOR_RESTART_URL")
    incubator_restart_token: str = Field(default="", alias="INCUBATOR_RESTART_TOKEN")
    incubator_restart_target: str = Field(default="all", alias="INCUBATOR_RESTART_TARGET")

    server_disk_paths: str = Field(default=".", alias="SERVER_DISK_PATHS")
    server_cpu_warn_percent: float = Field(default=90.0, alias="SERVER_CPU_WARN_PERCENT")
    server_ram_warn_percent: float = Field(default=85.0, alias="SERVER_RAM_WARN_PERCENT")
    server_disk_warn_percent: float = Field(default=85.0, alias="SERVER_DISK_WARN_PERCENT")
    telegram_api_check_enabled: bool = Field(default=True, alias="TELEGRAM_API_CHECK_ENABLED")
    telegram_api_timeout_seconds: float = Field(default=5.0, alias="TELEGRAM_API_TIMEOUT_SECONDS")
    backup_warn_age_hours: float = Field(default=48.0, alias="BACKUP_WARN_AGE_HOURS")
    log_warn_total_mb: int = Field(default=500, alias="LOG_WARN_TOTAL_MB")
    log_tail_lines: int = Field(default=80, alias="LOG_TAIL_LINES")
    log_tail_bytes: int = Field(default=65536, alias="LOG_TAIL_BYTES")
    backup_paths: str = Field(default="", alias="BACKUP_PATHS")
    log_paths: str = Field(default="", alias="LOG_PATHS")
    containers_snapshot_path: Path = Field(default=Path("/app/data/container-status.json"), alias="CONTAINERS_SNAPSHOT_PATH")
    containers_snapshot_max_age_minutes: float = Field(default=10.0, alias="CONTAINERS_SNAPSHOT_MAX_AGE_MINUTES")
    docker_socket_path: Path = Field(default=Path("/var/run/docker.sock"), alias="DOCKER_SOCKET_PATH")
    docker_check_enabled: bool = Field(default=False, alias="DOCKER_CHECK_ENABLED")
    systemd_check_enabled: bool = Field(default=False, alias="SYSTEMD_CHECK_ENABLED")
    restart_timeout_seconds: float = Field(default=10.0, alias="RESTART_TIMEOUT_SECONDS")

    @property
    def admin_id_set(self) -> frozenset[int]:
        values: set[int] = set()
        for raw in self.admin_ids.replace(";", ",").split(","):
            item = raw.strip()
            if not item:
                continue
            values.add(int(item))
        return frozenset(values)

    @property
    def disk_path_list(self) -> list[Path]:
        return [Path(item.strip()) for item in self.server_disk_paths.split(",") if item.strip()]

    @property
    def rememberme_container_list(self) -> list[str]:
        return [item.strip() for item in self.rememberme_docker_containers.split(",") if item.strip()]

    @property
    def backup_path_list(self) -> list[Path]:
        return [Path(item.strip()) for item in self.backup_paths.split(",") if item.strip()]

    @property
    def log_path_list(self) -> list[Path]:
        return [Path(item.strip()) for item in self.log_paths.split(",") if item.strip()]


def setup_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
