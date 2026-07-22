# Reference copy of config.py (same env-loading behavior).
# You do not need to copy this file — commit includes config.py.
# Copy `.env.example` → `.env` and set secrets there.

import os
from pathlib import Path
from typing import Optional

_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _val.strip().strip('"').strip("'"))


def _env_int(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(str(raw).strip())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_int_list(name: str) -> list:
    raw = os.getenv(name, "")
    ids = []
    for part in str(raw).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return ids


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

ENABLE_PAYMENTS = _env_bool("ENABLE_PAYMENTS", False)
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY", "")
OXAPAY_SANDBOX = _env_bool("OXAPAY_SANDBOX", True)
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "USD")
ENABLE_TELEGRAM_PAY = _env_bool("ENABLE_TELEGRAM_PAY", False)

ADMIN_USER_ID = _env_int("ADMIN_USER_ID", 123456789) or 123456789

# Telegram user IDs that receive new orders (comma-separated). Empty = ADMIN_USER_ID.
ORDER_ADMIN_IDS = _env_int_list("ORDER_ADMIN_IDS") or [ADMIN_USER_ID]

# Customer-facing text on the payment step (empty = default placeholder).
PAYMENT_INSTRUCTIONS = os.getenv("PAYMENT_INSTRUCTIONS", "")

SUPPORT_HANDLE = os.getenv("SUPPORT_HANDLE", "@your_support_handle")
SHOP_IMAGE = os.getenv("SHOP_IMAGE", "tetrahydroguild.png")
CURRENCY = os.getenv("CURRENCY", "$")

PRODUCTS = []

# Private channel ID (bot must be admin). Example: -1001234567890
STOCK_CHANNEL_ID = _env_int("STOCK_CHANNEL_ID")

CATALOG_SYNC_POST_LIMIT = _env_int("CATALOG_SYNC_POST_LIMIT", 100) or 100
CATALOG_ACTIVE_CARD_LOOKBACK = _env_int("CATALOG_ACTIVE_CARD_LOOKBACK", 20) or 20
CATALOG_SYNC_INTERVAL_MINUTES = _env_int("CATALOG_SYNC_INTERVAL_MINUTES", 5) or 0

DEFAULT_PRICES = {1: 10.0, 5: 45.0, 10: 80.0}
PRODUCT_PRICES = {}

DATABASE_FILE = os.getenv("DATABASE_FILE", "orders.db")
MAX_ORDERS_PER_USER = _env_int("MAX_ORDERS_PER_USER", 10) or 10
RATE_LIMIT_SECONDS = _env_int("RATE_LIMIT_SECONDS", 60) or 60
