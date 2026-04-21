"""ShippingCalculator behaviour: default, interface, settings-based lookup."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cart.shipping import (
    DefaultShippingCalculator,
    ShippingCalculator,
    get_shipping_calculator,
)


class CustomShippingCalculator(ShippingCalculator):
    """Module-level test double referenced by dotted path in settings."""

    def calculate(self, cart):
        return Decimal("15.00")

    def get_options(self, cart):
        return [
            {"id": "express", "name": "Express Shipping", "price": Decimal("25.00")},
            {"id": "standard", "name": "Standard Shipping", "price": Decimal("10.00")},
        ]


def _mock_cart(summary=Decimal("100.00")):
    cart = MagicMock()
    cart.summary.return_value = summary
    return cart


def test_default_shipping_calculator_returns_zero():
    assert DefaultShippingCalculator().calculate(_mock_cart()) == Decimal("0.00")


def test_default_shipping_options_returns_single_free_option():
    options = DefaultShippingCalculator().get_options(_mock_cart())

    assert len(options) == 1
    assert options[0]["id"] == "free"
    assert options[0]["name"] == "Free Shipping"
    assert str(options[0]["price"]) == "0.00"


def test_get_shipping_calculator_returns_default_when_setting_unset():
    assert isinstance(get_shipping_calculator(), DefaultShippingCalculator)


@pytest.mark.django_db
def test_get_shipping_calculator_loads_custom_class_from_settings(settings):
    settings.CART_SHIPPING_CALCULATOR = "tests.test_shipping.CustomShippingCalculator"

    calculator = get_shipping_calculator()

    assert isinstance(calculator, CustomShippingCalculator)
    assert calculator.calculate(_mock_cart()) == Decimal("15.00")
    assert len(calculator.get_options(_mock_cart())) == 2


def test_custom_shipping_calculator_subclass_is_usable_inline():
    class InlineShipping(ShippingCalculator):
        def calculate(self, cart):
            return Decimal("5.99")

        def get_options(self, cart):
            return [{"id": "flat", "name": "Flat", "price": Decimal("5.99")}]

    calc = InlineShipping()
    assert calc.calculate(_mock_cart()) == Decimal("5.99")
    assert len(calc.get_options(_mock_cart())) == 1


@pytest.mark.django_db
def test_get_shipping_calculator_warns_and_falls_back_when_class_path_is_bad(settings):
    """P2 regression: misconfigured ``CART_SHIPPING_CALCULATOR`` used
    to silently collapse to the default zero-cost calculator — a typo
    produced "free shipping" without a log entry. The factory now
    emits a :class:`RuntimeWarning` naming the setting before falling
    back to the default."""
    settings.CART_SHIPPING_CALCULATOR = "nonexistent.module.FakeShipping"

    with pytest.warns(RuntimeWarning, match="CART_SHIPPING_CALCULATOR"):
        calculator = get_shipping_calculator()

    assert isinstance(calculator, DefaultShippingCalculator)
