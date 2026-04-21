"""Cart checkout: checkout() mark, can_checkout() gates, cart lifecycle after checkout."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# can_checkout() gates
# --------------------------------------------------------------------------- #


def test_can_checkout_rejects_empty_cart(cart):
    can_checkout, message = cart.can_checkout()

    assert can_checkout is False
    assert message == "Cart is empty."


def test_can_checkout_accepts_cart_with_items(cart, product):
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)

    can_checkout, message = cart.can_checkout()

    assert can_checkout is True
    assert message == ""


def test_can_checkout_rejects_cart_below_min_order_amount_setting(
    cart, product, settings
):
    settings.CART_MIN_ORDER_AMOUNT = Decimal("500.00")
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)

    can_checkout, message = cart.can_checkout()

    assert can_checkout is False
    assert "500.00" in message


def test_can_checkout_accepts_cart_at_or_above_min_order_amount(
    cart, product, settings
):
    """Covers the `min_amount is not None AND summary >= min_amount`
    branch in can_checkout — previously unreachable through the suite
    (only the below-minimum path was exercised)."""
    settings.CART_MIN_ORDER_AMOUNT = Decimal("100.00")
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)

    can_checkout, message = cart.can_checkout()

    assert can_checkout is True
    assert message == ""


# --------------------------------------------------------------------------- #
# checkout() — marks the DB record
# --------------------------------------------------------------------------- #


def test_checkout_marks_the_cart_checked_out(cart, product):
    cart.add(product, Decimal("1.00"))

    cart.checkout()

    cart.cart.refresh_from_db()
    assert cart.cart.checked_out is True


def test_checkout_is_allowed_on_an_empty_cart_by_design(cart):
    """Until P1-2 lands in 3.1.0, Cart.checkout() is lax by design —
    it does not enforce can_checkout(). This test locks in the current
    contract so P1-2's change surfaces clearly on diff."""
    cart.checkout()

    cart.cart.refresh_from_db()
    assert cart.cart.checked_out is True


# --------------------------------------------------------------------------- #
# Lifecycle — post-checkout behaviour
# --------------------------------------------------------------------------- #


def test_a_fresh_request_after_checkout_yields_a_new_cart(cart, rf_request):
    cart.checkout()

    fresh = Cart(rf_request)

    assert fresh.cart.pk != cart.cart.pk


def test_clear_followed_by_checkout_is_a_clean_lifecycle(cart, product):
    cart.add(product, Decimal("5.00"), quantity=1)

    cart.clear()
    assert cart.is_empty() is True

    cart.add(product, Decimal("5.00"), quantity=1)
    cart.checkout()

    cart.cart.refresh_from_db()
    assert cart.cart.checked_out is True
