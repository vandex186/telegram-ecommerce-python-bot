import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import requests
import config
import time
import random
import sqlite3
from datetime import datetime, date
import os

ADMIN_USER_ID = config.ADMIN_USER_ID  # Get from config file

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
        address TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
        code TEXT PRIMARY KEY,
        percent INTEGER,
        expires TEXT
    )''')
    conn.commit()
    conn.close()

def save_order(user_id, product, quantity, price, invoice_id, discount_code=None, discount_percent=0, referred_by=None, address=None):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("INSERT INTO orders (timestamp, user_id, product_id, product_name, quantity, price, invoice_id, discount_code, discount_percent, referred_by, address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (datetime.now().isoformat(), user_id, product["id"], product["name"], quantity, price, invoice_id, discount_code, discount_percent, referred_by, address))
    conn.commit()
    conn.close()

def get_recent_orders(limit=10):
    conn = sqlite3.connect("orders.db")
    c = conn.cursor()
    c.execute("SELECT timestamp, user_id, product_id, product_name, quantity, price, invoice_id, discount_code, discount_percent, referred_by, address FROM orders ORDER BY id DESC LIMIT ?", (limit,))
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

def create_crypto_payment_invoice(product, user_id, price):
    if not config.OXAPAY_API_KEY:
        fake_invoice_id = str(random.randint(10000000, 99999999))
        fake_pay_url = f"https://pay.crypto-provider.com/test/{fake_invoice_id}"
        return {"invoice_id": fake_invoice_id, "pay_url": fake_pay_url}
    url = "https://api.crypto-provider.com/merchant/invoice"
    headers = {"Content-Type": "application/json", "Authorization": config.OXAPAY_API_KEY}
    data = {
        "out": str(price),
        "out_currency": config.CURRENCY,
        "callback_url": "",
        "order_id": f"{user_id}_{product['id']}_{int(time.time())}",
        "description": product["name"]
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        return response.json().get("result", {})
    return None

def check_crypto_payment_invoice(invoice_id):
    if not config.OXAPAY_API_KEY:
        return {"status": "paid"}
    url = f"https://api.crypto-provider.com/merchant/invoice/{invoice_id}"
    headers = {"Authorization": config.OXAPAY_API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("result", {})
    return None

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_USER_ID
    
    # Respond appropriately for both messages and callback queries
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text("Welcome to the shop!")
        target = update.message
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text("Welcome to the shop!")
        target = update.callback_query.message
    else:
        return
    
    if is_admin:
        keyboard = [
            [InlineKeyboardButton("Shop", callback_data="menu_shop")],
            [InlineKeyboardButton("Giveaways", callback_data="menu_giveaways")],
            [InlineKeyboardButton("Support", callback_data="menu_support")],
            [InlineKeyboardButton("Refer a Friend", callback_data="menu_refer")],
            [InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("Shop", callback_data="menu_shop")],
            [InlineKeyboardButton("Giveaways", callback_data="menu_giveaways")],
            [InlineKeyboardButton("Support", callback_data="menu_support")],
            [InlineKeyboardButton("Refer a Friend", callback_data="menu_refer")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text("Please choose an option:", reply_markup=reply_markup)

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data == "menu_shop":
        keyboard = [
            [InlineKeyboardButton(f"{p['name']}", callback_data=f"select_{p['id']}")]
            for p in config.PRODUCTS
        ]
        keyboard.append([InlineKeyboardButton("Main Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Select a product:', reply_markup=reply_markup)
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
    elif data == "menu_refer":
        code = generate_referral_code(user_id)
        await query.edit_message_text(f"Share this referral code with friends for a discount: {code}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]))
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
        product = next((p for p in config.PRODUCTS if p["id"] == product_id), None)
        if not product:
            await query.edit_message_text("Product not found.")
            return
        context.user_data["cart_product"] = product
        keyboard = [
            [InlineKeyboardButton(f"{qty} for £{product['prices'][qty]} {config.CURRENCY}", callback_data=f"qty_{qty}") for qty in product["prices"]],
            [InlineKeyboardButton("Back", callback_data="menu_shop"), InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Select quantity for {product['name']}:\n{product['description']}", reply_markup=reply_markup)

async def quantity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("qty_"):
        qty = int(data.split("_")[1])
        product = context.user_data.get("cart_product")
        if not product:
            await query.edit_message_text("No product selected.")
            return
        price = product["prices"][qty]
        context.user_data["cart_quantity"] = qty
        context.user_data["cart_price"] = price
        context.user_data["cart_discount_code"] = None
        context.user_data["cart_discount_percent"] = 0
        context.user_data["cart_referred_by"] = None
        context.user_data["cart_address"] = None
        await show_cart(update, context)

async def show_cart(update_or_query, context):
    user_data = context.user_data
    product = user_data.get("cart_product")
    qty = user_data.get("cart_quantity")
    price = user_data.get("cart_price")
    discount_code = user_data.get("cart_discount_code")
    discount_percent = user_data.get("cart_discount_percent", 0)
    referred_by = user_data.get("cart_referred_by")
    address = user_data.get("cart_address")
    subtotal = price
    msg = f"Cart:\nProduct: {product['name']}\nQuantity: {qty}\nSubtotal: £{subtotal} {config.CURRENCY}"
    if discount_percent:
        msg += f"\nDiscount: {discount_percent}% ({discount_code})"
    # Do not echo the address, just show checkmark on button
    address_entered = bool(address)
    address_btn_text = "Enter Address ✅" if address_entered else "Enter Address"
    keyboard = [
        [InlineKeyboardButton(address_btn_text, callback_data="enter_address")],
        [InlineKeyboardButton("Apply Discount Code", callback_data="apply_discount")],
        [InlineKeyboardButton("Checkout", callback_data="checkout")],
        [InlineKeyboardButton("Back", callback_data="menu_shop"), InlineKeyboardButton("Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Robust handling for both messages and callback queries
    if hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(msg, reply_markup=reply_markup)
    elif hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(msg, reply_markup=reply_markup)
    elif hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
        await update_or_query.callback_query.edit_message_text(msg, reply_markup=reply_markup)

async def cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    if data == "enter_address":
        user_data["awaiting_address"] = True
        await query.edit_message_text(
            "Please enter your shipping address in this format:\nJohn Doe\nFlat 2B, 123 Green Street\nLondon\nNW1 5DB\nUnited Kingdom"
        )
    elif data == "apply_discount":
        user_data["awaiting_discount"] = True
        await query.edit_message_text("Please enter your discount or referral code, or type 'skip' to continue.")
    elif data == "checkout":
        # Proceed to payment
        await checkout_handler(update, context)
    elif data == "menu_shop":
        await menu_handler(update, context)
    elif data == "main_menu":
        await start(update, context)

async def address_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    if user_data.get("awaiting_address"):
        address = update.message.text.strip()
        user_data["cart_address"] = address
        user_data["awaiting_address"] = False
        await show_cart(update, context)

async def discount_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = context.user_data
    if user_data.get("awaiting_discount"):
        text = update.message.text.strip()
        product = user_data.get("cart_product")
        qty = user_data.get("cart_quantity")
        price = product["prices"][qty]
        discount_percent = 0
        discount_code = None
        referred_by = None
        if text.lower() != "skip":
            code = text.upper()
            referrer = get_referrer_from_code(code)
            if referrer and referrer != user_id:
                discount_percent = 10
                discount_code = code
                referred_by = referrer
            else:
                d = get_discount_code(code)
                if d:
                    discount_percent = d["percent"]
                    discount_code = code
        if discount_percent:
            price = round(price * (1 - discount_percent / 100), 2)
        user_data["cart_price"] = price
        user_data["cart_discount_code"] = discount_code
        user_data["cart_discount_percent"] = discount_percent
        user_data["cart_referred_by"] = referred_by
        user_data["awaiting_discount"] = False
        await show_cart(update, context)

async def checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = context.user_data
    product = user_data.get("cart_product")
    qty = user_data.get("cart_quantity")
    price = user_data.get("cart_price")
    discount_code = user_data.get("cart_discount_code")
    discount_percent = user_data.get("cart_discount_percent", 0)
    referred_by = user_data.get("cart_referred_by")
    address = user_data.get("cart_address")
    if not address:
        await update.callback_query.edit_message_text(
            "Please enter your address before checking out.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Cart", callback_data="back_to_cart")]])
        )
        return
    invoice = create_crypto_payment_invoice(product, user_id, price)
    if not invoice:
        await update.callback_query.edit_message_text("Failed to create payment invoice. Please try again later.")
        return
    pay_url = invoice.get("pay_url")
    invoice_id = invoice.get("invoice_id")
    message = (
        f"Your Telegram User ID: {user_id}\n"
        f"Your Crypto Payment Transaction ID: {invoice_id}\n"
        f"Please pay £{price} {config.CURRENCY} using the link below:\n{pay_url}\n\n"
        "After payment, click the button below."
    )
    user_data["pending_invoice_id"] = invoice_id
    user_data["pending_product_id"] = product["id"]
    user_data["pending_quantity"] = qty
    user_data["pending_price"] = price
    await update.callback_query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("I've paid", callback_data=f"check_{invoice_id}_{product['id']}"), InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ])
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith("select_"):
        await select_product_handler(update, context)
    elif data.startswith("qty_"):
        await quantity_handler(update, context)
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
        await show_cart(update, context)
    elif data in ["enter_address", "apply_discount", "checkout", "menu_shop", "main_menu"]:
        if data == "main_menu":
            await start(update, context)
        else:
            await cart_handler(update, context)
    elif data.startswith("check_"):
        _, invoice_id, product_id = data.split("_")
        user_data = context.user_data
        status = check_crypto_payment_invoice(invoice_id)
        if status and status.get("status") == "paid":
            product = user_data.get("cart_product")
            qty = user_data.get("cart_quantity")
            price = user_data.get("cart_price")
            discount_code = user_data.get("cart_discount_code")
            discount_percent = user_data.get("cart_discount_percent", 0)
            referred_by = user_data.get("cart_referred_by")
            address = user_data.get("cart_address")
            save_order(update.effective_user.id, product, qty, price, invoice_id, discount_code, discount_percent, referred_by, address)
            await query.edit_message_text(f"Payment received! Here is your product: {product['name']}\n{product['description']}\n\nYour order will be shipped to:\n{address}")
            for key in ["cart_product", "cart_quantity", "cart_price", "cart_discount_code", "cart_discount_percent", "cart_referred_by", "cart_address", "pending_invoice_id", "pending_product_id", "pending_quantity", "pending_price"]:
                context.user_data.pop(key, None)
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
        msg += f"\nTime: {o[0]}\nUser ID: {o[1]}\nProduct: {o[3]} (ID: {o[2]})\nQuantity: {o[4]}\nPrice: £{o[5]} {config.CURRENCY}\nInvoice ID: {o[6]}\nDiscount: {o[7]} ({o[8]}%)\nReferred by: {o[9]}\nAddress: {o[10]}\n---"
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
    csv_data = "Order ID,User ID,Product,Quantity,Price,Invoice ID,Discount Code,Discount %,Referred By,Address,Date\n"
    for order in orders:
        csv_data += f"{order[0]},{order[1]},{order[3]},{order[4]},{order[5]},{order[6]},{order[7] or ''},{order[8] or 0},{order[9] or ''},{order[10] or ''},{order[0]}\n"
    
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
    msg += f"💰 **Total Revenue:** £{total_revenue} {config.CURRENCY}\n"
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
    
    keyboard = [
        [InlineKeyboardButton("View Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("Manage Giveaways", callback_data="admin_giveaways")],
        [InlineKeyboardButton("Add Discount Code", callback_data="admin_discount")],
        [InlineKeyboardButton("Bot Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Admin Panel\n\nSelect an option to manage your bot:", reply_markup=reply_markup)

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
        msg += f"Price: £{order[5]} {config.CURRENCY}\n"
        msg += f"Date: {order[0][:19]}\n"
        if order[7]:  # Discount code
            msg += f"Discount: {order[7]} ({order[8]}%)\n"
        msg += f"Invoice: {order[6]}\n"
        msg += "---\n"
        total_revenue += order[5]
    
    msg += f"\nTotal Revenue (last 10): £{total_revenue} {config.CURRENCY}"
    
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

async def admin_discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("You are not authorized to manage discount codes.")
        return
    
    await query.answer()
    
    msg = "💰 Add Discount Code\n\nUse the command:\n/addcode CODE PERCENT YYYY-MM-DD\n\nExample:\n/addcode SUMMER20 20 2024-08-31"
    
    keyboard = [
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
    msg += f"💰 Total Revenue: £{total_revenue} {config.CURRENCY}\n"
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

if __name__ == "__main__":
    init_db()
    init_giveaway_db()
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CommandHandler("addcode", addcode))
    app.add_handler(CommandHandler("create_giveaway", create_giveaway_cmd))
    app.add_handler(CommandHandler("list_giveaways", list_giveaways))
    app.add_handler(CommandHandler("view_entries", view_giveaway_entries))
    app.add_handler(CommandHandler("export_orders", export_orders))
    app.add_handler(CommandHandler("bot_status", bot_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, discount_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler))
    print("Bot is running...")
    app.run_polling() 