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
        cart.add_bulk(
            [
                {
                    "product": product_factory(name="BulkMax"),
                    "unit_price": Decimal("10.00"),
                    "quantity": 10,
                },
            ]
        )


# --------------------------------------------------------------------------- #
# Merge caps combined quantity at max (unlike add, which raises, merge
# silently clamps — the two paths are reached by cart/cart.py:373 and 381).
# --------------------------------------------------------------------------- #


def test_merge_caps_combined_quantity_when_both_carts_contain_the_same_product(
    cart, other_cart, product, settings
):
    """cart/cart.py:373 — existing item path."""
    settings.CART_MAX_QUANTITY_PER_ITEM = 10
    cart.add(product, Decimal("10.00"), quantity=6)
    other_cart.add(product, Decimal("10.00"), quantity=6)

    cart.merge(other_cart, strategy="add")

    assert cart.cart.items.first().quantity == 10


def test_merge_caps_new_item_quantity_when_source_cart_overshoots(
    cart, other_cart, product, settings
):
    """cart/cart.py:381 — new-item path (product not already in target).

    Populate the source cart first (without the cap), then apply the cap
    before merging. Otherwise the cap would block the setup-stage add.
    """
    other_cart.add(product, Decimal("10.00"), quantity=20)
    settings.CART_MAX_QUANTITY_PER_ITEM = 5

    cart.merge(other_cart, strategy="add")

    assert cart.cart.items.first().quantity == 5
