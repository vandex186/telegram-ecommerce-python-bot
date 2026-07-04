"""Smoke tests for bot UI helpers (run: python tests_bot_ui.py)."""
import ast
import sys
from pathlib import Path

import bot


def _button_labels(markup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def test_start_menu_has_referral():
    for is_admin in (False, True):
        labels = _button_labels(bot.build_main_menu_keyboard(is_admin))
        assert "Refer a Friend" in labels
        assert "Apply Discount Code" not in labels
        if is_admin:
            assert "Admin Panel" in labels
    print("OK main menu: Refer a Friend present")


def test_cart_keyboard_has_discount():
    delivery_labels = _button_labels(bot.build_cart_delivery_keyboard({}))
    assert "Apply Discount Code" in delivery_labels
    assert "Checkout" in delivery_labels
    assert "Set Location" in delivery_labels
    assert "Set Phone" in delivery_labels
    print("OK cart: Apply Discount Code present")


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


def test_admin_panel_has_add_discount_button():
    source = Path("bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "admin_panel_handler"
    )
    fn_src = ast.get_source_segment(source, fn) or ""
    assert "Add Discount Code" in fn_src
    assert "admin_discount" in fn_src
    assert "Refer a Friend" in source
    print("OK admin panel: Add Discount Code button present")


def test_admin_commands_has_addcode_menu():
    names = [c.command for c in bot.ADMIN_BOT_COMMANDS]
    assert "addcode" in names
    print("OK admin command menu: addcode shortcut present")


def test_telegram_pay_handlers_registered():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "PreCheckoutQueryHandler(precheckout_handler)" in source
    assert "filters.SUCCESSFUL_PAYMENT" in source
    assert "send_invoice" in source
    print("OK bot.py: Telegram Pay handlers registered")


def test_referral_and_discount_helpers():
    assert bot.generate_referral_code(42) == "REF42"
    assert bot.get_referrer_from_code("REF42") == 42
    assert bot.get_referrer_from_code("SUMMER20") is None

    user_data = {
        "cart_items": [{"line_price": 100.0}],
        "cart_referred_by": 99,
    }
    code, percent = bot.get_effective_discount(user_data)
    assert percent == 10
    assert code == "REF99"
    assert bot.get_cart_total(user_data) == 90.0

    bot.apply_discount_to_cart(user_data, "SUMMER20", 20)
    assert user_data["cart_discount_percent"] == 20
    assert user_data["cart_price"] == 80.0
    print("OK referral/discount pricing helpers")


def main() -> int:
    tests = [
        test_start_menu_has_referral,
        test_cart_keyboard_has_discount,
        test_empty_cart_restore,
        test_checkout_location_keyboard,
        test_checkout_handler_sends_new_message,
        test_oxapay_helpers_present,
        test_telegram_pay_handlers_registered,
        test_admin_panel_has_add_discount_button,
        test_admin_commands_has_addcode_menu,
        test_referral_and_discount_helpers,
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
