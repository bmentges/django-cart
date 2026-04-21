"""Cart serialization: cart_serializable() output + from_serializable() round-trip.

As of v3.0.13 (P1-D fix), the payload keys are composites of the form
``"<content_type_id>:<object_id>"`` — previously the key was the bare
``object_id`` string, which collided when two product models shared a
primary key. Values carry ``content_type_id`` and ``object_id``
explicitly so consumers don't need to parse keys.

``from_serializable`` accepts both the new composite-key format and the
legacy plain-object_id format, provided the legacy payload carries
``content_type_id`` in each value (required for the P0-1 contract).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart


pytestmark = pytest.mark.django_db


def _composite_key(product) -> str:
    """Compute the ``cart_serializable`` key for a product instance."""
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(product._meta.model)
    return f"{ct.pk}:{product.pk}"


# --------------------------------------------------------------------------- #
# cart_serializable — structure and content
# --------------------------------------------------------------------------- #

def test_cart_serializable_structure(cart, product):
    cart.add(product, Decimal("15.00"), quantity=2)

    data = cart.cart_serializable()

    key = _composite_key(product)
    assert key in data
    assert data[key]["quantity"] == 2
    assert data[key]["unit_price"] == "15.00"
    assert data[key]["total_price"] == "30.00"
    assert data[key]["object_id"] == product.pk


def test_cart_serializable_on_empty_cart_returns_empty_dict(cart):
    assert cart.cart_serializable() == {}


def test_cart_serializable_preserves_unicode_product_names(cart, product_factory):
    product = product_factory(name="Produkt mit Ümläuten")
    cart.add(product, Decimal("10.00"), quantity=2)

    data = cart.cart_serializable()

    assert _composite_key(product) in data


def test_cart_serializable_serializes_multiple_items(cart, product_factory):
    p1 = product_factory(name="Multi1")
    p2 = product_factory(name="Multi2")
    cart.add(p1, Decimal("5.00"), quantity=1)
    cart.add(p2, Decimal("10.00"), quantity=3)

    data = cart.cart_serializable()

    assert len(data) == 2
    assert data[_composite_key(p1)]["total_price"] == "5.00"
    assert data[_composite_key(p2)]["total_price"] == "30.00"


def test_cart_serializable_value_types_are_int_and_string(cart, product):
    cart.add(product, Decimal("15.50"), quantity=2)

    data = cart.cart_serializable()

    item_data = next(iter(data.values()))
    assert isinstance(item_data["quantity"], int)
    assert isinstance(item_data["unit_price"], str)
    assert isinstance(item_data["total_price"], str)
    assert isinstance(item_data["content_type_id"], int)
    assert isinstance(item_data["object_id"], int)


# --------------------------------------------------------------------------- #
# from_serializable — updates existing items on same session
# --------------------------------------------------------------------------- #

def test_from_serializable_updates_existing_items_quantity_and_price(
    cart, product, rf_request
):
    cart.add(product, Decimal("5.00"), quantity=1)

    restored = Cart.from_serializable(
        rf_request,
        {_composite_key(product): {"quantity": 10, "unit_price": "15.00"}},
    )

    item = restored.cart.items.first()
    assert item.quantity == 10
    assert item.unit_price == Decimal("15.00")


def test_from_serializable_partial_update_keeps_unit_price(cart, product, rf_request):
    cart.add(product, Decimal("5.00"), quantity=1)

    restored = Cart.from_serializable(
        rf_request,
        {_composite_key(product): {"quantity": 5}},
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
        f"{ct.pk}:{product.pk}": {
            "content_type_id": ct.pk,
            "object_id": product.pk,
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
    assert data[_composite_key(product)]["content_type_id"] == ct.pk


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


# --------------------------------------------------------------------------- #
# P1-D: cross-content-type collisions (v3.0.13)
#
# Before the fix, two products with the same primary key but different
# content types collapsed to a single entry on serialize (dict key
# collision on `str(object_id)`) and updated the wrong item on restore
# (``Item.objects.filter(cart=..., object_id=...)`` matched either one).
# See docs/ANALYSIS.md §4.5.
# --------------------------------------------------------------------------- #

def test_cart_serializable_keeps_both_items_with_same_object_id_across_content_types(
    cart, rf_request
):
    from tests.test_app.models import FakeProduct, FakeProductNoPrice

    p1 = FakeProduct.objects.create(pk=100, name="Physical", price=Decimal("5.00"))
    p2 = FakeProductNoPrice.objects.create(pk=100, name="Digital")
    cart.add(p1, Decimal("5.00"), quantity=2)
    cart.add(p2, Decimal("7.00"), quantity=3)

    data = cart.cart_serializable()

    assert len(data) == 2
    quantities = sorted(entry["quantity"] for entry in data.values())
    assert quantities == [2, 3]


def test_from_serializable_update_does_not_cross_content_types(cart, rf_request):
    """Updating the FakeProductNoPrice item by (content_type_id, object_id)
    must not touch the FakeProduct item that shares its object_id."""
    from django.contrib.contenttypes.models import ContentType
    from tests.test_app.models import FakeProduct, FakeProductNoPrice

    p1 = FakeProduct.objects.create(pk=200, name="Physical", price=Decimal("5.00"))
    p2 = FakeProductNoPrice.objects.create(pk=200, name="Digital")
    cart.add(p1, Decimal("5.00"), quantity=2)
    cart.add(p2, Decimal("7.00"), quantity=3)

    ct_p2 = ContentType.objects.get_for_model(FakeProductNoPrice)
    payload_updating_p2_only = {
        f"{ct_p2.pk}:200": {
            "content_type_id": ct_p2.pk,
            "object_id": 200,
            "quantity": 9,
            "unit_price": "7.00",
        }
    }

    Cart.from_serializable(rf_request, payload_updating_p2_only)

    ct_p1 = ContentType.objects.get_for_model(FakeProduct)
    p1_item = cart.cart.items.get(content_type=ct_p1, object_id=200)
    p2_item = cart.cart.items.get(content_type=ct_p2, object_id=200)
    assert p1_item.quantity == 2  # unchanged
    assert p2_item.quantity == 9  # updated


def test_from_serializable_accepts_legacy_object_id_keys(rf_request, product):
    """Back-compat: a payload with a plain ``str(object_id)`` key still
    restores as long as the value carries ``content_type_id``. Consumers
    that stored payloads before v3.0.13 must keep working."""
    from django.contrib.contenttypes.models import ContentType
    from tests.test_app.models import FakeProduct

    ct = ContentType.objects.get_for_model(FakeProduct)
    legacy_payload = {
        str(product.pk): {
            "content_type_id": ct.pk,
            "quantity": 4,
            "unit_price": "12.00",
        }
    }

    cart = Cart.from_serializable(rf_request, legacy_payload)

    assert cart.count() == 4
    item = cart.cart.items.first()
    assert item.object_id == product.pk
    assert item.quantity == 4
    assert item.unit_price == Decimal("12.00")


# --------------------------------------------------------------------------- #
# P2: applied discount survives the round-trip
#
# Before v3.0.14, cart_serializable dropped the applied Discount on the
# floor — a "restore cart on a new device" flow lost the promo code the
# user had already applied. The payload now carries the code under a
# reserved ``__discount__`` key; from_serializable reattaches the
# matching Discount row. See docs/ANALYSIS.md §0 (P2 list).
# --------------------------------------------------------------------------- #

def test_cart_serializable_emits_applied_discount_code(cart, product):
    from cart.models import Discount, DiscountType

    Discount.objects.create(
        code="ROUND_TRIP",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    cart.add(product, Decimal("10.00"), quantity=1)
    cart.apply_discount("ROUND_TRIP")

    data = cart.cart_serializable()

    assert data["__discount__"] == {"code": "ROUND_TRIP"}


def test_cart_serializable_emits_null_discount_when_none_applied(cart, product):
    """The ``__discount__`` key must be absent (or explicitly null)
    when no discount is applied — tests must be able to distinguish
    'payload omitted the field' from 'no discount'."""
    cart.add(product, Decimal("10.00"), quantity=1)

    data = cart.cart_serializable()

    assert "__discount__" not in data


def test_round_trip_reattaches_applied_discount(cart, product):
    from django.test import RequestFactory
    from cart.models import Discount, DiscountType

    Discount.objects.create(
        code="ROUND_TRIP",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    cart.add(product, Decimal("10.00"), quantity=1)
    cart.apply_discount("ROUND_TRIP")
    payload = cart.cart_serializable()

    fresh_request = RequestFactory().get("/")
    fresh_request.session = {}
    restored = Cart.from_serializable(fresh_request, payload)

    assert restored.discount_code() == "ROUND_TRIP"


def test_round_trip_skips_silently_if_referenced_discount_deleted(cart, product):
    """If the Discount row has been removed between serialise and
    restore (expired cleanup, admin deletion), reattaching would raise.
    Silent skip is safer — the cart restores without a discount and
    the caller can decide whether to surface the miss."""
    from django.test import RequestFactory
    from cart.models import Discount, DiscountType

    Discount.objects.create(
        code="GONE",
        discount_type=DiscountType.PERCENT,
        value=Decimal("10.00"),
    )
    cart.add(product, Decimal("10.00"), quantity=1)
    cart.apply_discount("GONE")
    payload = cart.cart_serializable()

    Discount.objects.filter(code="GONE").delete()

    fresh_request = RequestFactory().get("/")
    fresh_request.session = {}
    restored = Cart.from_serializable(fresh_request, payload)

    assert restored.discount_code() is None
    assert restored.count() == 1  # items are still restored
