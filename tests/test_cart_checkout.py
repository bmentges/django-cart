"""Cart.can_checkout() — gate logic for whether the cart is ready to check out.

This file is seeded in Phase 4 with the can_checkout cases migrated from
test_v300.py. Phase 5 will add the cart.checkout() tests currently living
in tests/test_cart.py::CartCheckoutTest / CartCheckoutEdgeCaseTest.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


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
