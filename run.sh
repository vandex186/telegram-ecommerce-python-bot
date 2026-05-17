#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example and set TELEGRAM_BOT_TOKEN"
  exit 1
fi

exec .venv/bin/python bot.py
