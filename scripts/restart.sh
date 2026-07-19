#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
MAIN="$ROOT/main.py"

# Kill only real bot python processes (exact argv), never the shell running this script.
if [[ -x "$PY" ]]; then
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    # Confirm cwd is this project
    cwd=$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)
    if [[ "$cwd" == "$ROOT" ]]; then
      echo "stopping pid=$pid"
      kill "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f "^${PY} ${MAIN}" || true)
fi

# Wait for lock release / processes exit
for _ in $(seq 1 20); do
  if ! pgrep -f "^${PY} ${MAIN}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

rm -f /tmp/discord-video-bot/bot.lock 2>/dev/null || true
mkdir -p logs

# console.log only for startup stderr; bot.log is owned by the app logger
nohup "$PY" "$MAIN" >> "$ROOT/logs/console.log" 2>&1 &
echo "started pid=$!"
sleep 2
tail -n 10 "$ROOT/logs/bot.log" 2>/dev/null || true
