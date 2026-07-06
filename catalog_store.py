"""SQLite storage for channel-synced catalog."""
import json
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

import config
from catalog_parser import (
    is_price_post,
    parse_catalog_text,
    parse_price_post,
    parse_price_post_entries,
    parse_price_post_entries_with_links,
    _stable_id,
)

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


def upsert_products(
    products: list[dict],
    photo_file_id: Optional[str],
    message_id: Optional[int],
    *,
    force_prices: bool = False,
) -> int:
    if not products:
        return 0
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    prices_clause = (
        "prices_json=excluded.prices_json"
        if force_prices
        else "prices_json=COALESCE(excluded.prices_json, catalog_products.prices_json)"
    )
    count = 0
    for p in products:
        c.execute(
            f"""INSERT INTO catalog_products
               (id, slug, name, description, in_stock, prices_json, photo_file_id, source_message_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 in_stock=excluded.in_stock,
                 {prices_clause},
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


def _fetch_newest_source_posts(limit: int) -> list[tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT chat_id, message_id, text, photo_file_id
           FROM catalog_source_posts
           ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC
           LIMIT ?""",
        (limit,),
    )
    rows = list(reversed(c.fetchall()))
    conn.close()
    return rows


def _recent_catalog_message_ids(lookback: int) -> set[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT message_id, text
           FROM catalog_source_posts
           WHERE message_id IS NOT NULL
           ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC"""
    )
    rows = c.fetchall()
    conn.close()

    ids: list[int] = []
    for message_id, text in rows:
        if parse_catalog_text(text):
            ids.append(message_id)
        if len(ids) >= lookback:
            break
    return set(ids)


def apply_recent_catalog_availability(lookback: int) -> int:
    """Keep in stock only products tied to a recent catalog card post."""
    recent_ids = _recent_catalog_message_ids(lookback)
    if not recent_ids:
        return 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" * len(recent_ids))
    c.execute(
        f"""UPDATE catalog_products
            SET in_stock = 0
            WHERE in_stock = 1
              AND source_message_id IS NOT NULL
              AND source_message_id NOT IN ({placeholders})""",
        tuple(recent_ids),
    )
    hidden = c.rowcount
    conn.commit()
    conn.close()
    return hidden


def prune_source_posts(keep: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM catalog_source_posts")
    total = c.fetchone()[0]
    if total <= keep:
        conn.close()
        return 0
    c.execute(
        """DELETE FROM catalog_source_posts
           WHERE id NOT IN (
             SELECT id FROM catalog_source_posts
             ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC
             LIMIT ?
           )""",
        (keep,),
    )
    removed = c.rowcount
    conn.commit()
    conn.close()
    mark_orphan_products_out_of_stock()
    return removed


def mark_orphan_products_out_of_stock() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """UPDATE catalog_products
           SET in_stock = 0
           WHERE in_stock = 1
             AND source_message_id IS NOT NULL
             AND source_message_id NOT IN (
               SELECT message_id FROM catalog_source_posts WHERE message_id IS NOT NULL
             )"""
    )
    count = c.rowcount
    conn.commit()
    conn.close()
    return count


def get_source_post_by_message_id(message_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT chat_id, message_id, text, photo_file_id, posted_at
           FROM catalog_source_posts WHERE message_id = ?""",
        (message_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "chat_id": row[0],
        "message_id": row[1],
        "text": row[2],
        "photo_file_id": row[3],
        "posted_at": row[4],
    }


def find_newest_price_post() -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT chat_id, message_id, text, photo_file_id, posted_at
           FROM catalog_source_posts
           ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC"""
    )
    rows = c.fetchall()
    conn.close()
    for row in rows:
        text = row[2]
        has_photo = bool(row[3])
        if is_price_post(text, has_photo=has_photo):
            return {
                "chat_id": row[0],
                "message_id": row[1],
                "text": row[2],
                "photo_file_id": row[3],
                "posted_at": row[4],
            }
    return None


def resolve_card_for_entry(entry: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Resolve product card by t.me/c/… message id, falling back to slug search."""
    slug = entry.get("slug") or ""
    card_message_id = entry.get("card_message_id")
    if card_message_id:
        card = get_source_post_by_message_id(card_message_id)
        if card:
            return card, None
        fallback = find_card_post_for_slug(slug)
        if fallback:
            return fallback, f"Card message {card_message_id} not in cache; matched slug {slug}."
        return None, f"Card message {card_message_id} not in cache for {slug}."

    fallback = find_card_post_for_slug(slug)
    if fallback:
        return fallback, f"No t.me/c/… link for {entry.get('name') or slug}; matched by slug."
    return None, f"No t.me/c/… link for {entry.get('name') or slug}."


def ensure_catalog_synced(limit: Optional[int] = None) -> dict:
    """Run full catalog sync when the shop is empty but cached channel posts exist."""
    post_limit = limit if limit is not None else getattr(config, "CATALOG_SYNC_POST_LIMIT", 60)
    available = catalog_stats()[1]
    if available > 0:
        return {"ok": True, "skipped": True, "shop_available": available}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM catalog_source_posts")
    cached_posts = c.fetchone()[0]
    conn.close()
    if cached_posts == 0:
        return {"ok": False, "skipped": True, "reason": "no_cached_posts", "shop_available": 0}

    return sync_catalog_full(limit=post_limit)


def find_card_post_for_slug(slug: str) -> Optional[dict]:
    lookback = getattr(config, "CATALOG_ACTIVE_CARD_LOOKBACK", 20)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT chat_id, message_id, text, photo_file_id, posted_at
           FROM catalog_source_posts
           WHERE photo_file_id IS NOT NULL
           ORDER BY COALESCE(posted_at, saved_at) DESC, id DESC"""
    )
    rows = c.fetchall()
    conn.close()
    cards_seen = 0
    for row in rows:
        products = parse_catalog_text(row[2])
        if not products:
            continue
        cards_seen += 1
        if cards_seen > lookback:
            break
        for product in products:
            if _slug_matches(slug, product["slug"]):
                return {
                    "chat_id": row[0],
                    "message_id": row[1],
                    "text": row[2],
                    "photo_file_id": row[3],
                    "posted_at": row[4],
                    "product": product,
                }
    return None


def _product_from_card(slug: str, card: dict) -> Optional[dict]:
    products = parse_catalog_text(card["text"])
    for product in products:
        if _slug_matches(slug, product["slug"]):
            return product
    cached = card.get("product")
    if cached and _slug_matches(slug, cached["slug"]):
        return cached
    return None


def _refresh_cached_posts(limit: int) -> int:
    rows = _fetch_newest_source_posts(limit)
    scanned = 0
    for _chat_id, message_id, text, photo_file_id in rows:
        scanned += 1
        sync_from_text(text=text, photo_file_id=photo_file_id, message_id=message_id)
        sync_price_post(text=text, message_id=message_id)
    return scanned


def _replace_price_overrides_from_post(price_message_id: int, entries: list[dict]) -> int:
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM catalog_price_overrides")
    count = 0
    for entry in entries:
        c.execute(
            """INSERT INTO catalog_price_overrides (slug, name, prices_json, source_message_id, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                entry["slug"],
                entry["name"],
                json.dumps(entry["prices"]),
                price_message_id,
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def sync_catalog_full(limit: Optional[int] = None) -> dict:
    """
    Full shop sync for scheduled agents:
    1) Re-parse newest cached channel posts
    2) Use newest text-only price post (AVAILABLE list) for prices + assortment
    3) Follow t.me/c/... links to product cards for description, photo, Available/Unavailable
    """
    post_limit = limit if limit is not None else getattr(config, "CATALOG_SYNC_POST_LIMIT", 60)
    result = {
        "ok": False,
        "cache_posts_scanned": 0,
        "price_message_id": None,
        "price_items": 0,
        "cards_linked": 0,
        "cards_missing": 0,
        "shop_available": 0,
        "total_products": 0,
        "errors": [],
    }

    result["cache_posts_scanned"] = _refresh_cached_posts(post_limit)
    price_post = find_newest_price_post()
    if not price_post:
        result["errors"].append("No price post found in cache (text-only AVAILABLE post).")
        prune_source_posts(post_limit)
        total, available = catalog_stats()
        result["total_products"] = total
        result["shop_available"] = available
        return result

    entries = parse_price_post_entries_with_links(price_post["text"])
    if not entries:
        result["errors"].append(f"Could not parse price post (message {price_post['message_id']}).")
        prune_source_posts(post_limit)
        total, available = catalog_stats()
        result["total_products"] = total
        result["shop_available"] = available
        return result

    result["price_message_id"] = price_post["message_id"]
    result["price_items"] = len(entries)
    _replace_price_overrides_from_post(price_post["message_id"], entries)

    listed_slugs: set[str] = set()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE catalog_products SET in_stock = 0")
    conn.commit()
    conn.close()

    for entry in entries:
        slug = entry["slug"]
        listed_slugs.add(slug)
        card, card_error = resolve_card_for_entry(entry)
        if not card:
            result["cards_missing"] += 1
            if card_error:
                result["errors"].append(card_error)
            continue
        if card_error:
            result["errors"].append(card_error)

        product = _product_from_card(slug, card)
        if not product:
            result["cards_missing"] += 1
            result["errors"].append(
                f"Could not parse card message {card.get('message_id')} for {slug}."
            )
            continue

        result["cards_linked"] += 1
        in_stock = bool(product.get("in_stock"))

        record = {
            "id": product["id"],
            "slug": slug,
            "name": product.get("name") or entry["name"],
            "description": product.get("description") or entry["name"],
            "in_stock": in_stock,
            "prices": entry["prices"],
        }
        upsert_products(
            [record],
            photo_file_id=card.get("photo_file_id"),
            message_id=card.get("message_id"),
            force_prices=True,
        )

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if listed_slugs:
        placeholders = ",".join("?" * len(listed_slugs))
        c.execute(
            f"UPDATE catalog_products SET in_stock = 0 WHERE slug NOT IN ({placeholders})",
            tuple(listed_slugs),
        )
    conn.commit()
    conn.close()

    mark_orphan_products_out_of_stock()
    prune_source_posts(post_limit)

    total, available = catalog_stats()
    result["total_products"] = total
    result["shop_available"] = available
    result["ok"] = True
    return result


def sync_last_source_posts(limit: int = 30) -> tuple[int, int, int]:
    """Backward-compatible wrapper around full catalog sync."""
    result = sync_catalog_full(limit)
    return (
        result.get("cache_posts_scanned", 0),
        result.get("price_items", 0),
        result.get("price_items", 0),
    )


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


def _slug_matches(product_slug: str, override_slug: str) -> bool:
    if product_slug == override_slug:
        return True
    if product_slug.startswith(override_slug + "_") or override_slug.startswith(product_slug + "_"):
        return True
    if product_slug in override_slug or override_slug in product_slug:
        return True
    return False


def _get_price_for_slug(slug: str, parsed_prices: Optional[dict]) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT prices_json FROM catalog_price_overrides WHERE slug = ?", (slug,))
        row = c.fetchone()
        if row and row[0]:
            try:
                raw = json.loads(row[0])
                return {int(k): float(v) for k, v in raw.items()}
            except Exception:
                pass
        c.execute("SELECT slug, prices_json FROM catalog_price_overrides")
        for override_slug, prices_json in c.fetchall():
            if not _slug_matches(slug, override_slug):
                continue
            try:
                raw = json.loads(prices_json)
                return {int(k): float(v) for k, v in raw.items()}
            except Exception:
                continue
    finally:
        conn.close()
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
