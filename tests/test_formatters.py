from app.formatters import format_alert, format_bot_details, format_status_summary
from app.status import BotStatus, ComponentStatus, Status


def test_summary_includes_user_metrics():
    text = format_status_summary(
        [
            BotStatus(
                "rememberme",
                "RememberMe",
                Status.OK,
                [],
                {"users_total": 10, "active_users_24h": 3, "version": "1.0"},
            )
        ]
    )

    assert "RememberMe: работает (OK)" in text
    assert "всего 10" in text
    assert "активных за 24 часа 3" in text
    assert "Версия: 1.0" in text


def test_alert_is_verbose_and_russian():
    text = format_alert(
        "RememberMe",
        "DOWN",
        "OK",
        BotStatus(
            "rememberme",
            "RememberMe",
            Status.OK,
            [ComponentStatus("api health", Status.OK, "ok")],
            {"users_total": 10, "active_users_24h": 3, "version": "1.0"},
        ),
    )

    assert "RememberMe: восстановлен" in text
    assert "Было: недоступен (DOWN)" in text
    assert "Стало: работает (OK)" in text
    assert "Причина:" in text
    assert "пользователи:" in text


def test_rememberme_service_status_metrics_are_formatted():
    text = format_bot_details(
        BotStatus(
            "rememberme",
            "RememberMe",
            Status.OK,
            [ComponentStatus("service status", Status.OK, "ok")],
            {
                "services": {
                    "api": {"status": "ok", "last_seen_at": "2026-05-27T08:00:00Z"},
                    "bot": {"status": "ok", "last_seen_at": "2026-05-27T08:00:00Z"},
                    "worker": {"status": "ok", "last_seen_at": "2026-05-27T08:00:00Z"},
                }
            },
        )
    )

    assert "статус сервисов" in text
    assert "Telegram-бот" in text


def test_summary_explains_server_degraded_reason():
    text = format_status_summary(
        [],
        BotStatus(
            "server",
            "Server",
            Status.DEGRADED,
            [
                ComponentStatus("cpu", Status.OK, "3.0% used"),
                ComponentStatus("backup /external/backups/incubator", Status.DEGRADED, "no backup files"),
            ],
            {
                "cpu_percent": 3.0,
                "ram_percent": 74.8,
                "net_recv_kbps": 122.8,
                "net_sent_kbps": 49.4,
                "uptime_seconds": 144000,
                "disks": [{"path": "/app/data", "free_gb": 5.21, "percent": 61.2}],
            },
        ),
    )

    assert "Сервер: работает с проблемами (DEGRADED)" in text
    assert "Причина: резервные копии /external/backups/incubator — backup-файлов нет" in text
