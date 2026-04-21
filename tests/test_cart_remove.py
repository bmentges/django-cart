"""Cart.remove behaviour."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import ItemDoesNotExist

pytestmark = pytest.mark.django_db


def test_remove_existing_product_empties_the_cart(cart, product):
    cart.add(product, Decimal("5.00"), quantity=1)

    cart.remove(product)

    assert cart.is_empty() is True


def test_remove_unknown_product_raises(cart, product_factory):
    ghost = product_factory(name="Ghost")

    with pytest.raises(ItemDoesNotExist):
        cart.remove(ghost)


def test_remove_one_product_preserves_others(cart, product_factory):
    p1 = product_factory(name="First", price="5.00")
    p2 = product_factory(name="Second", price="3.00")
    cart.add(p1, Decimal("5.00"), quantity=1)
    cart.add(p2, Decimal("3.00"), quantity=4)

    cart.remove(p1)

    assert cart.unique_count() == 1
    assert cart.count() == 4
