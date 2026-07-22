# Runtime config — committed without secrets. Set values in `.env` (see `.env.example`).
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


# Required: Telegram bot token from @BotFather
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Payment is intentionally disabled for now (catalog + cart only).
ENABLE_PAYMENTS = _env_bool("ENABLE_PAYMENTS", False)
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY", "")
OXAPAY_SANDBOX = _env_bool("OXAPAY_SANDBOX", True)
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "USD")
ENABLE_TELEGRAM_PAY = _env_bool("ENABLE_TELEGRAM_PAY", False)

# Your numeric Telegram user ID (e.g. from @userinfobot)
ADMIN_USER_ID = _env_int("ADMIN_USER_ID", 123456789) or 123456789

# Telegram user IDs that receive new orders (comma-separated). Empty = ADMIN_USER_ID.
# Each recipient must have opened a private chat with the bot at least once.
ORDER_ADMIN_IDS = _env_int_list("ORDER_ADMIN_IDS") or [ADMIN_USER_ID]

# Text shown to the customer on the payment step before the order is placed.
# Leave empty to show the default "manual payment" placeholder message.
# This is the seam where a real payment integration plugs in later.
PAYMENT_INSTRUCTIONS = os.getenv("PAYMENT_INSTRUCTIONS", "")

SUPPORT_HANDLE = os.getenv("SUPPORT_HANDLE", "@your_support_handle")
SHOP_IMAGE = os.getenv("SHOP_IMAGE", "tetrahydroguild.png")
CURRENCY = os.getenv("CURRENCY", "$")

# Static product list is unused — catalog comes from the private stock channel.
PRODUCTS = []

# Private channel ID (bot must be admin). Example: -1001234567890
STOCK_CHANNEL_ID = _env_int("STOCK_CHANNEL_ID")

# Newest cached channel posts to refresh on /sync_catalog
CATALOG_SYNC_POST_LIMIT = _env_int("CATALOG_SYNC_POST_LIMIT", 100) or 100
# Newest product-card posts used when resolving item links / slugs
CATALOG_ACTIVE_CARD_LOOKBACK = _env_int("CATALOG_ACTIVE_CARD_LOOKBACK", 20) or 20
# Background auto-sync interval while the bot process is running (0 = disabled)
CATALOG_SYNC_INTERVAL_MINUTES = _env_int("CATALOG_SYNC_INTERVAL_MINUTES", 5) or 0

# Fallback prices only if a channel post has no price lines (prefer channel price posts).
DEFAULT_PRICES = {1: 10.0, 5: 45.0, 10: 80.0}
PRODUCT_PRICES = {}

DATABASE_FILE = os.getenv("DATABASE_FILE", "orders.db")
MAX_ORDERS_PER_USER = _env_int("MAX_ORDERS_PER_USER", 10) or 10
RATE_LIMIT_SECONDS = _env_int("RATE_LIMIT_SECONDS", 60) or 60
