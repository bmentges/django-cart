"""Cart.update behaviour."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import InvalidQuantity, ItemDoesNotExist


pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_with_product(cart, product):
    cart.add(product, Decimal("5.00"), quantity=3)
    return cart


def test_update_changes_the_quantity(cart_with_product, product):
    cart_with_product.update(product, quantity=10)

    assert cart_with_product.count() == 10


def test_update_with_quantity_zero_removes_the_item(cart_with_product, product):
    cart_with_product.update(product, quantity=0)

    assert cart_with_product.is_empty() is True


def test_update_can_change_unit_price(cart_with_product, product):
    cart_with_product.update(product, quantity=2, unit_price=Decimal("9.99"))

    assert cart_with_product.cart.items.first().unit_price == Decimal("9.99")


def test_update_on_unknown_product_raises(cart_with_product, product_factory):
    ghost = product_factory(name="Ghost")

    with pytest.raises(ItemDoesNotExist):
        cart_with_product.update(ghost, quantity=1)


def test_update_with_negative_quantity_raises(cart_with_product, product):
    with pytest.raises(InvalidQuantity):
        cart_with_product.update(product, quantity=-1)
