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
    check_interval_seconds: int = Field(default=60, alias="CHECK_INTERVAL_SECONDS")
    alert_cooldown_seconds: int = Field(default=600, alias="ALERT_COOLDOWN_SECONDS")
    status_db_path: Path = Field(default=Path("data/status_bot.db"), alias="STATUS_DB_PATH")

    rememberme_enabled: bool = Field(default=True, alias="REMEMBERME_ENABLED")
    rememberme_name: str = Field(default="RememberMe", alias="REMEMBERME_NAME")
    rememberme_api_base_url: str = Field(default="http://127.0.0.1:8000", alias="REMEMBERME_API_BASE_URL")
    rememberme_admin_token: str = Field(default="", alias="REMEMBERME_ADMIN_TOKEN")
    rememberme_timeout_seconds: float = Field(default=5.0, alias="REMEMBERME_TIMEOUT_SECONDS")
    rememberme_required: bool = Field(default=True, alias="REMEMBERME_REQUIRED")
    rememberme_docker_containers: str = Field(default="", alias="REMEMBERME_DOCKER_CONTAINERS")

    incubator_enabled: bool = Field(default=True, alias="INCUBATOR_ENABLED")
    incubator_name: str = Field(default="Инкубатор", alias="INCUBATOR_NAME")
    incubator_project_path: Path | None = Field(default=None, alias="INCUBATOR_PROJECT_PATH")
    incubator_database_path: Path | None = Field(default=None, alias="INCUBATOR_DATABASE_PATH")
    incubator_pid_file: Path | None = Field(default=None, alias="INCUBATOR_PID_FILE")
    incubator_required: bool = Field(default=True, alias="INCUBATOR_REQUIRED")
    incubator_docker_container: str = Field(default="", alias="INCUBATOR_DOCKER_CONTAINER")
    incubator_systemd_unit: str = Field(default="", alias="INCUBATOR_SYSTEMD_UNIT")

    server_disk_paths: str = Field(default=".", alias="SERVER_DISK_PATHS")
    docker_check_enabled: bool = Field(default=False, alias="DOCKER_CHECK_ENABLED")
    systemd_check_enabled: bool = Field(default=False, alias="SYSTEMD_CHECK_ENABLED")

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


def setup_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

