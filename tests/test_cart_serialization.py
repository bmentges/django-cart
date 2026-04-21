"""Cart serialization: cart_serializable() output + from_serializable() round-trip.

NOTE: `from_serializable` on a fresh cart silently produces an empty cart
today (P0-1). The behaviour is exercised here with a PRE-POPULATED cart,
mirroring what the legacy tests did — the fresh-cart bug is owned by
P0-1 and will get an @xfail regression test in Phase 7.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart


pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# cart_serializable — structure and content
# --------------------------------------------------------------------------- #

def test_cart_serializable_structure(cart, product):
    cart.add(product, Decimal("15.00"), quantity=2)

    data = cart.cart_serializable()

    key = str(product.pk)
    assert key in data
    assert data[key]["quantity"] == 2
    assert data[key]["unit_price"] == "15.00"
    assert data[key]["total_price"] == "30.00"


def test_cart_serializable_on_empty_cart_returns_empty_dict(cart):
    assert cart.cart_serializable() == {}


def test_cart_serializable_preserves_unicode_product_names(cart, product_factory):
    product = product_factory(name="Produkt mit Ümläuten")
    cart.add(product, Decimal("10.00"), quantity=2)

    data = cart.cart_serializable()

    assert str(product.pk) in data


def test_cart_serializable_serializes_multiple_items(cart, product_factory):
    p1 = product_factory(name="Multi1")
    p2 = product_factory(name="Multi2")
    cart.add(p1, Decimal("5.00"), quantity=1)
    cart.add(p2, Decimal("10.00"), quantity=3)

    data = cart.cart_serializable()

    assert len(data) == 2
    assert data[str(p1.pk)]["total_price"] == "5.00"
    assert data[str(p2.pk)]["total_price"] == "30.00"


def test_cart_serializable_value_types_are_int_and_string(cart, product):
    cart.add(product, Decimal("15.50"), quantity=2)

    data = cart.cart_serializable()

    item_data = next(iter(data.values()))
    assert isinstance(item_data["quantity"], int)
    assert isinstance(item_data["unit_price"], str)
    assert isinstance(item_data["total_price"], str)


# --------------------------------------------------------------------------- #
# from_serializable — updates existing items on same session
# --------------------------------------------------------------------------- #

def test_from_serializable_updates_existing_items_quantity_and_price(cart, product, rf_request):
    cart.add(product, Decimal("5.00"), quantity=1)

    restored = Cart.from_serializable(
        rf_request,
        {str(product.pk): {"quantity": 10, "unit_price": "15.00"}},
    )

    item = restored.cart.items.first()
    assert item.quantity == 10
    assert item.unit_price == Decimal("15.00")


def test_from_serializable_partial_update_keeps_unit_price(cart, product, rf_request):
    cart.add(product, Decimal("5.00"), quantity=1)

    restored = Cart.from_serializable(
        rf_request,
        {str(product.pk): {"quantity": 5}},
    )

    item = restored.cart.items.first()
    assert item.quantity == 5
    assert item.unit_price == Decimal("5.00")


def test_from_serializable_with_empty_data_leaves_cart_untouched(cart, product, rf_request):
    cart.add(product, Decimal("5.00"), quantity=1)

    restored = Cart.from_serializable(rf_request, {})

    assert restored.count() == 1


# --------------------------------------------------------------------------- #
# P0-1 regression (xfail removed in v3.0.11 — this commit's purpose)
# --------------------------------------------------------------------------- #

def test_from_serializable_is_not_a_silent_noop_on_fresh_cart(rf_request, product):
    """Calling from_serializable with items on a brand-new cart should
    leave the cart populated. Today it silently returns an empty cart."""
    data = {str(product.pk): {"quantity": 3, "unit_price": "15.00"}}

    cart = Cart.from_serializable(rf_request, data)

    assert not cart.is_empty()
