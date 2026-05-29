# Configuration file for Telegram Cryptocurrency Shop Bot
# Copy this file to config.py and update with your actual values

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Get from @BotFather
OXAPAY_API_KEY = ""  # Leave empty for testing without crypto payment provider

# Admin Configuration
ADMIN_USER_ID = 123456789  # Replace with your Telegram user ID

# Bot Settings
SUPPORT_HANDLE = "@your_support_handle"
SHOP_IMAGE = "shop_banner.jpg"  # Placeholder image filename
CURRENCY = "$"

# Product Configuration
# Update these with your actual products
PRODUCTS = []

# Private channel ID for stock posts (catalog/channel-cards branch only; bot must be channel admin)
# Leave None on catalog/inline-buttons branch
STOCK_CHANNEL_ID = None  # e.g. -1001234567890

DEFAULT_PRICES = {1: 10.0, 5: 45.0, 10: 80.0}
PRODUCT_PRICES = {
    "unknown_berry": {1: 10.0, 5: 45.0, 10: 80.0},
    "da_funk": {1: 20.0, 5: 90.0, 10: 160.0},
    "miracle_alien_cookies": {1: 10.0, 5: 45.0, 10: 80.0},
}

# Database Configuration
DATABASE_FILE = "orders.db"

# Security Settings
MAX_ORDERS_PER_USER = 10  # Maximum orders per user per day
RATE_LIMIT_SECONDS = 60   # Rate limiting for admin commands 