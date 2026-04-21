"""Cart.add behaviour."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import InvalidQuantity

pytestmark = pytest.mark.django_db


def test_add_new_product_stores_the_quantity(cart, product):
    cart.add(product, Decimal("5.00"), quantity=2)

    assert cart.count() == 2


def test_add_existing_product_accumulates_quantity(cart, product):
    cart.add(product, Decimal("5.00"), quantity=2)
    cart.add(product, Decimal("5.00"), quantity=3)

    assert cart.count() == 5


def test_add_updates_unit_price_to_latest_call(cart, product):
    cart.add(product, Decimal("5.00"), quantity=1)
    cart.add(product, Decimal("7.50"), quantity=1)

    assert cart.cart.items.first().unit_price == Decimal("7.50")


def test_add_defaults_to_quantity_of_one(cart, product):
    cart.add(product, Decimal("5.00"))

    assert cart.count() == 1


@pytest.mark.parametrize("invalid_quantity", [0, -1, -100])
def test_add_with_non_positive_quantity_raises(cart, product, invalid_quantity):
    with pytest.raises(InvalidQuantity):
        cart.add(product, Decimal("5.00"), quantity=invalid_quantity)
