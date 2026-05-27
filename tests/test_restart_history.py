import sys
import types

sys.modules.setdefault("psutil", types.SimpleNamespace())

import app.diagnostics as diagnostics


class RestartHistorySettings:
    restart_history_limit = 10
    bot_timezone = "Europe/Moscow"

    def __init__(self, paths: list) -> None:
        self.restart_request_path_list = paths


class FakePath:
    def __init__(self, value: str) -> None:
        self.value = value
        self.name = value.rsplit("/", 1)[-1]

    def exists(self) -> bool:
        return True

    def __truediv__(self, item: str) -> "FakePath":
        return FakePath(f"{self.value}/{item}")

    def __str__(self) -> str:
        return self.value


def test_restart_history_shows_processed_request(monkeypatch) -> None:
    def fake_restart_entries(path, bot_name: str, state: str, pattern: str) -> list[dict]:
        if state != "обработано":
            return []
        return [
            {
                "bot": bot_name,
                "state": state,
                "path": types.SimpleNamespace(stem="20260528100010-rememberme-20260528-test"),
                "mtime": 0,
                "payload": {
                    "operation_id": "rememberme-20260528-test",
                    "target": "all",
                    "requested_by": "telegram:123",
                    "reason": "manual restart from status bot",
                    "requested_at": "2026-05-28T10:00:00+00:00",
                },
            }
        ]

    monkeypatch.setattr(diagnostics, "_restart_entries", fake_restart_entries)

    text = diagnostics.format_restart_history(RestartHistorySettings([FakePath("/external/restarts/rememberme")]))

    assert "История перезапусков:" in text
    assert "28.05.2026 13:00:00" in text
    assert "RememberMe: обработано" in text
    assert "цель: все компоненты" in text
    assert "инициатор: Telegram ID 123" in text
    assert "ручной перезапуск из статус-бота" in text
    assert "rememberme-20260528-test" in text


def test_restart_history_reports_empty_directory(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "_restart_entries", lambda *args, **kwargs: [])

    text = diagnostics.format_restart_history(RestartHistorySettings([FakePath("/external/restarts/rememberme")]))

    assert "- записей нет" in text
