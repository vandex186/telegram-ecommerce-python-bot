#!/usr/bin/env python3
"""Full catalog sync for cron / Cursor agent (no Telegram UI).

Uses cached channel posts in orders.db (bot must have received channel updates).

Usage:
  python sync_catalog_cli.py
  python sync_catalog_cli.py --limit 100
"""
import argparse
import json
import sys

import catalog_store
import config


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync shop from latest price post + product cards")
    default_limit = getattr(config, "CATALOG_SYNC_POST_LIMIT", 100)
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help="Newest cached channel posts to refresh",
    )
    args = parser.parse_args()

    catalog_store.init_catalog_db()
    result = catalog_store.sync_catalog_full(limit=args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
