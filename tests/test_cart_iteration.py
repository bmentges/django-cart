"""Cart iteration: `for item in cart`, list(cart).

Includes two tests recovered from the shadowed `CartIterationTest` at
test_cart.py:579 — silently overridden by a second class of the same
name at line 1277 until P-1 Phase 5 dissolved the collision. See
docs/ROADMAP_2026_04.md §P1-5.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.django_db


def test_iter_yields_all_items(cart, product_factory):
    p1 = product_factory(name="Iter1")
    p2 = product_factory(name="Iter2")
    cart.add(p1, Decimal("5.00"), quantity=1)
    cart.add(p2, Decimal("10.00"), quantity=2)

    items = list(cart)

    assert len(items) == 2


def test_iter_yields_single_item_when_cart_has_one_product(cart, product):
    cart.add(product, Decimal("5.00"), quantity=1)

    items = list(cart)

    assert len(items) == 1
    assert items[0].quantity == 1


def test_iter_returns_unique_distinct_rows_per_product(cart, product_factory):
    p1 = product_factory(name="P1")
    p2 = product_factory(name="P2")
    cart.add(p1, Decimal("5.00"), quantity=2)
    cart.add(p2, Decimal("10.00"), quantity=3)

    items = list(cart)

    assert len(items) == 2
    assert {item.quantity for item in items} == {2, 3}


def test_len_of_cart_equals_count_method(cart, product):
    cart.add(product, Decimal("5.00"), quantity=7)

    assert len(cart) == cart.count()
