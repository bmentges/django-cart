"""Transaction-level atomicity of Cart.add / Cart.update.

Uses ``pytest.mark.django_db(transaction=True)`` — equivalent to
``TransactionTestCase`` — so ``transaction.atomic`` blocks actually
commit or roll back against real DB state rather than savepoints of a
wrapping test transaction.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart, InvalidQuantity, ItemDoesNotExist


pytestmark = pytest.mark.django_db(transaction=True)


def test_add_persists_on_success(rf_request, product):
    cart = Cart(rf_request)

    item = cart.add(product, Decimal("5.00"), quantity=1)

    assert cart.count() == 1
    item.refresh_from_db()
    assert item.quantity == 1


def test_add_twice_accumulates_quantity_atomically(rf_request, product):
    cart = Cart(rf_request)
    cart.add(product, Decimal("5.00"), quantity=1)
    cart.add(product, Decimal("5.00"), quantity=2)

    assert cart.cart.items.first().quantity == 3


def test_update_persists_on_success(rf_request, product):
    cart = Cart(rf_request)
    cart.add(product, Decimal("5.00"), quantity=1)

    cart.update(product, quantity=10, unit_price=Decimal("15.00"))

    item = cart.cart.items.first()
    assert item.quantity == 10
    assert item.unit_price == Decimal("15.00")


def test_update_to_zero_removes_the_item_atomically(rf_request, product):
    cart = Cart(rf_request)
    cart.add(product, Decimal("5.00"), quantity=5)

    cart.update(product, quantity=0)

    assert cart.is_empty() is True


def test_add_with_invalid_quantity_leaves_cart_unchanged(rf_request, product):
    cart = Cart(rf_request)
    cart.add(product, Decimal("5.00"), quantity=1)

    with pytest.raises(InvalidQuantity):
        cart.add(product, Decimal("5.00"), quantity=0)

    assert cart.cart.items.first().quantity == 1


def test_update_on_unknown_product_leaves_cart_unchanged(rf_request, product, product_factory):
    cart = Cart(rf_request)
    cart.add(product, Decimal("5.00"), quantity=1)
    ghost = product_factory(name="Ghost")

    with pytest.raises(ItemDoesNotExist):
        cart.update(ghost, quantity=5)

    assert cart.cart.items.first().quantity == 1
