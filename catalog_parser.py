"""Parse product blocks and price posts from Telegram channel messages."""
import hashlib
import re
from typing import Optional

AVAILABILITY_RE = re.compile(r"(❇️ Available|❌ Unavailable|❌ Unvailable)\s*$", re.MULTILINE)
META_PREFIXES = ("🧪", "🧬", "🪬", "🥳", "💫", "- ")
EMOJI_TITLE_RE = re.compile(
    r"^[\U0001F300-\U0001FAFF🛞🍭✨🧪🌸💫🪬🥳🔥💎🌿❇️❌].+",
    re.UNICODE,
)
EXPLICIT_PRICE_RE = re.compile(
    r"(?im)(\d{1,3})\s*(?:x|pcs?|g|gram|grams)?\s*[:=\-]\s*[£$€]?\s*(\d+(?:[.,]\d+)?)\s*[£$€]?"
)
SINGLE_PRICE_RE = re.compile(r"(?im)(?:price|cost)?\s*[:=\-]?\s*[£$€]\s*(\d+(?:[.,]\d+)?)")
TAG_RE = re.compile(r"<[^>]+>")


def _slugify(name: str) -> str:
    clean = re.sub(r"^[\U0001F300-\U0001FAFF🛞🍭✨🧪🌸💫🪬🥳🔥💎🌿❇️❌\s]+", "", name).strip()
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

        # Keep original line breaks/empty lines from channel post formatting.
        raw_lines = [ln.rstrip() for ln in block.split("\n")]
        lines = [_plain(ln) for ln in raw_lines]
        name = None
        name_idx = 0
        for idx, line in enumerate(lines):
            if not line:
                continue
            if line.startswith(META_PREFIXES):
                continue
            if AVAILABILITY_RE.search(line):
                continue
            if EMOJI_TITLE_RE.match(line) or (len(line) < 80 and line.isupper()):
                name = line
                name_idx = idx
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
    """Parse dedicated price post, e.g.:
    🏀 Orange • 16%
    5g =30$ / 10g =50$
    """
    if not text or not text.strip():
        return None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None

    title_line = _plain(lines[0])
    if not title_line:
        return None

    prices = _extract_prices("\n".join(lines[1:3]))
    if not prices:
        prices = _extract_prices(text)
    if not prices:
        return None

    slug = _slugify(title_line)
    return {"slug": slug, "name": title_line, "prices": prices}


def parse_price_post_entries(text: str) -> list[dict]:
    """Parse multi-item price posts, e.g. several strains in one message."""
    if not text or not text.strip():
        return []

    lines = [_plain(ln) for ln in text.splitlines()]
    entries = []
    for idx, raw in enumerate(lines):
        title = raw.strip()
        if not title:
            continue
        if AVAILABILITY_RE.search(title):
            continue
        if title.startswith(META_PREFIXES):
            continue
        if not EMOJI_TITLE_RE.match(title):
            continue
        # Title should contain letters and should not itself be only a price line.
        if not re.search(r"[A-Za-z]", title):
            continue
        if _extract_prices(title):
            continue

        # Find the nearest non-empty line below as price line.
        next_line = ""
        for j in range(idx + 1, len(lines)):
            nxt = lines[j].strip()
            if nxt:
                next_line = nxt
                break
        if not next_line:
            continue
        if AVAILABILITY_RE.search(next_line):
            continue
        if "=" not in next_line:
            continue
        prices = _extract_prices(next_line)
        if not prices:
            continue
        entries.append({"slug": _slugify(title), "name": title, "prices": prices})
    return entries
