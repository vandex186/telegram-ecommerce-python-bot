"""Parse product blocks and price posts from Telegram channel messages."""
import hashlib
import re
import unicodedata
from typing import Optional

AVAILABILITY_RE = re.compile(r"(❇️ Available|❌ Unavailable|❌ Unvailable)\s*$", re.MULTILINE)
META_PREFIXES = ("🧪", "🧬", "🪬", "🥳", "💫", "- ")
EMOJI_TITLE_RE = re.compile(
    r"^[\U0001F300-\U0001FAFF🛞🍭✨🧪🌸💫🪬🥳🔥💎🌿❇️❌⭐️🎡🛍🏀🧁🕋👻🍰🎀].+",
    re.UNICODE,
)
EXPLICIT_PRICE_RE = re.compile(
    r"(?i)(\d{1,3})\s*(?:g|gr|gram|grams)\s*=\s*[£$€]?\s*(\d+(?:[.,]\d+)?)\s*[£$€]?"
)
SINGLE_PRICE_RE = re.compile(r"(?im)(?:price|cost)?\s*[:=\-]?\s*[£$€]?\s*(\d+(?:[.,]\d+)?)\s*[£$€]?")
TAG_RE = re.compile(r"<[^>]+>")
CHANNEL_POST_LINK_RE = re.compile(r"https://t\.me/c/(\d+)/(\d+)")


def _slugify(name: str) -> str:
    clean = _plain(name)
    clean = unicodedata.normalize("NFKC", clean)
    clean = re.sub(r"^[\U0001F300-\U0001FAFF🛞🍭✨🧪🌸💫🪬🥳🔥💎🌿❇️❌⭐️🎡🛍🏀🧁🕋👻🍰🎀\s]+", "", clean).strip()
    clean = re.sub(r"\s+\d+\s*(?:g|gr)\s*=\s*\d+.*$", "", clean, flags=re.I)
    clean = re.sub(r"\s*=\s*\d+(?:[.,]\d+)?\s*[£$€]?\s*$", "", clean)
    clean = re.sub(r"\s*[•\-]\s*\d{1,3}%\s*$", "", clean)
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", clean.lower()).strip("_")
    return clean or hashlib.md5(name.encode()).hexdigest()[:12]


def _stable_id(slug: str) -> int:
    return int(hashlib.md5(slug.encode()).hexdigest()[:8], 16) % 1_000_000_000


def _plain(text: str) -> str:
    return TAG_RE.sub("", text or "").strip()


def _extract_prices(block_text: str) -> Optional[dict]:
    prices = {}
    for qty_s, price_s in EXPLICIT_PRICE_RE.findall(block_text):
        try:
            qty = int(qty_s)
            price = float(price_s.replace(",", "."))
        except ValueError:
            continue
        if qty > 0 and price > 0:
            prices[qty] = price

    if prices:
        return dict(sorted(prices.items(), key=lambda item: item[0]))

    single = SINGLE_PRICE_RE.search(block_text)
    if single:
        try:
            return {1: float(single.group(1).replace(",", "."))}
        except ValueError:
            return None
    return None


def _is_price_title_line(line: str) -> bool:
    if not line or not re.search(r"[A-Za-z]", line):
        return False
    if AVAILABILITY_RE.search(line):
        return False
    if line.startswith(META_PREFIXES):
        return False
    if EMOJI_TITLE_RE.match(line):
        return True
    # "Grape Kush • 15%" without leading emoji
    if re.search(r"[•\-]\s*\d{1,3}\s*%", line):
        return True
    return False


def _pick_prices_for_title(title_line: str, next_line: str) -> Optional[dict]:
    next_prices = _extract_prices(next_line) if next_line and "=" in next_line else None
    title_prices = _extract_prices(title_line)
    if next_prices and len(next_prices) >= 2:
        return next_prices
    if next_prices:
        return next_prices
    if title_prices:
        return title_prices
    return None


def parse_catalog_text(text: str) -> list[dict]:
    if not text or not text.strip():
        return []

    text = text.replace("❌ Unvailable", "❌ Unavailable").strip()
    products = []
    markers = list(AVAILABILITY_RE.finditer(text))
    if not markers:
        return products

    for i, match in enumerate(markers):
        block_start = 0 if i == 0 else markers[i - 1].end()
        block_end = match.end()
        block = text[block_start:block_end].strip()
        in_stock = match.group(1).startswith("❇️")

        raw_lines = [ln.rstrip() for ln in block.split("\n")]
        lines = [_plain(ln) for ln in raw_lines]
        name = None
        for idx, line in enumerate(lines):
            if not line:
                continue
            if line.startswith(META_PREFIXES):
                continue
            if AVAILABILITY_RE.search(line):
                continue
            if EMOJI_TITLE_RE.match(line) or (len(line) < 80 and line.isupper()):
                name = line
                break

        if not name:
            continue

        description_lines = []
        for raw_line in raw_lines:
            if AVAILABILITY_RE.search(_plain(raw_line)):
                break
            description_lines.append(raw_line)
        description = "\n".join(description_lines).rstrip() or name

        slug = _slugify(name)
        parsed_prices = _extract_prices(block)
        products.append(
            {
                "id": _stable_id(slug),
                "slug": slug,
                "name": name,
                "description": description,
                "in_stock": in_stock,
                "prices": parsed_prices,
            }
        )

    return products


def parse_price_post(text: str) -> Optional[dict]:
    if not text or not text.strip():
        return None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 1:
        return None

    title_line = _plain(lines[0])
    if not title_line:
        return None

    prices = None
    if len(lines) >= 2:
        prices = _pick_prices_for_title(title_line, _plain(lines[1]))
    if not prices:
        prices = _extract_prices(text)
    if not prices:
        return None

    slug = _slugify(title_line)
    return {"slug": slug, "name": title_line, "prices": prices}


def is_price_post(text: str, has_photo: bool = False) -> bool:
    """Text-only channel post listing prices (often titled AVAILABLE)."""
    if has_photo or not text or not text.strip():
        return False
    entries = parse_price_post_entries(text)
    if len(entries) >= 2:
        return True
    plain = _plain(text).upper()
    if "AVAILABLE" in plain and entries:
        return True
    return bool(entries) and bool(CHANNEL_POST_LINK_RE.search(text))


def parse_price_post_entries_with_links(text: str) -> list[dict]:
    """Multi-item price post; attaches card_message_id from t.me/c/... links in order."""
    entries = parse_price_post_entries(text)
    link_ids = [int(match.group(2)) for match in CHANNEL_POST_LINK_RE.finditer(text)]
    for index, entry in enumerate(entries):
        if index < len(link_ids):
            entry["card_message_id"] = link_ids[index]
    return entries


def parse_price_post_entries(text: str) -> list[dict]:
    """Parse multi-item price posts, e.g. several strains in one message."""
    if not text or not text.strip():
        return []

    lines = [_plain(ln) for ln in text.splitlines()]
    entries = []
    skip_until = 0
    for idx, raw in enumerate(lines):
        if idx < skip_until:
            continue
        title = raw.strip()
        if not title:
            continue
        if not _is_price_title_line(title):
            continue

        next_line = ""
        next_idx = None
        for j in range(idx + 1, len(lines)):
            nxt = lines[j].strip()
            if nxt:
                next_line = nxt
                next_idx = j
                break
        if next_line and AVAILABILITY_RE.search(next_line):
            next_line = ""

        prices = _pick_prices_for_title(title, next_line)
        if not prices:
            continue

        if next_idx is not None and next_line and _extract_prices(next_line):
            skip_until = next_idx + 1

        entries.append({"slug": _slugify(title), "name": title, "prices": prices})
    return entries
