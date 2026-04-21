"""Cart.add_bulk: multi-item add in a single transaction."""
from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


def test_add_bulk_creates_all_items(cart, product_factory):
    items = [
        {"product": product_factory(name="Bulk1"), "unit_price": Decimal("10.00"), "quantity": 1},
        {"product": product_factory(name="Bulk2"), "unit_price": Decimal("20.00"), "quantity": 2},
        {"product": product_factory(name="Bulk3"), "unit_price": Decimal("30.00"), "quantity": 3},
    ]

    result = cart.add_bulk(items)

    assert len(result) == 3
    assert cart.count() == 6
    assert cart.summary() == Decimal("140.00")


def test_add_bulk_replaces_existing_item_state(cart, product):
    cart.add(product, Decimal("10.00"), quantity=1)

    cart.add_bulk([
        {"product": product, "unit_price": Decimal("15.00"), "quantity": 5},
    ])

    assert cart.count() == 5
    assert cart.cart.items.first().unit_price == Decimal("15.00")


def test_add_bulk_with_empty_list_is_a_noop(cart):
    result = cart.add_bulk([])

    assert result == []
    assert cart.is_empty() is True


def test_add_bulk_returns_list_of_item_instances(cart, product_factory):
    result = cart.add_bulk([
        {"product": product_factory(name="Return"), "unit_price": Decimal("10.00"), "quantity": 2},
    ])

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].quantity == 2
