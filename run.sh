#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
# Bot does not use scheduled jobs; APScheduler breaks startup on macOS/Python 3.9
.venv/bin/pip uninstall -y apscheduler 2>/dev/null || true

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example and set TELEGRAM_BOT_TOKEN"
  exit 1
fi

export TZ=UTC
exec .venv/bin/python bot.py
