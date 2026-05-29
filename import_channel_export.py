"""Import Telegram channel export JSON into Streetrader catalog DB.

Usage:
  python import_channel_export.py --json /path/to/result.json --start-from "Grape Kush"
"""
import argparse
import json
from pathlib import Path

import catalog_store


def _flatten_text(raw_text) -> str:
    if isinstance(raw_text, str):
        return raw_text
    if isinstance(raw_text, list):
        chunks = []
        for part in raw_text:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict):
                chunks.append(str(part.get("text", "")))
        return "".join(chunks)
    return ""


def import_export(json_path: Path, start_from: str) -> tuple[int, int]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    messages = payload.get("messages", [])
    start_idx = 0
    marker = start_from.lower().strip()

    for idx, msg in enumerate(messages):
        text = _flatten_text(msg.get("text", ""))
        if marker and marker in text.lower():
            start_idx = idx
            break

    scanned = 0
    imported = 0
    for msg in messages[start_idx:]:
        text = _flatten_text(msg.get("text", "")).strip()
        if not text:
            continue
        scanned += 1
        # import only posts that include an availability marker
        if "❇️ Available" not in text and "❌ Unavailable" not in text and "❌ Unvailable" not in text:
            continue
        imported += catalog_store.sync_from_text(
            text=text,
            photo_file_id=None,
            message_id=msg.get("id"),
        )
    return scanned, imported


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, help="Path to Telegram export result.json")
    parser.add_argument(
        "--start-from",
        default="Grape Kush",
        help="Import starts from first message that contains this text",
    )
    args = parser.parse_args()

    json_path = Path(args.json).expanduser().resolve()
    if not json_path.exists():
        raise SystemExit(f"JSON file not found: {json_path}")

    catalog_store.init_catalog_db()
    scanned, imported = import_export(json_path, args.start_from)
    total, available = catalog_store.catalog_stats()
    print(f"Scanned messages: {scanned}")
    print(f"Imported products: {imported}")
    print(f"Catalog total: {total}, available: {available}")


if __name__ == "__main__":
    main()
