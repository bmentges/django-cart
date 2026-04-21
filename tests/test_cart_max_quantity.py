"""CART_MAX_QUANTITY_PER_ITEM setting enforcement across add / update / add_bulk."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import InvalidQuantity


pytestmark = pytest.mark.django_db


def test_add_above_max_raises(cart, product, settings):
    settings.CART_MAX_QUANTITY_PER_ITEM = 10

    with pytest.raises(InvalidQuantity):
        cart.add(product, Decimal("10.00"), quantity=11)


def test_add_at_exactly_max_succeeds(cart, product, settings):
    settings.CART_MAX_QUANTITY_PER_ITEM = 10

    cart.add(product, Decimal("10.00"), quantity=10)

    assert cart.count() == 10


def test_update_above_max_raises(cart, product, settings):
    settings.CART_MAX_QUANTITY_PER_ITEM = 100
    cart.add(product, Decimal("10.00"), quantity=50)

    with pytest.raises(InvalidQuantity):
        cart.update(product, quantity=101)


def test_add_that_pushes_existing_item_above_max_raises(cart, product, settings):
    settings.CART_MAX_QUANTITY_PER_ITEM = 10
    cart.add(product, Decimal("10.00"), quantity=8)

    with pytest.raises(InvalidQuantity):
        cart.add(product, Decimal("10.00"), quantity=5)


def test_without_max_setting_any_quantity_is_accepted(cart, product):
    cart.add(product, Decimal("10.00"), quantity=1000)

    assert cart.count() == 1000


def test_add_bulk_respects_max(cart, product_factory, settings):
    settings.CART_MAX_QUANTITY_PER_ITEM = 5

    with pytest.raises(InvalidQuantity):
        cart.add_bulk([
            {"product": product_factory(name="BulkMax"), "unit_price": Decimal("10.00"), "quantity": 10},
        ])
