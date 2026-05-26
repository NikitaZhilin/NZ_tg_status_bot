from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    status: Status
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    required: bool = True


@dataclass(frozen=True)
class BotStatus:
    key: str
    name: str
    status: Status
    components: list[ComponentStatus]
    metrics: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "status": self.status.value,
            "metrics": self.metrics,
            "checked_at": self.checked_at.isoformat(),
            "components": [
                {
                    "name": item.name,
                    "status": item.status.value,
                    "message": item.message,
                    "details": item.details,
                    "required": item.required,
                }
                for item in self.components
            ],
        }


def combine_status(components: list[ComponentStatus]) -> Status:
    required = [item for item in components if item.required]
    source = required or components
    if any(item.status == Status.DOWN for item in source):
        return Status.DOWN
    if any(item.status in {Status.DEGRADED, Status.UNKNOWN} for item in source):
        return Status.DEGRADED
    return Status.OK


def combine_bot_statuses(items: list[BotStatus]) -> Status:
    if not items:
        return Status.UNKNOWN
    if any(item.status == Status.DOWN for item in items):
        return Status.DOWN
    if any(item.status in {Status.DEGRADED, Status.UNKNOWN} for item in items):
        return Status.DEGRADED
    return Status.OK

