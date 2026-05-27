#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-/opt/nz_tg_status_bot/data/container-status.json}"
TMP="$(mktemp)"

mkdir -p "$(dirname "$OUT")"

docker ps -a --format '{{json .}}' | python3 -c '
import datetime
import json
import sys

rows = [json.loads(line) for line in sys.stdin if line.strip()]
payload = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "containers": rows,
}
print(json.dumps(payload, ensure_ascii=False))
' > "$TMP"

install -m 0644 "$TMP" "$OUT"
rm -f "$TMP"
