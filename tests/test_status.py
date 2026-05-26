from app.status import ComponentStatus, Status, combine_bot_statuses, combine_status, BotStatus


def test_combine_status_down_wins_for_required_components():
    result = combine_status(
        [
            ComponentStatus("api", Status.OK, required=True),
            ComponentStatus("db", Status.DOWN, required=True),
            ComponentStatus("docker", Status.UNKNOWN, required=False),
        ]
    )

    assert result == Status.DOWN


def test_optional_unknown_does_not_degrade_required_ok():
    result = combine_status(
        [
            ComponentStatus("api", Status.OK, required=True),
            ComponentStatus("docker", Status.UNKNOWN, required=False),
        ]
    )

    assert result == Status.OK


def test_bot_status_degraded_when_any_bot_unknown():
    result = combine_bot_statuses(
        [
            BotStatus("a", "A", Status.OK, []),
            BotStatus("b", "B", Status.UNKNOWN, []),
        ]
    )

    assert result == Status.DEGRADED

