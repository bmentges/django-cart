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
# P0-1: from_serializable restores items on a fresh cart (fixed in v3.0.11)
# --------------------------------------------------------------------------- #

def test_from_serializable_is_not_a_silent_noop_on_fresh_cart(rf_request, product):
    """Calling from_serializable with items on a brand-new cart must
    populate it (P0-1 fix — pre-v3.0.11 this was a silent no-op)."""
    from django.contrib.contenttypes.models import ContentType
    from tests.test_app.models import FakeProduct

    ct = ContentType.objects.get_for_model(FakeProduct)
    data = {
        str(product.pk): {
            "content_type_id": ct.pk,
            "quantity": 3,
            "unit_price": "15.00",
        }
    }

    cart = Cart.from_serializable(rf_request, data)

    assert cart.count() == 3
    item = cart.cart.items.first()
    assert item.quantity == 3
    assert item.unit_price == Decimal("15.00")
    assert item.object_id == product.pk


def test_cart_serializable_includes_content_type_id(cart, product):
    """The v3.0.11 output format includes content_type_id so payloads
    can be fed to from_serializable on a fresh cart."""
    from django.contrib.contenttypes.models import ContentType
    from tests.test_app.models import FakeProduct

    cart.add(product, Decimal("10.00"), quantity=1)

    data = cart.cart_serializable()

    ct = ContentType.objects.get_for_model(FakeProduct)
    assert data[str(product.pk)]["content_type_id"] == ct.pk


def test_cart_serializable_and_from_serializable_round_trip(cart, product):
    """Serialising a populated cart and restoring into a fresh session
    reproduces the original cart state."""
    from django.test import RequestFactory

    cart.add(product, Decimal("15.00"), quantity=3)
    payload = cart.cart_serializable()

    fresh_request = RequestFactory().get("/")
    fresh_request.session = {}
    restored = Cart.from_serializable(fresh_request, payload)

    assert restored.count() == 3
    item = restored.cart.items.first()
    assert item.quantity == 3
    assert item.unit_price == Decimal("15.00")
    assert item.object_id == product.pk


def test_from_serializable_raises_clear_error_on_legacy_payload(rf_request, product):
    """Pre-v3.0.11 payloads (without content_type_id) cannot restore new
    items; the method raises a clear ValueError instead of silently
    no-op'ing, which was the P0-1 bug."""
    legacy_payload = {
        str(product.pk): {"quantity": 3, "unit_price": "15.00"},  # no content_type_id
    }

    with pytest.raises(ValueError, match="content_type_id"):
        Cart.from_serializable(rf_request, legacy_payload)
