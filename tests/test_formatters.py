from app.formatters import format_alert, format_status_summary
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

    assert "RememberMe: OK" in text
    assert "10 total" in text
    assert "3 active 24h" in text
    assert "Version: 1.0" in text


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
