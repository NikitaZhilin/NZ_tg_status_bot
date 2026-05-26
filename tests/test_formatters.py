from app.formatters import format_status_summary
from app.status import BotStatus, Status


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

