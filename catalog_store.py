"""SQLite storage for channel-synced catalog."""
import json
import sqlite3
from datetime import datetime
from typing import Optional

import config
from catalog_parser import parse_catalog_text, parse_price_post, parse_price_post_entries

DB_PATH = config.DATABASE_FILE


def init_catalog_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS catalog_products (
            id INTEGER PRIMARY KEY,
            slug TEXT UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            in_stock INTEGER NOT NULL DEFAULT 0,
            prices_json TEXT,
            photo_file_id TEXT,
            source_message_id INTEGER,
            updated_at TEXT NOT NULL
        )"""
    )
    c.execute("PRAGMA table_info(catalog_products)")
    existing_columns = {row[1] for row in c.fetchall()}
    if "prices_json" not in existing_columns:
        c.execute("ALTER TABLE catalog_products ADD COLUMN prices_json TEXT")
    c.execute(
        """CREATE TABLE IF NOT EXISTS catalog_source_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            text TEXT NOT NULL,
            photo_file_id TEXT,
            posted_at TEXT,
            saved_at TEXT NOT NULL,
            UNIQUE(chat_id, message_id)
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS catalog_price_overrides (
            slug TEXT PRIMARY KEY,
            name TEXT,
            prices_json TEXT NOT NULL,
            source_message_id INTEGER,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


def upsert_products(products: list[dict], photo_file_id: Optional[str], message_id: Optional[int]) -> int:
    if not products:
        return 0
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    for p in products:
        c.execute(
            """INSERT INTO catalog_products
               (id, slug, name, description, in_stock, prices_json, photo_file_id, source_message_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 in_stock=excluded.in_stock,
                 prices_json=COALESCE(excluded.prices_json, catalog_products.prices_json),
                 photo_file_id=COALESCE(excluded.photo_file_id, catalog_products.photo_file_id),
                 source_message_id=excluded.source_message_id,
                 updated_at=excluded.updated_at""",
            (
                p["id"],
                p["slug"],
                p["name"],
                p["description"],
                1 if p["in_stock"] else 0,
                json.dumps(p.get("prices")) if p.get("prices") else None,
                photo_file_id,
                message_id,
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def sync_from_text(text: str, photo_file_id: Optional[str] = None, message_id: Optional[int] = None) -> int:
    products = parse_catalog_text(text)
    return upsert_products(products, photo_file_id, message_id)


def sync_price_post(text: str, message_id: Optional[int] = None) -> int:
    parsed_entries = parse_price_post_entries(text)
    if not parsed_entries:
        single = parse_price_post(text)
        parsed_entries = [single] if single else []
    if not parsed_entries:
        return 0
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    for parsed in parsed_entries:
        c.execute(
            """INSERT INTO catalog_price_overrides (slug, name, prices_json, source_message_id, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 prices_json=excluded.prices_json,
                 source_message_id=excluded.source_message_id,
                 updated_at=excluded.updated_at""",
            (
                parsed["slug"],
                parsed["name"],
                json.dumps(parsed["prices"]),
                message_id,
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def save_source_post(
    chat_id: Optional[int],
    message_id: Optional[int],
    text: str,
    photo_file_id: Optional[str] = None,
    posted_at: Optional[str] = None,
) -> None:
    if not text or not text.strip():
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO catalog_source_posts
           (chat_id, message_id, text, photo_file_id, posted_at, saved_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(chat_id, message_id) DO UPDATE SET
             text=excluded.text,
             photo_file_id=COALESCE(excluded.photo_file_id, catalog_source_posts.photo_file_id),
             posted_at=COALESCE(excluded.posted_at, catalog_source_posts.posted_at),
             saved_at=excluded.saved_at""",
        (chat_id, message_id, text, photo_file_id, posted_at, now),
    )
    conn.commit()
    conn.close()


def sync_last_source_posts(limit: int = 30) -> tuple[int, int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT chat_id, message_id, text, photo_file_id
           FROM catalog_source_posts
           ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC
           LIMIT ?""",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()

    scanned = 0
    imported = 0
    for chat_id, message_id, text, photo_file_id in rows:
        scanned += 1
        imported += sync_from_text(text=text, photo_file_id=photo_file_id, message_id=message_id)
        imported += sync_price_post(text=text, message_id=message_id)
    return scanned, imported


def get_product_by_id(product_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, slug, name, description, in_stock, prices_json, photo_file_id FROM catalog_products WHERE id = ?",
        (product_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_product(row)


def get_shop_products(available_only: bool = True) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if available_only:
        c.execute(
            "SELECT id, slug, name, description, in_stock, prices_json, photo_file_id FROM catalog_products WHERE in_stock = 1 ORDER BY name"
        )
    else:
        c.execute(
            "SELECT id, slug, name, description, in_stock, prices_json, photo_file_id FROM catalog_products ORDER BY name"
        )
    rows = c.fetchall()
    conn.close()
    return [_row_to_product(row) for row in rows]


def _row_to_product(row) -> dict:
    product_id, slug, name, description, in_stock, prices_json, photo_file_id = row
    parsed_prices = None
    if prices_json:
        try:
            raw = json.loads(prices_json)
            parsed_prices = {int(k): float(v) for k, v in raw.items()}
        except Exception:
            parsed_prices = None
    prices = _get_price_for_slug(slug, parsed_prices)
    return {
        "id": product_id,
        "slug": slug,
        "name": name,
        "description": description,
        "in_stock": bool(in_stock),
        "prices": prices,
        "image": None,
        "photo_file_id": photo_file_id,
    }


def _get_price_for_slug(slug: str, parsed_prices: Optional[dict]) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT prices_json FROM catalog_price_overrides WHERE slug = ?", (slug,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        try:
            raw = json.loads(row[0])
            return {int(k): float(v) for k, v in raw.items()}
        except Exception:
            pass
    return parsed_prices or {}


def catalog_stats() -> tuple[int, int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM catalog_products")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM catalog_products WHERE in_stock = 1")
    available = c.fetchone()[0]
    conn.close()
    return total, available
