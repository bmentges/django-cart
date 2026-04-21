"""TaxCalculator behaviour: default, interface, settings-based lookup."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cart.tax import DefaultTaxCalculator, TaxCalculator, get_tax_calculator


class CustomTaxCalculator(TaxCalculator):
    """Module-level test double referenced by dotted path in settings."""

    def calculate(self, cart):
        return Decimal("10.00")


def _mock_cart(summary=Decimal("100.00")):
    cart = MagicMock()
    cart.summary.return_value = summary
    return cart


def test_default_tax_calculator_returns_zero():
    result = DefaultTaxCalculator().calculate(_mock_cart())

    assert result == Decimal("0.00")


def test_get_tax_calculator_returns_default_when_setting_unset():
    assert isinstance(get_tax_calculator(), DefaultTaxCalculator)


@pytest.mark.django_db
def test_get_tax_calculator_loads_custom_class_from_settings(settings):
    settings.CART_TAX_CALCULATOR = "tests.test_tax.CustomTaxCalculator"

    calculator = get_tax_calculator()

    assert isinstance(calculator, CustomTaxCalculator)
    assert calculator.calculate(_mock_cart()) == Decimal("10.00")


def test_custom_tax_calculator_subclass_is_usable_inline():
    class InlineTax(TaxCalculator):
        def calculate(self, cart):
            return Decimal("25.50")

    assert InlineTax().calculate(_mock_cart()) == Decimal("25.50")


@pytest.mark.django_db
def test_get_tax_calculator_warns_and_falls_back_when_class_path_is_bad(settings):
    """P2 regression: misconfigured ``CART_TAX_CALCULATOR`` used to
    silently collapse to the default zero-tax calculator — a typo in
    ``settings.py`` produced "tax is always 0" at runtime with no log
    entry. The factory now emits a :class:`RuntimeWarning` naming the
    setting, the bad path, and the underlying exception before falling
    back to the default."""
    settings.CART_TAX_CALCULATOR = "nonexistent.module.FakeTax"

    with pytest.warns(RuntimeWarning, match="CART_TAX_CALCULATOR"):
        calculator = get_tax_calculator()

    assert isinstance(calculator, DefaultTaxCalculator)
