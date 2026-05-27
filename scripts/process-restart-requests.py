from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REQUEST_DIRS = [
    Path("/opt/bots/rememberme/restart-requests"),
    Path("/opt/incubator-feed/restart-requests"),
]

ALLOWLIST = {
    "rememberme": {
        "api": ["rememberme_bot-api"],
        "bot": ["rememberme_bot-bot"],
        "worker": ["rememberme_bot-worker"],
        "all": ["rememberme_bot-bot", "rememberme_bot-worker", "rememberme_bot-api"],
    },
    "incubator": {
        "bot": ["incubator-feed-bot"],
        "worker": ["incubator-feed-bot"],
        "web": ["incubator-feed-web"],
        "all": ["incubator-feed-bot", "incubator-feed-web"],
    },
}


def main() -> None:
    for request_dir in REQUEST_DIRS:
        process_dir(request_dir)


def process_dir(request_dir: Path) -> None:
    if not request_dir.exists():
        return
    processed_dir = request_dir / "processed"
    failed_dir = request_dir / "failed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(request_dir.glob("*.json")):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
            containers = containers_for(request)
            for container in containers:
                subprocess.run(["docker", "restart", container], check=True)
            destination = processed_dir / f"{timestamp()}-{path.name}"
            shutil.move(str(path), destination)
        except Exception as exc:
            error_path = failed_dir / f"{timestamp()}-{path.name}.error.txt"
            error_path.write_text(str(exc), encoding="utf-8")
            shutil.move(str(path), failed_dir / f"{timestamp()}-{path.name}")


def containers_for(request: dict) -> list[str]:
    bot_key = str(request.get("bot_key", "")).strip().lower()
    target = str(request.get("target", "")).strip().lower()
    if bot_key not in ALLOWLIST:
        raise ValueError(f"Unknown bot_key: {bot_key}")
    if target not in ALLOWLIST[bot_key]:
        raise ValueError(f"Invalid target for {bot_key}: {target}")
    return ALLOWLIST[bot_key][target]


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


if __name__ == "__main__":
    main()
