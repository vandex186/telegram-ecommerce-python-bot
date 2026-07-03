"""Smoke tests for bot UI helpers (run: python tests_bot_ui.py)."""
import ast
import sys
from pathlib import Path

import bot


def _button_labels(markup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def test_start_menu_no_referral():
    for is_admin in (False, True):
        labels = _button_labels(bot.build_main_menu_keyboard(is_admin))
        assert "Refer a Friend" not in labels
        assert "Apply Discount Code" not in labels
        if is_admin:
            assert "Admin Panel" in labels
    print("OK main menu: no Refer a Friend / discount buttons")


def test_cart_keyboard_no_discount():
    delivery_labels = _button_labels(bot.build_cart_delivery_keyboard({}))
    assert "Apply Discount Code" not in delivery_labels
    assert "Checkout" in delivery_labels
    assert "Set Location" in delivery_labels
    assert "Set Phone" in delivery_labels
    print("OK cart: no Apply Discount Code")


def test_empty_cart_restore():
    labels = _button_labels(bot.build_empty_cart_keyboard())
    assert labels == ["Reload Cart", "Shop"]
    print("OK empty cart: Reload Cart + Shop")


def test_checkout_location_keyboard():
    labels = _button_labels(bot.build_checkout_location_keyboard())
    assert labels == ["Set Location", "Back to Cart"]
    print("OK checkout prompt: Set Location + Back to Cart")


def test_checkout_handler_sends_new_message():
    source = Path("bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "checkout_handler"
    )
    fn_src = ast.get_source_segment(source, fn) or ""
    assert "edit_message_text" not in fn_src
    assert "chat.send_message" in fn_src
    assert "start_telegram_payment" in fn_src
    assert "start_crypto_payment" in fn_src
    print("OK checkout_handler: payment method selection at checkout")


def test_oxapay_helpers_present():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "api.oxapay.com/v1/payment/invoice" in source
    assert "check_crypto_" in source
    assert "Pay with Crypto" in source
    print("OK bot.py: OxaPay crypto payment integrated")


def test_admin_panel_no_add_discount_button():
    source = Path("bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "admin_panel_handler"
    )
    fn_src = ast.get_source_segment(source, fn) or ""
    assert "Add Discount Code" not in fn_src
    assert "admin_discount" not in fn_src
    assert "Refer a Friend" not in source
    print("OK admin panel: no Add Discount Code button")


def test_admin_commands_no_addcode_menu():
    names = [c.command for c in bot.ADMIN_BOT_COMMANDS]
    assert "addcode" not in names
    print("OK admin command menu: no addcode shortcut")


def test_telegram_pay_handlers_registered():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "PreCheckoutQueryHandler(precheckout_handler)" in source
    assert "filters.SUCCESSFUL_PAYMENT" in source
    assert "send_invoice" in source
    print("OK bot.py: Telegram Pay handlers registered")


def main() -> int:
    tests = [
        test_start_menu_no_referral,
        test_cart_keyboard_no_discount,
        test_empty_cart_restore,
        test_checkout_location_keyboard,
        test_checkout_handler_sends_new_message,
        test_oxapay_helpers_present,
        test_telegram_pay_handlers_registered,
        test_admin_panel_no_add_discount_button,
        test_admin_commands_no_addcode_menu,
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
