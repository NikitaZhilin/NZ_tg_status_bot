import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "process-restart-requests.py"
spec = importlib.util.spec_from_file_location("restart_processor", SCRIPT_PATH)
restart_processor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(restart_processor)


def test_rememberme_request_uses_directory_bot_key_when_payload_has_no_bot_key() -> None:
    request = {"target": "all", "operation_id": "rememberme-20260528-test"}

    containers = restart_processor.containers_for(request, default_bot_key="rememberme")

    assert containers == ["rememberme_bot-bot", "rememberme_bot-worker", "rememberme_bot-api"]


def test_payload_bot_key_still_takes_precedence() -> None:
    request = {"bot_key": "incubator", "target": "web"}

    containers = restart_processor.containers_for(request, default_bot_key="rememberme")

    assert containers == ["incubator-feed-web"]
