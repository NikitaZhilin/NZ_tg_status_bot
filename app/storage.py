from __future__ import annotations

import json
import sqlite3
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LastAlert:
    old_status: str
    new_status: str
    sent_at: datetime


class StatusStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS status_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_key TEXT NOT NULL,
                    overall_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_status_snapshots_bot_created
                    ON status_snapshots (bot_key, created_at);

                CREATE TABLE IF NOT EXISTS alert_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_key TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_alert_events_bot_sent
                    ON alert_events (bot_key, sent_at);

                CREATE TABLE IF NOT EXISTS monitor_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    traceback TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS alert_pending (
                    bot_key TEXT PRIMARY KEY,
                    old_status TEXT NOT NULL,
                    target_status TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_mutes (
                    bot_key TEXT PRIMARY KEY,
                    muted_until TEXT NOT NULL,
                    reason TEXT
                );
                """
            )

    def save_snapshot(self, bot_key: str, status: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO status_snapshots (bot_key, overall_status, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    bot_key,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def last_status(self, bot_key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT overall_status
                FROM status_snapshots
                WHERE bot_key = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (bot_key,),
            ).fetchone()
        return str(row["overall_status"]) if row else None

    def should_alert(self, bot_key: str, old_status: str, new_status: str, cooldown_seconds: int) -> bool:
        if old_status == new_status:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sent_at
                FROM alert_events
                WHERE bot_key = ? AND old_status = ? AND new_status = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (bot_key, old_status, new_status),
            ).fetchone()
        if not row:
            return True
        try:
            sent_at = datetime.fromisoformat(str(row["sent_at"]))
        except ValueError:
            return True
        return sent_at <= cutoff

    def record_alert(self, bot_key: str, old_status: str, new_status: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_events (bot_key, old_status, new_status, message, sent_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bot_key, old_status, new_status, message, datetime.now(timezone.utc).isoformat()),
            )

    def record_error(self, source: str, exc: BaseException | str) -> None:
        if isinstance(exc, BaseException):
            message = str(exc)
            tb = "".join(traceback.format_exception(exc))
        else:
            message = exc
            tb = None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO monitor_errors (source, message, traceback, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source[:120], message[:1000], tb, datetime.now(timezone.utc).isoformat()),
            )

    def recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source, message, created_at
                FROM monitor_errors
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def snapshots_since(self, bot_key: str, since: datetime) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT bot_key, overall_status, payload_json, created_at
                FROM status_snapshots
                WHERE bot_key = ? AND created_at >= ?
                ORDER BY id ASC
                """,
                (bot_key, since.isoformat()),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json"))
            except Exception:
                item["payload"] = {}
            result.append(item)
        return result

    def recent_snapshots(self, bot_key: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT bot_key, overall_status, payload_json, created_at
                FROM status_snapshots
                WHERE bot_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (bot_key, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json"))
            except Exception:
                item["payload"] = {}
            result.append(item)
        return list(reversed(result))

    def upsert_pending_alert(self, bot_key: str, old_status: str, target_status: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT target_status, count FROM alert_pending WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()
            if row and row["target_status"] == target_status:
                count = int(row["count"]) + 1
                conn.execute(
                    """
                    UPDATE alert_pending
                    SET count = ?, last_seen_at = ?
                    WHERE bot_key = ?
                    """,
                    (count, now, bot_key),
                )
                return count
            conn.execute(
                """
                INSERT INTO alert_pending (bot_key, old_status, target_status, count, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(bot_key) DO UPDATE SET
                    old_status = excluded.old_status,
                    target_status = excluded.target_status,
                    count = 1,
                    first_seen_at = excluded.first_seen_at,
                    last_seen_at = excluded.last_seen_at
                """,
                (bot_key, old_status, target_status, now, now),
            )
            return 1

    def pending_alert(self, bot_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM alert_pending WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()
        return dict(row) if row else None

    def clear_pending_alert(self, bot_key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM alert_pending WHERE bot_key = ?", (bot_key,))

    def mute_alerts(self, bot_key: str, seconds: int, reason: str = "") -> None:
        muted_until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_mutes (bot_key, muted_until, reason)
                VALUES (?, ?, ?)
                ON CONFLICT(bot_key) DO UPDATE SET
                    muted_until = excluded.muted_until,
                    reason = excluded.reason
                """,
                (bot_key, muted_until, reason),
            )

    def muted_until(self, bot_key: str) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT muted_until FROM alert_mutes WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()
        if not row:
            return None
        try:
            value = datetime.fromisoformat(str(row["muted_until"]))
        except ValueError:
            return None
        if value <= datetime.now(timezone.utc):
            with self._connect() as conn:
                conn.execute("DELETE FROM alert_mutes WHERE bot_key = ?", (bot_key,))
            return None
        return value

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn
