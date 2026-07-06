"""Smoke tests for bot UI helpers (run: python tests_bot_ui.py)."""
import ast
import sys
from pathlib import Path

import bot
from catalog_parser import is_price_post, parse_price_post_entries_with_links


def _button_labels(markup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def test_start_menu_catalog_and_cart():
    for is_admin in (False, True):
        labels = _button_labels(bot.build_main_menu_keyboard(is_admin))
        assert "Shop" in labels
        assert "Cart" in labels
        assert "Refer a Friend" not in labels
        if is_admin:
            assert "Admin Panel" in labels
        else:
            assert "Admin Panel" not in labels
    print("OK main menu: Shop + Cart (payment extras hidden)")


def test_cart_keyboard_is_list_and_remove_only():
    user_data = {
        "cart_items": [
            {"product_name": "🦜 TROPICAL BLUES", "qty": 5, "line_price": 45.0},
            {"product_name": "Plain Item", "qty": 1, "line_price": 10.0},
        ]
    }
    remove_labels = _button_labels(bot.build_cart_remove_keyboard(user_data))
    assert remove_labels == ["1) 🦜=❌", "2)=❌"]

    footer_labels = _button_labels(bot.build_cart_footer_keyboard(user_data))
    assert footer_labels == ["Shop", "Main Menu"]
    assert "Checkout" not in footer_labels
    assert "Apply Discount Code" not in footer_labels
    print("OK cart: remove buttons + Shop/Main Menu footer")


def test_empty_cart_restore():
    labels = _button_labels(bot.build_empty_cart_keyboard())
    assert labels == ["Reload Cart", "Shop"]
    print("OK empty cart: Reload Cart + Shop")


def test_payments_disabled_by_default():
    assert bot.payments_enabled() is False
    source = Path("bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "checkout_handler"
    )
    fn_src = ast.get_source_segment(source, fn) or ""
    assert "Payment is not connected yet" in fn_src
    print("OK checkout: payment stubbed")


def test_payment_handlers_gated():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "if payments_enabled():" in source
    assert "PreCheckoutQueryHandler(precheckout_handler)" in source
    print("OK bot.py: payment handlers only register when ENABLE_PAYMENTS")


def test_cart_message_lists_items():
    user_data = {
        "cart_items": [
            {"product_name": "Item A", "qty": 5, "line_price": 45.0},
        ]
    }
    text = bot.build_cart_items_message(user_data)
    assert "Cart:" in text
    assert "Item A" in text
    assert "5g = $45" in text
    assert "You can delete wrong items:" in text
    print("OK cart message lists selected items")


def test_price_post_parses_card_links():
    text = """AVAILABLE

🦜 TROPICAL BLUES
5g = 45
10g = 80
https://t.me/c/1234567890/42
"""
    assert is_price_post(text)
    entries = parse_price_post_entries_with_links(text)
    assert len(entries) == 1
    assert entries[0]["card_message_id"] == 42
    assert entries[0]["prices"] == {5: 45.0, 10: 80.0}
    print("OK catalog: price post links to product card")


def test_validate_runtime_config_rejects_placeholder_token():
    old = bot.config.TELEGRAM_BOT_TOKEN
    try:
        bot.config.TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
        try:
            bot.validate_runtime_config()
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "TELEGRAM_BOT_TOKEN" in str(exc)
    finally:
        bot.config.TELEGRAM_BOT_TOKEN = old
    print("OK startup validation rejects placeholder token")


def main() -> int:
    tests = [
        test_start_menu_catalog_and_cart,
        test_cart_keyboard_is_list_and_remove_only,
        test_empty_cart_restore,
        test_payments_disabled_by_default,
        test_payment_handlers_gated,
        test_cart_message_lists_items,
        test_price_post_parses_card_links,
        test_validate_runtime_config_rejects_placeholder_token,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}", file=sys.stderr)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
