import logging
import html
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    MessageOriginChannel,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)
import requests
import config
import catalog_store
import time
import random
import sqlite3
from datetime import datetime, date
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

SHOP_HEADER_CAPTION = (
    "<b>T E T R A H Y D R O G U I L D</b>\n\n"
    "Choice. Payment. Delivery\n\n"
    "Phnom Penh. Cambodia"
)

SHOP_FOOTER_TEXT = (
    "Available for order right now!\n"
    "Browse items above. Tap a price to add to cart.\n\n"
    "Delivery time: 8 am to 10 pm"
)

DISCOUNT_GUIDE_URL = f"https://t.me/tetrahydroguide?text={quote('Have a some disco, Bro?')}"

ADMIN_USER_ID = config.ADMIN_USER_ID  # Get from config file
ADMIN_USER_FILTER = filters.User(user_id=ADMIN_USER_ID)

HTML_TAG_RE = re.compile(r"<[^>]+>")

PUBLIC_BOT_COMMANDS = [
    BotCommand("start", "Main menu"),
]

ADMIN_BOT_COMMANDS = [
    BotCommand("start", "Main menu"),
    BotCommand("orders", "Recent orders"),
    BotCommand("export_orders", "Export orders CSV"),
    BotCommand("addcode", "Add discount code"),
    BotCommand("create_giveaway", "Create giveaway"),
    BotCommand("list_giveaways", "List giveaways"),
    BotCommand("view_entries", "Giveaway entries"),
    BotCommand("bot_status", "Bot status"),
    BotCommand("sync_catalog", "Full catalog sync (prices + cards)"),
    BotCommand("sync_last_30", "Re-parse last 30 cached channel posts"),
    BotCommand("sync_last_60", "Re-parse last 60 cached channel posts"),
]


def apply_fallback_html_formatting(text: str) -> str:
    """Apply lightweight formatting when source text has no HTML markup."""
    lines = text.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if stripped.startswith("-"):
            out.append(html.escape(line))
            continue
        # Emphasize short descriptor lines (title, THC, hybrid, ratios, labels).
        if len(stripped) <= 52 or any(k in stripped.lower() for k in ("thc", "cbd", "sativa", "indica", "hybrid")):
            out.append(f"<b>{html.escape(line)}</b>")
        else:
            out.append(html.escape(line))
    return "\n".join(out)


def format_money(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_price(value: float) -> str:
    return f"{config.CURRENCY}{format_money(value)}"


def get_cart_items(user_data: dict) -> list:
    return user_data.setdefault("cart_items", [])


def get_cart_subtotal(user_data: dict) -> float:
    return round(sum(float(item.get("line_price", 0.0)) for item in get_cart_items(user_data)), 2)


def reset_cart_discount(user_data: dict) -> None:
    """Clear promo discount fields. Keeps cart_referred_by (set via /start or referral code)."""
    user_data["cart_price"] = None
    user_data["cart_discount_code"] = None
    user_data["cart_discount_percent"] = 0


def get_effective_discount(user_data: dict) -> tuple:
    """Return (code, percent). Promo codes win; otherwise referral gives 10%."""
    code = user_data.get("cart_discount_code")
    percent = int(user_data.get("cart_discount_percent", 0) or 0)
    if percent > 0:
        return code, percent
    referred_by = user_data.get("cart_referred_by")
    if referred_by:
        return generate_referral_code(referred_by), 10
    return None, 0


def get_cart_total(user_data: dict) -> float:
    subtotal = get_cart_subtotal(user_data)
    _, percent = get_effective_discount(user_data)
    if percent:
        return round(subtotal * (1 - percent / 100), 2)
    return subtotal


def apply_discount_to_cart(user_data: dict, code: str, percent: int) -> float:
    user_data["cart_discount_code"] = code
    user_data["cart_discount_percent"] = int(percent)
    total = get_cart_total(user_data)
    user_data["cart_price"] = total
    return total


def sync_cart_price(user_data: dict) -> float:
    """Persist effective total onto cart_price for payment handlers."""
    code, percent = get_effective_discount(user_data)
    if percent and not user_data.get("cart_discount_percent"):
        user_data["cart_discount_code"] = code
        user_data["cart_discount_percent"] = percent
    total = get_cart_total(user_data)
    user_data["cart_price"] = total
    return total


def extract_leading_emoji(name: str) -> str:
    """Leading emoji from product title, e.g. '🦜' from '🦜 TROPICAL BLUES'."""
    plain = HTML_TAG_RE.sub("", name or "").strip()
    if not plain:
        return ""
    i = 0
    while i < len(plain):
        ch = plain[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isascii() and ch.isalpha():
            break
        i += 1
    return plain[:i].strip()


def format_cart_item_block(item_num: int, item: dict) -> list[str]:
    name = item.get("product_name", "Item")
    qty = item.get("qty", 0)
    price = format_price(item.get("line_price", 0.0))
    return [f"{item_num}) {name}", f"{qty}g = {price}"]


def format_cart_remove_button_label(item_num: int, item: dict) -> str:
    emoji = extract_leading_emoji(item.get("product_name", ""))
    if emoji:
        return f"{item_num}) {emoji}=❌"
    return f"{item_num})=❌"


def strip_trailing_separator_lines(text: str) -> str:
    lines = text.splitlines()
    while lines:
        plain = HTML_TAG_RE.sub("", lines[-1]).strip()
        if not plain:
            lines.pop()
            continue
        if re.fullmatch(r"[-\s]+", plain) and "-" in plain:
            lines.pop()
            continue
        break
    cleaned = "\n".join(lines).rstrip()
    cleaned = re.sub(r"(?i)\s*Select\s+quantity\s*:?\s*$", "", cleaned).rstrip()
    return cleaned


def build_cart_items_message(user_data: dict) -> str:
    cart_items = get_cart_items(user_data)
    discount_code, discount_percent = get_effective_discount(user_data)
    total = get_cart_total(user_data)
    lines = ["Cart:", ""]
    for idx, item in enumerate(cart_items, start=1):
        lines.extend(format_cart_item_block(idx, item))
        if idx < len(cart_items):
            lines.append("")
    lines.append("")
    lines.append(f"Total: <b>{html.escape(format_price(total))}</b>")
    if discount_percent:
        lines.append(f"Discount: {discount_percent}% ({html.escape(str(discount_code))})")
    lines.append("")
    lines.append("- - - - - - - - - - - - - - - - -")
    lines.append("")
    lines.append("You can delete wrong items:")
    return "\n".join(lines)


def build_cart_delivery_message() -> str:
    return "For creating order - please set your for delivery:"


def build_checkout_review_message(user_data: dict, total: float) -> str:
    cart_items = get_cart_items(user_data)
    discount_code, discount_percent = get_effective_discount(user_data)
    amount = format_price(total)
    lines = [
        "Let's check your order before confirmation",
        "",
        f"{amount} INVOICE",
        "",
    ]
    for idx, item in enumerate(cart_items, start=1):
        lines.extend(format_cart_item_block(idx, item))
        if idx < len(cart_items):
            lines.append("")
    lines.append("")
    if discount_percent:
        lines.append(f"Discount: {discount_percent}% ({html.escape(str(discount_code or ''))})")
    else:
        lines.append(f'Discount: No | <a href="{DISCOUNT_GUIDE_URL}">How to get</a> ->')
    lines.append("")
    lines.append(f"Total: <b>{html.escape(amount)}</b>")
    return "\n".join(lines)


def build_product_card_caption(product: dict) -> str:
    description = product.get("description", "") or ""
    if not HTML_TAG_RE.search(description):
        description = apply_fallback_html_formatting(description)
    description = strip_trailing_separator_lines(description)
    return f"{description}\n\nSelect packaging:"


def compute_1g_price(prices: dict) -> Optional[float]:
    """1g price = 5g channel price / 5."""
    price_5g = prices.get(5)
    if price_5g is None:
        return None
    return round(float(price_5g) / 5, 2)


def build_product_card_markup(product: dict) -> InlineKeyboardMarkup:
    product_id = product.get("id")
    prices = {int(k): float(v) for k, v in (product.get("prices", {}) or {}).items()}
    row = []
    one_g_price = compute_1g_price(prices)
    if one_g_price is not None:
        row.append(
            InlineKeyboardButton(
                f"1g = {format_price(one_g_price)}",
                callback_data=f"add_{product_id}_1",
            )
        )
    for qty in (5, 10):
        if qty in prices:
            row.append(
                InlineKeyboardButton(
                    f"{qty}g = {format_price(prices[qty])}",
                    callback_data=f"add_{product_id}_{qty}",
                )
            )
    if not row:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("No prices in channel post", callback_data="noop_qty_missing")]]
        )
    return InlineKeyboardMarkup([row])


async def send_product_card(chat, product: dict) -> None:
    caption = build_product_card_caption(product)
    reply_markup = build_product_card_markup(product)
    photo_file_id = product.get("photo_file_id")
    image_name = product.get("image")
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), image_name) if image_name else ""
    if photo_file_id:
        await chat.send_photo(photo=photo_file_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    elif image_name and os.path.isfile(image_path):
        with open(image_path, "rb") as photo:
            await chat.send_photo(photo=photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await chat.send_message(caption, reply_markup=reply_markup, parse_mode="HTML")


async def send_shop_product_cards(chat, products: list) -> None:
    for product in products:
        await send_product_card(chat, product)


def build_cart_remove_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    cart_items = get_cart_items(user_data)
    keyboard = []
    if cart_items:
        remove_buttons = [
            InlineKeyboardButton(
                format_cart_remove_button_label(i, item),
                callback_data=f"cart_remove_{i - 1}",
            )
            for i, item in enumerate(cart_items, start=1)
        ]
        max_per_row = 8
        for start in range(0, len(remove_buttons), max_per_row):
            keyboard.append(remove_buttons[start : start + max_per_row])
    return InlineKeyboardMarkup(keyboard)


def build_cart_delivery_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    address = user_data.get("cart_address")
    phone = user_data.get("cart_phone")
    address_btn_text = "Location ✅" if address else "Set Location"
    phone_btn_text = "Phone ✅" if phone else "Set Phone"
    _, discount_percent = get_effective_discount(user_data)
    if discount_percent:
        discount_btn_text = f"Discount ✅ {discount_percent}%"
    else:
        discount_btn_text = "Apply Discount Code"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(address_btn_text, callback_data="enter_address"),
            InlineKeyboardButton(phone_btn_text, callback_data="enter_phone"),
        ],
        [InlineKeyboardButton(discount_btn_text, callback_data="enter_discount")],
        [InlineKeyboardButton("Checkout", callback_data="checkout")],
        [InlineKeyboardButton("Back", callback_data="menu_shop"), InlineKeyboardButton("Main Menu", callback_data="main_menu")],
    ])


def build_empty_cart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Reload Cart", callback_data="open_cart")],
            [InlineKeyboardButton("Shop", callback_data="menu_shop")],
        ]
    )


def build_checkout_location_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Set Location", callback_data="enter_address")],
            [InlineKeyboardButton("Back to Cart", callback_data="back_to_cart")],
        ]
    )


def get_shop_header_image_path() -> Path:
    root = Path(__file__).resolve().parent
    for name in ("tetrahydroguild.png", getattr(config, "SHOP_IMAGE", "shop_banner.jpg")):
        path = root / name
        if path.is_file():
            return path
    return root / "tetrahydroguild.png"


def build_location_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("use my current location", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap to share your location",
    )


def build_phone_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Share my phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Type your phone number",
    )


def is_desktop_or_web_telegram(update: Update) -> bool:
    """Best-effort: Telegram Bot API does not expose client platform directly."""
    user = update.effective_user
    if user and user.api_kwargs:
        client = str(user.api_kwargs.get("client_type") or user.api_kwargs.get("platform") or "").lower()
        if client in ("desktop", "web", "tdesktop", "webk", "weba", "macos", "windows", "linux"):
            return True
    return False


def should_offer_gps_reply_keyboard(user_data: dict, update: Update) -> bool:
    if is_desktop_or_web_telegram(update):
        return False
    if user_data.get("is_text_location_user"):
        return False
    return bool(user_data.get("has_shared_location_before"))


def build_location_prompt_text(include_gps_button: bool) -> str:
    base = "Please set your 📍 location for delivery, before checkout.\n"
    if include_gps_button:
        return base + 'Use 📎 button for pin location or "use my current location" button'
    return base + "Use 📎 button for pin location or paste a Google Maps link."


async def send_shop_header(chat) -> None:
    photo_path = get_shop_header_image_path()
    if photo_path.is_file():
        with photo_path.open("rb") as photo:
            await chat.send_photo(photo=photo, caption=SHOP_HEADER_CAPTION, parse_mode="HTML")
    else:
        await chat.send_message(SHOP_HEADER_CAPTION, parse_mode="HTML")


async def send_phone_prompt(chat, user_data: dict) -> None:
    user_data["awaiting_phone"] = True
    user_data["awaiting_address"] = False
    user_data["awaiting_discount"] = False
    await chat.send_message(
        "Please share your phone number for delivery.\n"
        "Tap the button below or type your number.",
        reply_markup=build_phone_reply_keyboard(),
    )


async def send_location_prompt(chat, user_data: dict, update: Update) -> None:
    user_data["awaiting_address"] = True
    user_data["awaiting_phone"] = False
    user_data["awaiting_discount"] = False
    show_gps = should_offer_gps_reply_keyboard(user_data, update)
    text = build_location_prompt_text(show_gps)
    reply_markup = build_location_reply_keyboard() if show_gps else None
    if not show_gps and not is_desktop_or_web_telegram(update):
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("use my current location", callback_data="show_location_keyboard")]]
        )
    await chat.send_message(text, reply_markup=reply_markup)


def get_shop_products():
    if config.STOCK_CHANNEL_ID:
        return catalog_store.get_shop_products(available_only=True)
    return list(config.PRODUCTS)


def find_product(product_id):
    if config.STOCK_CHANNEL_ID:
        return catalog_store.get_product_by_id(product_id)
    return next((p for p in config.PRODUCTS if p["id"] == product_id), None)


async def process_catalog_message(message) -> int:
    text_plain = message.caption or message.text or ""
    text_formatted = None
    if message.caption:
        text_formatted = getattr(message, "caption_html", None) or message.caption
    elif message.text:
        text_formatted = getattr(message, "text_html", None) or message.text
    text_for_store = text_formatted or text_plain
    photo_file_id = message.photo[-1].file_id if message.photo else None
    posted_at = message.date.isoformat() if getattr(message, "date", None) else None
    chat_id = message.chat_id if getattr(message, "chat_id", None) else None
    message_id = message.message_id if getattr(message, "message_id", None) else None
    catalog_store.save_source_post(
        chat_id=chat_id,
        message_id=message_id,
        text=text_for_store,
        photo_file_id=photo_file_id,
        posted_at=posted_at,
    )
    parsed_catalog = catalog_store.sync_from_text(text_for_store, photo_file_id, message.message_id)
    parsed_prices = catalog_store.sync_price_post(text_plain, message.message_id)
    return parsed_catalog + parsed_prices

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def init_db():
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        user_id INTEGER,
        product_id INTEGER,
        product_name TEXT,
        quantity INTEGER,
        price REAL,
        invoice_id TEXT,
        discount_code TEXT,
        discount_percent INTEGER,
        referred_by TEXT,
        address TEXT,
        phone TEXT
    )''')
    try:
        c.execute("ALTER TABLE orders ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
        code TEXT PRIMARY KEY,
        percent INTEGER,
        expires TEXT
    )''')
    conn.commit()
    conn.close()

def save_order(
    user_id,
    product,
    quantity,
    price,
    invoice_id,
    discount_code=None,
    discount_percent=0,
    referred_by=None,
    address=None,
    phone=None,
):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (timestamp, user_id, product_id, product_name, quantity, price, invoice_id, discount_code, discount_percent, referred_by, address, phone) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), user_id, product["id"], product["name"], quantity, price, invoice_id, discount_code, discount_percent, referred_by, address, phone),
    )
    conn.commit()
    conn.close()

def get_recent_orders(limit=10):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT timestamp, user_id, product_id, product_name, quantity, price, invoice_id, discount_code, discount_percent, referred_by, address, phone FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_discount_code(code, percent, expires):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("REPLACE INTO discount_codes (code, percent, expires) VALUES (?, ?, ?)", (code.upper(), percent, expires))
    conn.commit()
    conn.close()

def get_discount_code(code):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT code, percent, expires FROM discount_codes WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    conn.close()
    if row:
        expires = row[2]
        if expires and date.fromisoformat(expires) < date.today():
            return None
        return {"code": row[0], "percent": row[1], "expires": row[2]}
    return None

def generate_referral_code(user_id):
    return f"REF{user_id}"

def get_referrer_from_code(code):
    if code.startswith("REF") and code[3:].isdigit():
        return int(code[3:])
    return None

def init_giveaway_db():
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        prize TEXT,
        start_date TEXT,
        end_date TEXT,
        max_entries INTEGER,
        is_active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS giveaway_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        giveaway_id INTEGER,
        user_id INTEGER,
        username TEXT,
        entry_date TEXT,
        FOREIGN KEY (giveaway_id) REFERENCES giveaways (id)
    )''')
    conn.commit()
    conn.close()

def create_giveaway(title, description, end_date, max_entries=100):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    start_date = date.today().isoformat()
    c.execute("INSERT INTO giveaways (title, description, prize, start_date, end_date, max_entries) VALUES (?, ?, ?, ?, ?, ?)",
              (title, description, f"Prize from {title}", start_date, end_date, max_entries))
    giveaway_id = c.lastrowid
    conn.commit()
    conn.close()
    return giveaway_id

def get_active_giveaways():
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT id, title, description, prize, start_date, end_date, max_entries FROM giveaways WHERE is_active = 1 AND end_date > ? ORDER BY end_date ASC", (date.today().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

def enter_giveaway(giveaway_id, user_id, username):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    # Check if user already entered
    c.execute("SELECT id FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?", (giveaway_id, user_id))
    if c.fetchone():
        conn.close()
        return False, "You have already entered this giveaway!"
    
    # Check if giveaway is still active
    c.execute("SELECT end_date, max_entries FROM giveaways WHERE id = ? AND is_active = 1", (giveaway_id,))
    giveaway = c.fetchone()
    if not giveaway:
        conn.close()
        return False, "Giveaway not found or inactive!"
    
    end_date = date.fromisoformat(giveaway[0])
    if end_date < date.today():
        conn.close()
        return False, "This giveaway has ended!"
    
    # Check if max entries reached
    c.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,))
    current_entries = c.fetchone()[0]
    if current_entries >= giveaway[1]:
        conn.close()
        return False, "This giveaway has reached maximum entries!"
    
    # Add entry
    c.execute("INSERT INTO giveaway_entries (giveaway_id, user_id, username, entry_date) VALUES (?, ?, ?, ?)",
              (giveaway_id, user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True, "Successfully entered the giveaway! Good luck!"

def get_giveaway_entries(giveaway_id):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT user_id, username, entry_date FROM giveaway_entries WHERE giveaway_id = ? ORDER BY entry_date ASC", (giveaway_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM orders")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_broadcast_message(message_text, sent_by):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS broadcast_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_text TEXT,
        sent_by INTEGER,
        sent_date TEXT,
        recipients_count INTEGER
    )''')
    c.execute("INSERT INTO broadcast_messages (message_text, sent_by, sent_date, recipients_count) VALUES (?, ?, ?, ?)",
              (message_text, sent_by, datetime.now().isoformat(), 0))
    conn.commit()
    conn.close()

def create_crypto_payment_invoice(user_id: int, cart_items: list, price: float) -> Optional[dict]:
    api_key = get_oxapay_api_key()
    if not api_key:
        return None

    url = "https://api.oxapay.com/v1/payment/invoice"
    headers = {
        "merchant_api_key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "amount": float(price),
        "currency": get_payment_currency(),
        "lifetime": 60,
        "order_id": build_checkout_payload(user_id),
        "description": build_checkout_description(cart_items),
        "sandbox": bool(getattr(config, "OXAPAY_SANDBOX", False)),
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        body = response.json()
    except Exception as exc:
        logging.error("OxaPay invoice error: %s", exc)
        return None

    if response.status_code != 200 or body.get("status") != 200:
        logging.error("OxaPay invoice failed: %s", body)
        return None

    data = body.get("data") or {}
    track_id = data.get("track_id")
    payment_url = data.get("payment_url")
    if not track_id or not payment_url:
        return None
    return {"track_id": str(track_id), "payment_url": payment_url}


def check_crypto_payment_invoice(track_id: str) -> Optional[dict]:
    api_key = get_oxapay_api_key()
    if not api_key:
        return None

    url = f"https://api.oxapay.com/v1/payment/{track_id}"
    headers = {
        "merchant_api_key": api_key,
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        body = response.json()
    except Exception as exc:
        logging.error("OxaPay status error: %s", exc)
        return None

    if response.status_code != 200 or body.get("status") != 200:
        return None
    return body.get("data")


def is_crypto_payment_paid(status_data: Optional[dict]) -> bool:
    if not status_data:
        return False
    status = str(status_data.get("status", "")).lower()
    return status in {"paid", "completed", "confirmed"}


def get_oxapay_api_key() -> str:
    return (getattr(config, "OXAPAY_API_KEY", None) or "").strip()


def is_telegram_pay_enabled() -> bool:
    if not getattr(config, "ENABLE_TELEGRAM_PAY", False):
        return False
    return bool(get_payment_provider_token())


def get_payment_provider_token() -> str:
    return (getattr(config, "PAYMENT_PROVIDER_TOKEN", None) or "").strip()


def get_payment_currency() -> str:
    return (getattr(config, "PAYMENT_CURRENCY", None) or "USD").strip().upper()


def price_to_minor_units(amount: float, currency: str) -> int:
    zero_decimal = {
        "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG",
        "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
    }
    if currency in zero_decimal:
        return int(round(amount))
    return int(round(amount * 100))


def build_checkout_payload(user_id: int) -> str:
    return f"cart_{user_id}_{int(time.time())}"


def build_checkout_description(cart_items: list) -> str:
    lines = []
    for idx, item in enumerate(cart_items[:5], start=1):
        lines.append(f"{idx}) {item.get('product_name', 'Item')} — {item.get('qty', 0)}g")
    if len(cart_items) > 5:
        lines.append(f"+ {len(cart_items) - 5} more item(s)")
    return "\n".join(lines) or "Cart order"


def store_pending_telegram_payment(user_data: dict, payload: str, cart_items: list, price: float) -> None:
    user_data.setdefault("telegram_payments", {})[payload] = {
        "items": list(cart_items),
        "price": float(price),
        "discount_code": user_data.get("cart_discount_code"),
        "discount_percent": user_data.get("cart_discount_percent", 0),
        "referred_by": user_data.get("cart_referred_by"),
        "address": user_data.get("cart_address"),
        "phone": user_data.get("cart_phone"),
    }


def get_pending_telegram_payment(user_data: dict, payload: str) -> Optional[dict]:
    return user_data.get("telegram_payments", {}).get(payload)


async def send_telegram_pay_invoice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    user_data: dict,
    cart_items: list,
    price: float,
) -> bool:
    provider_token = get_payment_provider_token()
    if not provider_token:
        return False

    currency = get_payment_currency()
    payload = build_checkout_payload(user_id)
    store_pending_telegram_payment(user_data, payload, cart_items, price)

    await context.bot.send_invoice(
        chat_id=chat_id,
        title="TetrahydroGuild order",
        description=build_checkout_description(cart_items),
        payload=payload,
        provider_token=provider_token,
        currency=currency,
        prices=[LabeledPrice("Total", price_to_minor_units(price, currency))],
    )
    return True


def build_checkout_payment_keyboard(user_data: dict) -> Optional[InlineKeyboardMarkup]:
    has_telegram = is_telegram_pay_enabled()
    has_crypto = bool(get_oxapay_api_key())
    if has_telegram and has_crypto:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Pay with Crypto / Wallet", callback_data="pay_crypto")],
            [InlineKeyboardButton("Pay by Card", callback_data="pay_telegram")],
            [InlineKeyboardButton("Main Menu", callback_data="main_menu")],
        ])
    return None


def store_pending_crypto_payment(user_data: dict, track_id: str, cart_items: list, price: float) -> None:
    user_data["pending_invoice_id"] = track_id
    user_data["pending_items"] = list(cart_items)
    user_data["pending_price"] = float(price)


async def start_telegram_payment(
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    user_id: int,
    user_data: dict,
    cart_items: list,
    price: float,
) -> None:
    if not is_telegram_pay_enabled():
        await chat.send_message(
            "Card payments are disabled.\n"
            "Use Pay with Crypto / Wallet, or ask admin to set OXAPAY_API_KEY."
        )
        return
    if not await send_telegram_pay_invoice(context, chat.id, user_id, user_data, cart_items, price):
        await chat.send_message(
            "Telegram Pay is not configured.\n"
            "Admin: set PAYMENT_PROVIDER_TOKEN in .env (from @BotFather → Bot → Payments)."
        )
        return
    await chat.send_message(
        "Tap Pay on the invoice above.\n"
        "Note: Smart Glocal uses a bank card — this is not @wallet crypto balance.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]),
    )


async def start_crypto_payment(
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    user_id: int,
    user_data: dict,
    cart_items: list,
    price: float,
) -> None:
    invoice = create_crypto_payment_invoice(user_id, cart_items, price)
    if not invoice:
        await chat.send_message(
            "Crypto payments are not configured.\n"
            "Admin: set OXAPAY_API_KEY in .env (OxaPay → Merchant → API Key).\n"
            "Get a free merchant account at https://oxapay.com"
        )
        return

    track_id = invoice["track_id"]
    pay_url = invoice["payment_url"]
    store_pending_crypto_payment(user_data, track_id, cart_items, price)

    sandbox_note = "\n(Test mode — OxaPay sandbox)" if getattr(config, "OXAPAY_SANDBOX", False) else ""
    await chat.send_message(
        f"Pay {format_price(price)} with crypto.{sandbox_note}\n\n"
        "1. Tap Open payment page\n"
        "2. Choose TON / USDT / BTC — pay from @wallet or any crypto wallet\n"
        "3. Tap I've paid when the transfer is sent",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Open payment page", url=pay_url)],
            [InlineKeyboardButton("Open @wallet", url="https://t.me/wallet")],
            [InlineKeyboardButton("I've paid", callback_data=f"check_crypto_{track_id}")],
            [InlineKeyboardButton("Main Menu", callback_data="main_menu")],
        ]),
    )


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    pending = get_pending_telegram_payment(context.user_data, query.invoice_payload)
    if not pending:
        await query.answer(ok=False, error_message="Order expired. Open Cart and tap Checkout again.")
        return

    currency = get_payment_currency()
    expected = price_to_minor_units(float(pending["price"]), currency)
    if query.total_amount != expected or query.currency != currency:
        await query.answer(ok=False, error_message="Cart total changed. Please checkout again.")
        return
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    pending = get_pending_telegram_payment(context.user_data, payment.invoice_payload)
    if not pending:
        await update.message.reply_text("Payment received, but the order session expired. Contact support.")
        return

    invoice_id = payment.telegram_payment_charge_id
    summary = fulfill_paid_cart(
        update.effective_user.id,
        pending["items"],
        invoice_id,
        pending.get("discount_code"),
        pending.get("discount_percent", 0),
        pending.get("referred_by"),
        pending.get("address"),
        pending.get("phone"),
    )
    summary.append(f"\nTotal paid: {format_price(pending['price'])}")
    clear_cart_after_payment(context.user_data)
    await update.message.reply_text("\n".join(summary))


def clear_cart_after_payment(user_data: dict) -> None:
    for key in [
        "cart_items",
        "cart_product",
        "cart_quantity",
        "cart_price",
        "cart_discount_code",
        "cart_discount_percent",
        "cart_referred_by",
        "cart_address",
        "cart_phone",
        "awaiting_phone",
        "awaiting_address",
        "awaiting_discount",
        "cart_items_message_id",
        "cart_delivery_message_id",
        "cart_chat_id",
        "pending_invoice_id",
        "pending_items",
        "pending_price",
        "telegram_payments",
    ]:
        user_data.pop(key, None)


def fulfill_paid_cart(
    user_id: int,
    items: list,
    invoice_id: str,
    discount_code,
    discount_percent: int,
    referred_by,
    address: str,
    phone: str = None,
) -> list[str]:
    for item in items:
        line_price = float(item.get("line_price", 0))
        if discount_percent:
            line_price = round(line_price * (1 - discount_percent / 100), 2)
        product = {"id": item.get("product_id", 0), "name": item.get("product_name", "Item")}
        qty = int(item.get("qty", 1))
        save_order(user_id, product, qty, line_price, invoice_id, discount_code, discount_percent, referred_by, address, phone)

    summary = ["Payment received! Items:", ""]
    for idx, item in enumerate(items, start=1):
        summary.extend(format_cart_item_block(idx, item))
        if idx < len(items):
            summary.append("")
    if address:
        summary.append(f"\nShipping location:\n{address}")
    if phone:
        summary.append(f"\nPhone for delivery:\n{phone}")
    return summary


# --- Bot Handlers ---

def build_main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Shop", callback_data="menu_shop")],
        [InlineKeyboardButton("Cart", callback_data="open_cart")],
        [InlineKeyboardButton("Refer a Friend", callback_data="menu_referral")],
        [InlineKeyboardButton("Support", callback_data="menu_support")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def apply_start_referral(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """If /start was opened with a REF code, store referrer for this session."""
    if not context.args:
        return
    ref_code = str(context.args[0]).strip().upper()
    referrer = get_referrer_from_code(ref_code)
    if referrer is None or referrer == user_id:
        return
    context.user_data["cart_referred_by"] = referrer


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    apply_start_referral(context, user_id)
    is_admin = user_id == ADMIN_USER_ID
    reply_markup = build_main_menu_keyboard(is_admin)
    text = "Welcome to the shop!\n\nPlease choose an option:"
    if context.user_data.get("cart_referred_by") and update.message and context.args:
        text = (
            "Welcome to the shop!\n\n"
            "Referral applied — you get 10% off at checkout.\n\n"
            "Please choose an option:"
        )

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
        return

    query = update.callback_query
    if not query:
        return
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.chat.send_message(text, reply_markup=reply_markup)

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data == "menu_shop":
        products = get_shop_products()
        chat = query.message.chat

        # --- Old shop: one button per product (opens single card) ---
        # keyboard = [
        #     [InlineKeyboardButton(p["name"], callback_data=f"select_{p['id']}")]
        #     for p in products
        # ]
        # keyboard.append([InlineKeyboardButton("Main Menu", callback_data="main_menu")])
        # reply_markup = InlineKeyboardMarkup(keyboard)
        # try:
        #     await query.edit_message_text("Available now:", reply_markup=reply_markup)
        # except Exception:
        #     try:
        #         await query.message.delete()
        #     except Exception:
        #         pass
        #     await chat.send_message("Available now:", reply_markup=reply_markup)
        # return
        # --- End old shop ---

        try:
            await query.message.delete()
        except Exception:
            pass

        footer = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Cart", callback_data="open_cart")],
                [InlineKeyboardButton("Main Menu", callback_data="main_menu")],
            ]
        )
        if not products:
            extra = ""
            if config.STOCK_CHANNEL_ID:
                total, available = catalog_store.catalog_stats()
                if total == 0:
                    extra = "\n\n(Catalog empty — add the bot to the stock channel as admin, then post or edit a catalog message.)"
                else:
                    extra = f"\n\n({available} of {total} in stock — nothing available right now.)"
            else:
                extra = "\n\n(No products available.)"
            await send_shop_header(chat)
            if extra:
                await chat.send_message(extra.strip(), reply_markup=footer)
            else:
                await chat.send_message(SHOP_FOOTER_TEXT, reply_markup=footer)
            return

        await send_shop_header(chat)
        await send_shop_product_cards(chat, products)
        await chat.send_message(SHOP_FOOTER_TEXT, reply_markup=footer)
    elif data == "menu_giveaways":
        giveaways = get_active_giveaways()
        if not giveaways:
            await query.edit_message_text("No active giveaways at the moment. Check back later!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]))
            return
        
        keyboard = []
        for giveaway in giveaways:
            keyboard.append([InlineKeyboardButton(f"{giveaway[1]}", callback_data=f"giveaway_{giveaway[0]}")])
        keyboard.append([InlineKeyboardButton("Main Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Active Giveaways:", reply_markup=reply_markup)
    elif data == "menu_support":
        await query.edit_message_text(f"For support, contact: {config.SUPPORT_HANDLE}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]))
    elif data == "menu_referral":
        code = generate_referral_code(user_id)
        bot_username = context.bot.username
        share_link = f"https://t.me/{bot_username}?start={code}" if bot_username else code
        message = (
            "<b>Refer a Friend</b>\n\n"
            f"Your referral code: <code>{html.escape(code)}</code>\n\n"
            "Share this link with friends:\n"
            f"{html.escape(share_link)}\n\n"
            "When they open the bot with your link (or apply your code in Cart → Apply Discount Code), "
            "they get <b>10% off</b> and you are credited as their referrer."
        )
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    elif data == "main_menu":
        await start(update, context)
    else:
        await button(update, context)

async def select_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("select_"):
        product_id = int(data.split("_")[1])
        product = find_product(product_id)
        if not product:
            await query.edit_message_text("Product not found.")
            return
        if not product.get("in_stock", True):
            await query.edit_message_text(
                "This item is currently unavailable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Back to Shop", callback_data="menu_shop")]]
                ),
            )
            return
        context.user_data["cart_product"] = product
        product_prices = product.get("prices", {}) or {}
        qty_map = {int(q): float(p) for q, p in product_prices.items()} if product_prices else {}
        qty_buttons = sorted(qty_map.items(), key=lambda item: item[0])[:2]
        if qty_buttons:
            qty_row = [
                InlineKeyboardButton(
                    f"{qty}gr ={format_money(price)}{config.CURRENCY}",
                    callback_data=f"qty_{qty}",
                )
                for qty, price in qty_buttons
            ]
        else:
            qty_row = [InlineKeyboardButton("No prices in channel post", callback_data="noop_qty_missing")]
        keyboard = [
            qty_row,
            [InlineKeyboardButton("Cart", callback_data="open_cart")],
            [InlineKeyboardButton("Back", callback_data="menu_shop"), InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        description = product.get("description", "") or ""
        # Fallback: apply simple rich formatting if source does not contain HTML tags.
        if not HTML_TAG_RE.search(description):
            description = apply_fallback_html_formatting(description)
        caption = f"{description}\n\nSelect quantity:"
        photo_file_id = product.get("photo_file_id")
        image_name = product.get("image")
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), image_name) if image_name else ""
        try:
            await query.message.delete()
        except Exception:
            pass
        chat = query.message.chat
        if photo_file_id:
            await chat.send_photo(photo=photo_file_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        elif image_name and os.path.isfile(image_path):
            with open(image_path, "rb") as photo:
                await chat.send_photo(photo=photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await chat.send_message(caption, reply_markup=reply_markup, parse_mode="HTML")

async def add_to_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    if len(parts) != 3 or parts[0] != "add":
        await query.answer("Invalid action.", show_alert=True)
        return
    try:
        product_id = int(parts[1])
        qty = int(parts[2])
    except ValueError:
        await query.answer("Invalid item.", show_alert=True)
        return
    product = find_product(product_id)
    if not product:
        await query.answer("Product not found.", show_alert=True)
        return
    if not product.get("in_stock", True):
        await query.answer("This item is unavailable.", show_alert=True)
        return
    prices = {int(k): float(v) for k, v in (product.get("prices", {}) or {}).items()}
    if qty == 1:
        price = compute_1g_price(prices)
    else:
        price = prices.get(qty)
    if price is None:
        await query.answer("Price not found in channel price post.", show_alert=True)
        return
    line_price = round(float(price), 2)
    cart_items = get_cart_items(context.user_data)
    cart_items.append(
        {
            "product_id": product.get("id"),
            "product_name": product.get("name", "Item"),
            "qty": int(qty),
            "unit_price": line_price,
            "line_price": line_price,
            "description": product.get("description", ""),
        }
    )
    reset_cart_discount(context.user_data)
    await query.answer(f"Added: {product.get('name', 'Item')}, {qty}g, {format_price(line_price)}")


async def quantity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    if data.startswith("qty_"):
        qty = int(data.split("_")[1])
        product = context.user_data.get("cart_product")
        if not product:
            await query.edit_message_text("No product selected.")
            return
        prices = product.get("prices", {}) or {}
        price = prices.get(qty)
        if price is None:
            await query.answer("Price not found in channel price post.", show_alert=True)
            return
        cart_items = get_cart_items(context.user_data)
        line_price = round(float(price), 2)
        cart_items.append(
            {
                "product_id": product.get("id"),
                "product_name": product.get("name", "Item"),
                "qty": int(qty),
                "unit_price": line_price,
                "line_price": line_price,
                "description": product.get("description", ""),
            }
        )
        reset_cart_discount(context.user_data)
        await query.answer(f"Added: {product.get('name', 'Item')}, {qty}g, {format_price(line_price)}")


async def open_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = context.user_data
    cart_items = get_cart_items(user_data)
    if not cart_items:
        await query.edit_message_text(
            "Your cart is empty.",
            reply_markup=build_empty_cart_keyboard(),
        )
        return
    await show_cart(update, context)

def _resolve_chat(update_or_query):
    if hasattr(update_or_query, "effective_chat") and update_or_query.effective_chat:
        return update_or_query.effective_chat
    if hasattr(update_or_query, "message") and update_or_query.message:
        return update_or_query.message.chat
    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        return update_or_query.callback_query.message.chat
    raise ValueError("Cannot resolve chat from update")


async def _delete_cart_items_message(context: ContextTypes.DEFAULT_TYPE, user_data: dict) -> None:
    chat_id = user_data.get("cart_chat_id")
    items_mid = user_data.pop("cart_items_message_id", None)
    if chat_id and items_mid:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=items_mid)
        except Exception:
            pass


async def _delete_cart_delivery_message(context: ContextTypes.DEFAULT_TYPE, user_data: dict) -> None:
    chat_id = user_data.get("cart_chat_id")
    delivery_mid = user_data.pop("cart_delivery_message_id", None)
    if chat_id and delivery_mid:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=delivery_mid)
        except Exception:
            pass


async def _show_empty_cart(update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    msg = "Your cart is empty."
    reply_markup = build_empty_cart_keyboard()
    await _delete_cart_delivery_message(context, user_data)
    items_mid = user_data.pop("cart_items_message_id", None)
    chat_id = user_data.get("cart_chat_id")

    if items_mid and chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=items_mid,
                text=msg,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            user_data.pop("cart_items_message_id", None)

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(msg, reply_markup=reply_markup)
    elif hasattr(update_or_query, "message") and update_or_query.message:
        sent = await update_or_query.message.reply_text(msg, reply_markup=reply_markup)
        user_data["cart_items_message_id"] = sent.message_id
        user_data["cart_chat_id"] = sent.chat_id
    elif hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        query = update_or_query.callback_query
        try:
            await query.edit_message_text(msg, reply_markup=reply_markup)
            user_data["cart_items_message_id"] = query.message.message_id
            user_data["cart_chat_id"] = query.message.chat_id
        except Exception:
            sent = await query.message.chat.send_message(msg, reply_markup=reply_markup)
            user_data["cart_items_message_id"] = sent.message_id
            user_data["cart_chat_id"] = sent.chat_id


async def show_cart(
    update_or_query,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    refresh_at_bottom: bool = False,
):
    user_data = context.user_data
    cart_items = get_cart_items(user_data)
    if not cart_items:
        await _show_empty_cart(update_or_query, context)
        return

    chat = _resolve_chat(update_or_query)
    user_data["cart_chat_id"] = chat.id
    items_msg = build_cart_items_message(user_data)
    delivery_msg = build_cart_delivery_message()
    remove_kb = build_cart_remove_keyboard(user_data)
    delivery_kb = build_cart_delivery_keyboard(user_data)

    if refresh_at_bottom:
        await _delete_cart_items_message(context, user_data)
        await _delete_cart_delivery_message(context, user_data)
        sent_items = await chat.send_message(items_msg, reply_markup=remove_kb, parse_mode="HTML")
        sent_delivery = await chat.send_message(delivery_msg, reply_markup=delivery_kb, parse_mode="HTML")
        user_data["cart_items_message_id"] = sent_items.message_id
        user_data["cart_delivery_message_id"] = sent_delivery.message_id
        return

    items_mid = user_data.get("cart_items_message_id")
    delivery_mid = user_data.get("cart_delivery_message_id")
    if delivery_mid and items_mid and delivery_mid == items_mid:
        user_data.pop("cart_delivery_message_id", None)
        delivery_mid = None

    items_ok = False
    if items_mid:
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=items_mid,
                text=items_msg,
                reply_markup=remove_kb,
                parse_mode="HTML",
            )
            items_ok = True
        except Exception:
            user_data.pop("cart_items_message_id", None)
            items_mid = None

    if not items_ok:
        query_msg = None
        if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
            query_msg = update_or_query.callback_query.message
        if query_msg:
            try:
                await query_msg.edit_text(items_msg, reply_markup=remove_kb, parse_mode="HTML")
                user_data["cart_items_message_id"] = query_msg.message_id
                items_mid = query_msg.message_id
                items_ok = True
            except Exception:
                try:
                    await query_msg.delete()
                except Exception:
                    pass

    if not items_ok:
        sent_items = await chat.send_message(items_msg, reply_markup=remove_kb, parse_mode="HTML")
        user_data["cart_items_message_id"] = sent_items.message_id
        items_mid = sent_items.message_id

    delivery_ok = False
    if delivery_mid and delivery_mid != items_mid:
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=delivery_mid,
                text=delivery_msg,
                reply_markup=delivery_kb,
                parse_mode="HTML",
            )
            delivery_ok = True
        except Exception:
            user_data.pop("cart_delivery_message_id", None)

    if not delivery_ok:
        sent_delivery = await chat.send_message(delivery_msg, reply_markup=delivery_kb, parse_mode="HTML")
        user_data["cart_delivery_message_id"] = sent_delivery.message_id


async def remove_cart_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        idx = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.answer("Invalid item.", show_alert=True)
        return
    user_data = context.user_data
    cart_items = get_cart_items(user_data)
    if idx < 0 or idx >= len(cart_items):
        await query.answer("Item not found.", show_alert=True)
        return
    cart_items.pop(idx)
    reset_cart_discount(user_data)
    await show_cart(update, context)


async def cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    if data == "enter_address":
        user_data["awaiting_discount"] = False
        await send_location_prompt(query.message.chat, user_data, update)
    elif data == "enter_phone":
        user_data["awaiting_discount"] = False
        await send_phone_prompt(query.message.chat, user_data)
    elif data == "enter_discount":
        user_data["awaiting_discount"] = True
        user_data["awaiting_address"] = False
        user_data["awaiting_phone"] = False
        await query.message.chat.send_message(
            "Send your discount or referral code now.\n"
            "Example: SUMMER20 or REF123456789"
        )
    elif data == "show_location_keyboard":
        if is_desktop_or_web_telegram(update):
            await query.answer("On desktop/web use 📎 or paste a Google Maps link.", show_alert=True)
            return
        user_data["awaiting_address"] = True
        user_data["awaiting_phone"] = False
        user_data["awaiting_discount"] = False
        await query.message.chat.send_message(
            build_location_prompt_text(True),
            reply_markup=build_location_reply_keyboard(),
        )
    elif data == "checkout":
        # Proceed to payment
        await checkout_handler(update, context)
    elif data == "menu_shop":
        await menu_handler(update, context)
    elif data == "main_menu":
        await start(update, context)


async def _handle_discount_code_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Process text while awaiting a discount/referral code. Returns True if handled."""
    user_data = context.user_data
    if not user_data.get("awaiting_discount"):
        return False
    user_data["awaiting_discount"] = False
    code = (update.message.text or "").strip().upper()
    if not code:
        await update.message.reply_text("Please send a valid discount code.")
        return True

    discount = get_discount_code(code)
    if discount:
        total = apply_discount_to_cart(user_data, discount["code"], discount["percent"])
        await update.message.reply_text(
            f"Discount applied: {discount['percent']}% off ({discount['code']}).\n"
            f"New total: {format_price(total)}"
        )
        await show_cart(update, context, refresh_at_bottom=True)
        return True

    referrer = get_referrer_from_code(code)
    if referrer is not None:
        if referrer == update.effective_user.id:
            await update.message.reply_text("You cannot use your own referral code.")
            return True
        user_data["cart_referred_by"] = referrer
        total = apply_discount_to_cart(user_data, code, 10)
        await update.message.reply_text(
            f"Referral code applied: 10% off.\nNew total: {format_price(total)}"
        )
        await show_cart(update, context, refresh_at_bottom=True)
        return True

    await update.message.reply_text("Invalid or expired discount code.")
    return True


async def _handle_admin_discount_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Process admin interactive discount creation. Returns True if handled."""
    user_data = context.user_data
    if update.effective_user.id != ADMIN_USER_ID or not user_data.get("awaiting_admin_discount"):
        return False
    parts = (update.message.text or "").strip().split()
    if len(parts) < 3:
        await update.message.reply_text(
            "Format: CODE PERCENT YYYY-MM-DD\nExample: SUMMER20 20 2026-12-31"
        )
        return True
    code, percent_raw, expires = parts[0], parts[1], parts[2]
    try:
        percent = int(percent_raw)
        date.fromisoformat(expires)
    except Exception:
        await update.message.reply_text("Invalid percent or date format (use YYYY-MM-DD).")
        return True
    if percent <= 0 or percent > 100:
        await update.message.reply_text("Percent must be between 1 and 100.")
        return True
    add_discount_code(code, percent, expires)
    user_data["awaiting_admin_discount"] = False
    await update.message.reply_text(
        f"Discount code {code.upper()} for {percent}% off until {expires} added."
    )
    return True


async def address_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if await _handle_discount_code_message(update, context):
        return
    if await _handle_admin_discount_message(update, context):
        return
    if user_data.get("awaiting_phone"):
        phone = update.message.text.strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 8:
            await update.message.reply_text("Please send a valid phone number.")
            return
        user_data["cart_phone"] = phone
        user_data["awaiting_phone"] = False
        await update.message.reply_text("Phone saved.", reply_markup=ReplyKeyboardRemove())
        await show_cart(update, context, refresh_at_bottom=True)
        return
    if user_data.get("awaiting_address"):
        address = update.message.text.strip()
        maps_hint = "google.com/maps" in address.lower() or "maps.app.goo.gl" in address.lower()
        if not maps_hint:
            await update.message.reply_text(
                "Please send a Google Maps link + comment (hotel/house/apartment details), "
                "or send your location pin."
            )
            return
        user_data["cart_address"] = address
        user_data["is_text_location_user"] = True
        user_data["awaiting_address"] = False
        await update.message.reply_text("Location saved.", reply_markup=ReplyKeyboardRemove())
        await show_cart(update, context, refresh_at_bottom=True)


async def location_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if not user_data.get("awaiting_address"):
        return
    loc = update.message.location
    if not loc:
        return
    user_data["cart_address"] = f"https://maps.google.com/?q={loc.latitude},{loc.longitude}"
    user_data["has_shared_location_before"] = True
    user_data["awaiting_address"] = False
    await update.message.reply_text("Location saved.", reply_markup=ReplyKeyboardRemove())
    await show_cart(update, context, refresh_at_bottom=True)


async def contact_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if not user_data.get("awaiting_phone"):
        return
    contact = update.message.contact
    if not contact or not contact.phone_number:
        return
    user_data["cart_phone"] = contact.phone_number
    user_data["awaiting_phone"] = False
    await update.message.reply_text("Phone saved.", reply_markup=ReplyKeyboardRemove())
    await show_cart(update, context, refresh_at_bottom=True)


async def checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat = query.message.chat
    user_id = update.effective_user.id
    user_data = context.user_data
    cart_items = get_cart_items(user_data)
    if not cart_items:
        await chat.send_message(
            "Your cart is empty.",
            reply_markup=build_empty_cart_keyboard(),
        )
        return
    price = sync_cart_price(user_data)
    address = user_data.get("cart_address")
    if not address:
        user_data["awaiting_address"] = True
        show_gps = should_offer_gps_reply_keyboard(user_data, update)
        await chat.send_message(
            build_location_prompt_text(show_gps),
            reply_markup=build_checkout_location_keyboard(),
        )
        return
    await chat.send_message(
        build_checkout_review_message(user_data, price),
        parse_mode="HTML",
    )

    payment_keyboard = build_checkout_payment_keyboard(user_data)
    if payment_keyboard:
        await chat.send_message("Choose payment method:", reply_markup=payment_keyboard)
        return

    if get_oxapay_api_key():
        await start_crypto_payment(context, chat, user_id, user_data, cart_items, price)
        return

    if is_telegram_pay_enabled():
        await start_telegram_payment(context, chat, user_id, user_data, cart_items, price)
        return

    await chat.send_message(
        "No payment method configured.\n"
        "Admin: set OXAPAY_API_KEY in .env (recommended), or enable ENABLE_TELEGRAM_PAY=true with PAYMENT_PROVIDER_TOKEN."
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    # Legacy: one product button -> single card (replaced by shop card feed)
    # if data.startswith("select_"):
    #     await select_product_handler(update, context)
    if data.startswith("add_"):
        await add_to_cart_handler(update, context)
    elif data.startswith("qty_"):
        await quantity_handler(update, context)
    elif data == "open_cart":
        await open_cart_handler(update, context)
    elif data.startswith("cart_remove_"):
        await remove_cart_item_handler(update, context)
    elif data == "noop_qty_missing":
        await query.answer("No price post for this product yet.", show_alert=True)
    elif data == "menu_shop":
        await menu_handler(update, context)
    elif data == "main_menu":
        await start(update, context)
    elif data.startswith("giveaway_"):
        giveaway_id = int(data.split("_")[1])
        giveaways = get_active_giveaways()
        giveaway = next((g for g in giveaways if g[0] == giveaway_id), None)
        if not giveaway:
            await query.edit_message_text("Giveaway not found!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]))
            return
        
        # Show giveaway details
        end_date = date.fromisoformat(giveaway[4])
        days_left = (end_date - date.today()).days
        message = f"🎁 **{giveaway[1]}**\n\n{giveaway[2]}\n\n🏆 **Prize:** {giveaway[3]}\n⏰ **Ends in:** {days_left} days\n📅 **End Date:** {giveaway[4]}"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Enter Giveaway", callback_data=f"enter_giveaway_{giveaway_id}")],
            [InlineKeyboardButton("Back to Giveaways", callback_data="menu_giveaways"), InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    elif data.startswith("enter_giveaway_"):
        giveaway_id = int(data.split("_")[2])
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name or "Unknown"
        
        success, message = enter_giveaway(giveaway_id, user_id, username)
        keyboard = [
            [InlineKeyboardButton("Back to Giveaways", callback_data="menu_giveaways")],
            [InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
    elif data == "back_to_cart":
        context.user_data["awaiting_address"] = False
        context.user_data["awaiting_phone"] = False
        context.user_data["awaiting_discount"] = False
        await show_cart(update, context)
    elif data in ["enter_address", "enter_phone", "enter_discount", "checkout", "show_location_keyboard"]:
        await cart_handler(update, context)
    elif data == "pay_telegram":
        await query.answer()
        user_data = context.user_data
        cart_items = get_cart_items(user_data)
        if not cart_items:
            await query.edit_message_text("Your cart is empty.", reply_markup=build_empty_cart_keyboard())
            return
        price = sync_cart_price(user_data)
        await start_telegram_payment(
            context,
            query.message.chat,
            update.effective_user.id,
            user_data,
            cart_items,
            price,
        )
    elif data == "pay_crypto":
        await query.answer()
        user_data = context.user_data
        cart_items = get_cart_items(user_data)
        if not cart_items:
            await query.edit_message_text("Your cart is empty.", reply_markup=build_empty_cart_keyboard())
            return
        price = sync_cart_price(user_data)
        await start_crypto_payment(
            context,
            query.message.chat,
            update.effective_user.id,
            user_data,
            cart_items,
            price,
        )
    elif data.startswith("check_crypto_"):
        track_id = data[len("check_crypto_"):]
        user_data = context.user_data
        status_data = check_crypto_payment_invoice(track_id)
        if is_crypto_payment_paid(status_data):
            items = user_data.get("pending_items") or get_cart_items(user_data)
            if not items:
                await query.edit_message_text("Your cart is empty.")
                return
            total_price = user_data.get("pending_price") or user_data.get("cart_price")
            summary = fulfill_paid_cart(
                update.effective_user.id,
                items,
                track_id,
                user_data.get("cart_discount_code"),
                user_data.get("cart_discount_percent", 0),
                user_data.get("cart_referred_by"),
                user_data.get("cart_address"),
                user_data.get("cart_phone"),
            )
            if total_price is not None:
                summary.append(f"\nTotal paid: {format_price(total_price)}")
            await query.edit_message_text("\n".join(summary))
            clear_cart_after_payment(context.user_data)
        else:
            await query.answer("Payment not detected yet. Wait a minute and try again.", show_alert=True)
    elif data.startswith("check_"):
        _, invoice_id, product_id = data.split("_")
        user_data = context.user_data
        status_data = check_crypto_payment_invoice(invoice_id)
        if is_crypto_payment_paid(status_data):
            items = user_data.get("pending_items") or get_cart_items(user_data)
            if not items:
                await query.edit_message_text("Your cart is empty.")
                return
            total_price = user_data.get("pending_price") or user_data.get("cart_price")
            summary = fulfill_paid_cart(
                update.effective_user.id,
                items,
                invoice_id,
                user_data.get("cart_discount_code"),
                user_data.get("cart_discount_percent", 0),
                user_data.get("cart_referred_by"),
                user_data.get("cart_address"),
                user_data.get("cart_phone"),
            )
            if total_price is not None:
                summary.append(f"\nTotal paid: {format_price(total_price)}")
            await query.edit_message_text("\n".join(summary))
            clear_cart_after_payment(context.user_data)
        else:
            await query.edit_message_text("Payment not detected yet. Please wait a minute and try again.")
    elif data.startswith("menu_"):
        await menu_handler(update, context)
    elif data == "admin_panel":
        await admin_panel_handler(update, context)
    elif data == "admin_orders":
        await admin_orders_handler(update, context)
    elif data == "admin_giveaways":
        await admin_giveaways_handler(update, context)
    elif data == "admin_discount":
        await admin_discount_handler(update, context)
    elif data == "admin_stats":
        await admin_stats_handler(update, context)
    elif data == "admin_broadcast":
        await admin_broadcast_handler(update, context)
    elif data == "admin_giveaway_entries":
        await admin_giveaway_entries_handler(update, context)
    elif data.startswith("view_entries_"):
        await view_entries_handler(update, context)
    elif data.startswith("copy_entries_"):
        giveaway_id = int(data.split("_")[2])
        entries = get_giveaway_entries(giveaway_id)
        giveaway = next((g for g in get_active_giveaways() if g[0] == giveaway_id), None)
        if not giveaway:
            await update.callback_query.edit_message_text("Giveaway not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_giveaway_entries")]]))
            return
        
        numbered_list = ""
        for i, entry in enumerate(entries, 1):
            username = entry[1] if entry[1] else f"User{entry[0]}"
            numbered_list += f"{i}. @{username}\n"
        
        await update.callback_query.edit_message_text(numbered_list, parse_mode='Markdown')

async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to view orders.")
        return
    orders = get_recent_orders(10)
    if not orders:
        await update.message.reply_text("No orders found.")
        return
    msg = "Recent Orders:\n"
    for o in orders:
        msg += f"\nTime: {o[0]}\nUser ID: {o[1]}\nProduct: {o[3]} (ID: {o[2]})\nQuantity: {o[4]}\nPrice: {format_price(o[5])}\nInvoice ID: {o[6]}\nDiscount: {o[7]} ({o[8]}%)\nReferred by: {o[9]}\nAddress: {o[10]}\nPhone: {o[11] or '—'}\n---"
    await update.message.reply_text(msg)

async def addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to add codes.")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /addcode CODE PERCENT YYYY-MM-DD (expiry)")
        return
    code = args[0]
    try:
        percent = int(args[1])
        expires = args[2]
        date.fromisoformat(expires)
    except Exception:
        await update.message.reply_text("Invalid percent or date format.")
        return
    add_discount_code(code, percent, expires)
    await update.message.reply_text(f"Discount code {code} for {percent}% off until {expires} added.")

async def create_giveaway_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to create giveaways.")
        return
    
    # Get the full message text
    full_text = update.message.text
    if not full_text.startswith('/create_giveaway'):
        return
    
    # Remove the command part
    args_text = full_text[len('/create_giveaway'):].strip()
    
    # Split by spaces
    parts = args_text.split()
    
    if len(parts) < 3:
        await update.message.reply_text("Usage: /create_giveaway TITLE DESCRIPTION END_DATE [MAX_ENTRIES]")
        await update.message.reply_text("Example: /create_giveaway Monthly_Prize Win_amazing_products 2025-01-31 100")
        await update.message.reply_text("Note: Use underscores instead of spaces for title and description")
        return
    
    # Extract arguments
    title = parts[0].replace('_', ' ')
    description = parts[1].replace('_', ' ')
    end_date_str = parts[2]
    
    try:
        max_entries = int(parts[3]) if len(parts) > 3 else 100
    except (ValueError, IndexError):
        max_entries = 100
    
    try:
        date.fromisoformat(end_date_str)
    except Exception:
        await update.message.reply_text("Invalid date format. Use YYYY-MM-DD")
        return
    
    giveaway_id = create_giveaway(title, description, end_date_str, max_entries)
    await update.message.reply_text(f"✅ Giveaway '{title}' created successfully with ID: {giveaway_id}")

async def list_giveaways(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to view giveaways.")
        return
    
    giveaways = get_active_giveaways()
    if not giveaways:
        await update.message.reply_text("No active giveaways.")
        return
    
    msg = "Active Giveaways:\n\n"
    for g in giveaways:
        entries = get_giveaway_entries(g[0])
        msg += f"ID: {g[0]}\nTitle: {g[1]}\nPrize: {g[3]}\nEntries: {len(entries)}/{g[6]}\nEnd Date: {g[4]}\n---\n"
    
    await update.message.reply_text(msg)

async def view_giveaway_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to view giveaway entries.")
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Usage: /view_entries GIVEAWAY_ID")
        return
    
    try:
        giveaway_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid giveaway ID.")
        return
    
    entries = get_giveaway_entries(giveaway_id)
    if not entries:
        await update.message.reply_text(f"No entries found for giveaway {giveaway_id}.")
        return
    
    msg = f"Entries for Giveaway {giveaway_id}:\n\n"
    for i, entry in enumerate(entries, 1):
        msg += f"{i}. User: {entry[0]} (@{entry[1]})\n"
        msg += f"   Date: {entry[2][:19]}\n"
        msg += "---\n"
    
    await update.message.reply_text(msg)

async def export_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to export orders.")
        return
    
    orders = get_recent_orders(1000)
    if not orders:
        await update.message.reply_text("No orders to export.")
        return
    
    # Create CSV-like format
    csv_data = "Order ID,User ID,Product,Quantity,Price,Invoice ID,Discount Code,Discount %,Referred By,Address,Phone,Date\n"
    for order in orders:
        csv_data += f"{order[0]},{order[1]},{order[3]},{order[4]},{order[5]},{order[6]},{order[7] or ''},{order[8] or 0},{order[9] or ''},{order[10] or ''},{order[11] or ''},{order[0]}\n"
    
    # Save to file
    filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(csv_data)
    
    await update.message.reply_text(f"Orders exported to {filename}")

async def bot_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You are not authorized to view bot status.")
        return
    
    orders = get_recent_orders(1000)
    giveaways = get_active_giveaways()
    
    total_orders = len(orders)
    total_revenue = sum(order[5] for order in orders)
    active_giveaways = len(giveaways)
    total_entries = sum(len(get_giveaway_entries(g[0])) for g in giveaways)
    
    msg = "🤖 **Bot Status Report**\n\n"
    msg += f"📦 **Total Orders:** {total_orders}\n"
    msg += f"💰 **Total Revenue:** {format_price(total_revenue)}\n"
    msg += f"🎁 **Active Giveaways:** {active_giveaways}\n"
    msg += f"👥 **Total Giveaway Entries:** {total_entries}\n"
    msg += f"📅 **Report Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"🟢 **Bot Status:** Online and Running\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to access the admin panel.")
        return
    
    await query.answer()
    context.user_data["awaiting_admin_discount"] = False

    keyboard = [
        [InlineKeyboardButton("View Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("Manage Giveaways", callback_data="admin_giveaways")],
        [InlineKeyboardButton("Add Discount Code", callback_data="admin_discount")],
        [InlineKeyboardButton("Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Admin Panel\n\nSelect an option to manage your bot:", reply_markup=reply_markup)


async def admin_discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to add discount codes.")
        return
    await query.answer()
    context.user_data["awaiting_admin_discount"] = True
    message = (
        "<b>Add Discount Code</b>\n\n"
        "Send a message in this format:\n"
        "<code>CODE PERCENT YYYY-MM-DD</code>\n\n"
        "Example: <code>SUMMER20 20 2026-12-31</code>\n\n"
        "Or use the command:\n"
        "<code>/addcode CODE PERCENT YYYY-MM-DD</code>"
    )
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]]
        ),
        parse_mode="HTML",
    )

async def admin_orders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to view orders.")
        return
    
    await query.answer()
    
    orders = get_recent_orders(20)
    if not orders:
        await query.edit_message_text("No orders found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]]))
        return
    
    msg = "Recent Orders\n\n"
    total_revenue = 0
    
    for i, order in enumerate(orders[:10], 1):  # Show first 10 orders
        msg += f"{i}. Order #{order[0]}\n"
        msg += f"User: {order[1]}\n"
        msg += f"Product: {order[3]} (Qty: {order[4]})\n"
        msg += f"Price: {format_price(order[5])}\n"
        msg += f"Date: {order[0][:19]}\n"
        if order[7]:  # Discount code
            msg += f"Discount: {order[7]} ({order[8]}%)\n"
        if order[10]:
            msg += f"Address: {order[10]}\n"
        if len(order) > 11 and order[11]:
            msg += f"Phone: {order[11]}\n"
        msg += f"Invoice: {order[6]}\n"
        msg += "---\n"
        total_revenue += order[5]
    
    msg += f"\nTotal Revenue (last 10): {format_price(total_revenue)}"
    
    keyboard = [
        [InlineKeyboardButton("Export Orders", callback_data="admin_export_orders")],
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_giveaways_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to manage giveaways.")
        return
    
    await query.answer()
    
    giveaways = get_active_giveaways()
    if not giveaways:
        msg = "No Active Giveaways\n\nUse /create_giveaway to create a new giveaway."
    else:
        msg = "Active Giveaways\n\n"
        for g in giveaways:
            entries = get_giveaway_entries(g[0])
            end_date = date.fromisoformat(g[4])
            days_left = (end_date - date.today()).days
            msg += f"{g[1]} (ID: {g[0]})\n"
            msg += f"Prize: {g[3]}\n"
            msg += f"Entries: {len(entries)}/{g[6]}\n"
            msg += f"Days Left: {days_left}\n"
            msg += "---\n"
    
    keyboard = [
        [InlineKeyboardButton("View Entries", callback_data="admin_giveaway_entries")],
        [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to view statistics.")
        return
    
    await query.answer()
    
    # Get basic stats
    orders = get_recent_orders(1000)  # Get all orders for stats
    giveaways = get_active_giveaways()
    
    total_orders = len(orders)
    total_revenue = sum(order[5] for order in orders)
    active_giveaways = len(giveaways)
    total_entries = sum(len(get_giveaway_entries(g[0])) for g in giveaways)
    
    msg = "📈 Bot Statistics\n\n"
    msg += f"📦 Total Orders: {total_orders}\n"
    msg += f"💰 Total Revenue: {format_price(total_revenue)}\n"
    msg += f"🎁 Active Giveaways: {active_giveaways}\n"
    msg += f"👥 Total Giveaway Entries: {total_entries}\n"
    msg += f"📅 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    
    keyboard = [
        [InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to send broadcasts.")
        return
    
    await query.answer()
    
    msg = "📢 Broadcast Message\n\n"
    msg += "Send your broadcast message in the next message.\n\n"
    msg += "Supported formats:\n"
    msg += "• Plain text\n"
    msg += "• Markdown formatting\n\n"
    msg += "Recipients: All users who have interacted with the bot"
    
    context.user_data["awaiting_broadcast"] = True
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup)

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = context.user_data
    
    if user_id != ADMIN_USER_ID or not user_data.get("awaiting_broadcast"):
        return
    
    message_text = update.message.text
    users = get_all_users()
    
    if not users:
        await update.message.reply_text("No users found to broadcast to.")
        user_data["awaiting_broadcast"] = False
        return
    
    # Save broadcast message
    save_broadcast_message(message_text, user_id)
    
    # Send to all users
    success_count = 0
    failed_count = 0
    
    for user_id_target in users:
        try:
            await context.bot.send_message(
                chat_id=user_id_target,
                text=message_text,
                parse_mode='Markdown'
            )
            success_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Failed to send to {user_id_target}: {e}")
    
    await update.message.reply_text(
        f"📢 Broadcast Complete!\n\n"
        f"✅ Sent successfully: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"📊 Total recipients: {len(users)}"
    )
    
    user_data["awaiting_broadcast"] = False

async def admin_giveaway_entries_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to view entries.")
        return
    
    await query.answer()
    
    giveaways = get_active_giveaways()
    if not giveaways:
        await query.edit_message_text("No active giveaways found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")]]))
        return
    
    keyboard = []
    for g in giveaways:
        entries = get_giveaway_entries(g[0])
        keyboard.append([InlineKeyboardButton(f"🎁 {g[1]} ({len(entries)} entries)", callback_data=f"view_entries_{g[0]}")])
    
    keyboard.append([InlineKeyboardButton("Back to Admin Panel", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("🎁 Select Giveaway to View Entries:", reply_markup=reply_markup)

async def view_entries_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to view entries.")
        return
    
    await query.answer()
    
    data = query.data
    giveaway_id = int(data.split("_")[2])
    
    entries = get_giveaway_entries(giveaway_id)
    giveaways = get_active_giveaways()
    giveaway = next((g for g in giveaways if g[0] == giveaway_id), None)
    
    if not entries:
        await query.edit_message_text(f"No entries found for giveaway: {giveaway[1] if giveaway else 'Unknown'}", 
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_giveaway_entries")]]))
        return
    
    msg = f"🎁 Entries for: {giveaway[1] if giveaway else 'Unknown'}\n\n"
    msg += "Numbered List for Random Picker:\n"
    
    # Create numbered list for random picker
    numbered_list = ""
    for i, entry in enumerate(entries, 1):
        username = entry[1] if entry[1] else f"User{entry[0]}"
        numbered_list += f"{i}. @{username}\n"
    
    msg += numbered_list
    msg += f"\nTotal Entries: {len(entries)}"
    
    keyboard = [
        [InlineKeyboardButton("📋 Copy List", callback_data=f"copy_entries_{giveaway_id}")],
        [InlineKeyboardButton("Back", callback_data="admin_giveaway_entries")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')


async def channel_catalog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post or update.edited_channel_post
    if not post or post.chat_id != config.STOCK_CHANNEL_ID:
        return
    count = await process_catalog_message(post)
    logging.info("Catalog sync: %s products from channel message %s", count, post.message_id)


async def admin_forwarded_catalog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or update.effective_user.id != ADMIN_USER_ID:
        return
    channel_id = None
    if msg.forward_from_chat:
        channel_id = msg.forward_from_chat.id
    elif msg.forward_origin and isinstance(msg.forward_origin, MessageOriginChannel):
        channel_id = msg.forward_origin.chat.id
    if channel_id != config.STOCK_CHANNEL_ID:
        return
    count = await process_catalog_message(msg)
    await msg.reply_text(f"Catalog updated: {count} product(s) parsed.")


def _format_catalog_sync_result(result: dict) -> str:
    lines = [
        "Catalog sync finished." if result.get("ok") else "Catalog sync finished with issues.",
        f"Cache posts scanned: {result.get('cache_posts_scanned', 0)}",
        f"Price post: message {result.get('price_message_id') or '—'}",
        f"Items on price list: {result.get('price_items', 0)}",
        f"Cards linked: {result.get('cards_linked', 0)}",
        f"Cards missing from cache: {result.get('cards_missing', 0)}",
        f"Shop (Available): {result.get('shop_available', 0)} of {result.get('total_products', 0)} in DB",
    ]
    errors = result.get("errors") or []
    if errors:
        lines.append("")
        lines.append("Notes:")
        for err in errors[:8]:
            lines.append(f"• {err}")
        if len(errors) > 8:
            lines.append(f"• …and {len(errors) - 8} more")
    if not result.get("ok"):
        lines.append("")
        lines.append(
            "Ensure the bot is channel admin and has cached the latest AVAILABLE price post "
            "(forward it to the bot if needed)."
        )
    return "\n".join(lines)


async def sync_catalog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Not authorized.")
        return
    limit = getattr(config, "CATALOG_SYNC_POST_LIMIT", 60)
    await update.message.reply_text(f"Syncing catalog (newest {limit} cached posts)…")
    result = catalog_store.sync_catalog_full(limit=limit)
    await update.message.reply_text(_format_catalog_sync_result(result))


async def _sync_last_posts_reply(update: Update, limit: int) -> None:
    await update.message.reply_text(f"Syncing catalog (newest {limit} cached posts)…")
    result = catalog_store.sync_catalog_full(limit=limit)
    await update.message.reply_text(_format_catalog_sync_result(result))


async def sync_last_30_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Not authorized.")
        return
    await _sync_last_posts_reply(update, 30)


async def sync_last_60_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Not authorized.")
        return
    await _sync_last_posts_reply(update, 60)


async def setup_bot_commands(application) -> None:
    """Hide admin-only commands from the menu for regular users."""
    await application.bot.set_my_commands(PUBLIC_BOT_COMMANDS, scope=BotCommandScopeDefault())
    await application.bot.set_my_commands(
        ADMIN_BOT_COMMANDS,
        scope=BotCommandScopeChat(chat_id=ADMIN_USER_ID),
    )


if __name__ == "__main__":
    init_db()
    init_giveaway_db()
    catalog_store.init_catalog_db()
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(setup_bot_commands)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CommandHandler("addcode", addcode))
    app.add_handler(CommandHandler("create_giveaway", create_giveaway_cmd))
    app.add_handler(CommandHandler("list_giveaways", list_giveaways))
    app.add_handler(CommandHandler("view_entries", view_giveaway_entries))
    app.add_handler(CommandHandler("export_orders", export_orders))
    app.add_handler(CommandHandler("bot_status", bot_status))
    app.add_handler(
        CommandHandler("sync_catalog", sync_catalog_cmd, filters=ADMIN_USER_FILTER)
    )
    app.add_handler(
        CommandHandler("sync_last_30", sync_last_30_cmd, filters=ADMIN_USER_FILTER)
    )
    app.add_handler(
        CommandHandler("sync_last_60", sync_last_60_cmd, filters=ADMIN_USER_FILTER)
    )
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_catalog_handler))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.FORWARDED, admin_forwarded_catalog_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_message_handler))
    app.add_handler(MessageHandler(filters.CONTACT, contact_message_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler))
    print("Bot is running...")
    app.run_polling() 