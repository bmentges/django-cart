"""Cart.add / Cart.update validate_price=True path."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import PriceMismatchError


pytestmark = pytest.mark.django_db


@pytest.fixture
def priced_product(product_factory):
    return product_factory(name="PriceValidation", price="19.99")


def test_validate_price_succeeds_when_price_matches(cart, priced_product):
    cart.add(
        priced_product,
        unit_price=Decimal("19.99"),
        quantity=1,
        validate_price=True,
    )

    assert cart.count() == 1


def test_validate_price_raises_when_price_mismatches(cart, priced_product):
    with pytest.raises(PriceMismatchError):
        cart.add(
            priced_product,
            unit_price=Decimal("9.99"),
            quantity=1,
            validate_price=True,
        )


def test_validate_price_false_skips_validation(cart, priced_product):
    cart.add(
        priced_product,
        unit_price=Decimal("0.01"),
        quantity=1,
        validate_price=False,
    )

    assert cart.count() == 1


def test_validate_price_also_applies_to_update(cart, priced_product):
    cart.add(priced_product, Decimal("19.99"), quantity=1)

    with pytest.raises(PriceMismatchError):
        cart.update(
            priced_product,
            quantity=2,
            unit_price=Decimal("1.00"),
            validate_price=True,
        )


def test_validate_price_skips_products_without_price_attribute(cart, product_no_price):
    cart.add(
        product_no_price,
        unit_price=Decimal("10.00"),
        quantity=1,
        validate_price=True,
    )

    assert cart.count() == 1


def test_validate_price_accepts_zero_price_match(cart, product_factory):
    free = product_factory(name="Free", price="0.00")

    cart.add(free, Decimal("0.00"), quantity=1, validate_price=True)

    assert cart.count() == 1


def test_validate_price_blocks_client_side_price_tampering(cart, product_factory):
    """Integration check: a typical web-view flow rejects a request that
    claims a cheaper price than the product actually advertises. Mirrors
    the legacy CartSecurityIntegrationTest.test_price_validation_in_web_flow."""
    product = product_factory(name="WebPrice", price="25.00")

    # Honest caller — succeeds.
    cart.add(product, Decimal("25.00"), validate_price=True)
    assert cart.count() == 1

    # Tampered caller — rejected.
    cart.clear()
    with pytest.raises(PriceMismatchError):
        cart.add(product, Decimal("15.00"), validate_price=True)
