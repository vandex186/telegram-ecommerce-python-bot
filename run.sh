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
  echo "Create .env from .env.example and set:"
  echo "  TELEGRAM_BOT_TOKEN  (from @BotFather)"
  echo "  STOCK_CHANNEL_ID    (private catalog channel, bot must be admin)"
  echo "  ADMIN_USER_ID       (your Telegram user id)"
  exit 1
fi

# Cursor / shell HTTP proxies break Telegram Bot API (403 CONNECT tunnel failed).
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy \
  SOCKS_PROXY SOCKS5_PROXY socks_proxy socks5_proxy \
  GIT_HTTP_PROXY GIT_HTTPS_PROXY 2>/dev/null || true

export TZ=UTC
exec .venv/bin/python bot.py
