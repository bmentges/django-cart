"""Cart methods that integrate with tax/shipping calculators: tax(), shipping(),
shipping_options(), total()."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.models import Discount, DiscountType
from cart.shipping import ShippingCalculator
from cart.tax import TaxCalculator


class TaxCalculator10Percent(TaxCalculator):
    """Module-level test double — 10% of subtotal."""

    def calculate(self, cart):
        return cart.summary() * Decimal("0.10")


class TaxCalculatorTrailingDigits(TaxCalculator):
    """Test double that returns an unrounded four-digit Decimal.

    Exists to prove ``Cart.total()`` collapses long-tail decimals from
    aggregated calculators into 2dp — long-tail noise (e.g. real-world
    compound tax rates) otherwise leaks into display and into any
    downstream system that treats ``total()`` as already-rounded.
    """

    def calculate(self, cart):
        return Decimal("13.3375")


class ShippingCalculatorFlatRate(ShippingCalculator):
    """Module-level test double — $10 flat shipping."""

    def calculate(self, cart):
        return Decimal("10.00")

    def get_options(self, cart):
        return [{"id": "flat", "name": "Flat Rate", "price": Decimal("10.00")}]


pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_worth_200(cart, product):
    cart.add(product, unit_price=Decimal("100.00"), quantity=2)
    return cart


def test_tax_defaults_to_zero(cart_worth_200):
    assert cart_worth_200.tax() == Decimal("0.00")


def test_shipping_defaults_to_zero(cart_worth_200):
    assert cart_worth_200.shipping() == Decimal("0.00")


def test_shipping_options_defaults_to_non_empty_list(cart_worth_200):
    options = cart_worth_200.shipping_options()

    assert isinstance(options, list)
    assert len(options) > 0


def test_total_equals_subtotal_when_no_discount_tax_or_shipping(cart_worth_200):
    assert cart_worth_200.total() == Decimal("200.00")


def test_total_subtracts_applied_discount(cart_worth_200):
    Discount.objects.create(
        code="SAVE10",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    cart_worth_200.apply_discount("SAVE10")

    assert cart_worth_200.total() == Decimal("180.00")


def test_total_adds_custom_tax_when_settings_configured(cart_worth_200, settings):
    settings.CART_TAX_CALCULATOR = "tests.test_cart_tax_shipping.TaxCalculator10Percent"

    assert cart_worth_200.total() == Decimal("220.00")


def test_total_adds_custom_shipping_when_settings_configured(cart_worth_200, settings):
    settings.CART_SHIPPING_CALCULATOR = (
        "tests.test_cart_tax_shipping.ShippingCalculatorFlatRate"
    )

    assert cart_worth_200.total() == Decimal("210.00")


def test_total_is_clamped_to_zero_when_discount_exceeds_subtotal(cart_worth_200):
    Discount.objects.create(
        code="HUGE",
        discount_type=DiscountType.FIXED,
        value=Decimal("500.00"),
    )
    cart_worth_200.apply_discount("HUGE")

    assert cart_worth_200.total() == Decimal("0.00")


def test_total_is_rounded_to_two_decimal_places(cart_worth_200, settings):
    """P2 regression: ``Cart.total()`` used to return the raw sum of
    subtotal − discount + tax + shipping with no explicit quantize, so
    a TaxCalculator returning ``Decimal('13.3375')`` surfaced
    ``Decimal('213.3375')`` from ``total()`` — four decimal places
    bleeding into money fields, confusing downstream display code that
    assumes 2dp. Total must round half-up to ``Decimal('213.34')``.
    """
    settings.CART_TAX_CALCULATOR = (
        "tests.test_cart_tax_shipping.TaxCalculatorTrailingDigits"
    )

    assert cart_worth_200.total() == Decimal("213.34")


def test_total_returns_decimal_quantized_to_2dp_even_without_extras(
    cart_worth_200,
):
    """Even when no tax / shipping / discount is in play, the returned
    Decimal must be quantized — otherwise a downstream ``str(total)``
    might render ``"200"`` on one cart and ``"200.00"`` on another,
    depending on how the subtotal was constructed."""
    total = cart_worth_200.total()

    assert total == Decimal("200.00")
    assert total.as_tuple().exponent == -2
