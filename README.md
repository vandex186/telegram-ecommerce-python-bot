# Telegram Ecommerce Bot (Catalog + Cart)

Python Telegram shop bot. **Active features:** catalog cards synced from a **private Telegram channel**, and a **cart** with remove buttons. Payment and other checkout flows are **not connected yet**.

**Repository:** [github.com/wrogg/telegram-ecommerce-python-bot](https://github.com/wrogg/telegram-ecommerce-python-bot)

## Why a fresh GitHub clone used to fail

GitHub only stores code — it does not run the bot. Older `main` also:

1. **Did not ship `config.py`** (it was gitignored), so `import config` crashed after clone.
2. **Expected static product files / `PRODUCTS` in config**, which are not used anymore.
3. **Did not include catalog modules** (`catalog_store.py`, `catalog_parser.py`) on the published tree until this branch is pushed.

This tree fixes that: `config.py` is committed (no secrets), loads `.env`, and the shop reads products from the private channel only.

## Requirements

- Python 3.10+
- Bot token from [@BotFather](https://t.me/BotFather)
- A **private Telegram channel** for the catalog (bot must be **admin**)

## New bot via BotFather

New bot: [@TetraHydroGuild_bot](https://t.me/TetraHydroGuild_bot). Replacing [@streettrader_bot](https://t.me/streettrader_bot)? See **[NEW_BOT_SETUP.md](NEW_BOT_SETUP.md)** (Russian): paste `TELEGRAM_BOT_TOKEN` from @BotFather into `.env` → stop @streettrader_bot → add @TetraHydroGuild_bot as channel admin → `./run.sh`. Template: `.env.newbot.example`.

## Quick start (local)

```bash
git clone https://github.com/wrogg/telegram-ecommerce-python-bot.git
cd telegram-ecommerce-python-bot

# Use the branch that has channel catalog + cart (main)
# git checkout main

cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN, STOCK_CHANNEL_ID, ADMIN_USER_ID

./run.sh
# or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python bot.py
```

Open the bot in Telegram → `/start` → **Shop** / **Cart**.

### Required `.env` variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `STOCK_CHANNEL_ID` | Private channel ID, e.g. `-1001234567890` |
| `ADMIN_USER_ID` | Your numeric Telegram user ID (admin commands) |

Optional: `SUPPORT_HANDLE`, `CURRENCY`, `CATALOG_SYNC_POST_LIMIT`, `CATALOG_ACTIVE_CARD_LOOKBACK`.

Payment-related vars (`ENABLE_PAYMENTS`, OxaPay, Telegram Pay) stay **off** — leave `ENABLE_PAYMENTS=false`.

## Catalog from a private channel

There are **no product files** in the repo. The shop is filled from channel posts.

### Setup

1. Create a **private** channel.
2. Add the bot as **administrator** (needed so the bot receives channel posts).
3. Put the channel ID in `.env` as `STOCK_CHANNEL_ID` (forward a post to [@userinfobot](https://t.me/userinfobot), or check bot logs).
4. Post catalog messages (formats below).
5. While the bot is running, new/edited channel posts are ingested automatically.
6. For the first import, **forward** catalog posts from the channel to the bot in private chat (admin only).
7. Admin: `/sync_catalog` (or `/sync_last_60`) to rebuild the shop from the newest cached posts.

### Product card post (photo + caption)

Caption example:

```text
🦜 TROPICAL BLUES
🧪 THC 22%
🧬 Hybrid

Sweet tropical notes.

❇️ Available
```

- End with `❇️ Available` or `❌ Unavailable` (typo `❌ Unvailable` is accepted).
- Photo is optional but recommended (shown on the shop card).
- Prices can be on the card (`5g = 45`, `10g = 80`) **or** on a separate price list post.

### Price list post (text only, no photo)

Often titled `AVAILABLE`, with one product per block and optional links to cards:

```text
AVAILABLE

🦜 TROPICAL BLUES
5g = 45
10g = 80
https://t.me/c/1234567890/42

🌸 ANOTHER STRAIN
5g = 50
10g = 90
https://t.me/c/1234567890/43
```

- `Ng = price` lines set quantity buttons on cards.
- `1g` in the shop is derived as **5g price / 5** when a 5g price exists.
- `t.me/c/...` links attach each price row to its product card (photo + description + availability).

Only **Available** items appear in **Shop**, as cards with price buttons. Tap a price to add to cart.

### Admin sync commands

| Command | Action |
|---------|--------|
| `/sync_catalog` | Full sync from newest cached posts |
| `/sync_last_30` / `/sync_last_60` | Same, with a fixed cache window |

CLI (cron): ` .venv/bin/python sync_catalog_cli.py --limit 60`

## Cart

- **Cart** shows a numbered list of selected items and the total.
- Inline buttons like `1) 🦜=❌` remove that line item.
- Payment / delivery / discounts are **not connected** yet (footer explains this).

## Project layout

| File | Role |
|------|------|
| `bot.py` | Handlers, shop UI, cart |
| `catalog_parser.py` | Parse channel card + price posts |
| `catalog_store.py` | SQLite catalog cache |
| `config.py` | Loads `.env` (no secrets in git) |
| `.env.example` | Template for secrets |
| `run.sh` | Create venv, install deps, run bot |
| `orders.db` | Local SQLite (created at runtime, not in git) |

## Deploy 24/7

GitHub does not host a running bot. Use Render, Railway, or a VPS — see [DEPLOY.md](DEPLOY.md). Set the same env vars there.

## License

MIT — see [LICENSE](LICENSE).
