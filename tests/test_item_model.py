"""Item Django model: total_price, product property, validation, uniqueness."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from cart.models import Cart as CartModel, Item
from tests.test_app.models import FakeProduct


pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Core behaviour
# --------------------------------------------------------------------------- #

@pytest.fixture
def cart_with_item(product):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    item = Item.objects.create(
        cart=cart,
        content_type=ct,
        object_id=product.pk,
        unit_price=Decimal("10.00"),
        quantity=3,
    )
    return cart, item


def test_total_price_is_quantity_times_unit_price(cart_with_item):
    _, item = cart_with_item

    assert item.total_price == Decimal("30.00")


def test_item_str_includes_quantity(cart_with_item):
    _, item = cart_with_item

    assert "3" in str(item)


def test_unique_together_rejects_duplicate_on_same_cart(cart_with_item, product):
    cart, _ = cart_with_item
    ct = ContentType.objects.get_for_model(FakeProduct)

    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        Item.objects.create(
            cart=cart,
            content_type=ct,
            object_id=product.pk,
            unit_price=Decimal("5.00"),
            quantity=1,
        )


# --------------------------------------------------------------------------- #
# Item.product property
# --------------------------------------------------------------------------- #

def test_product_property_returns_the_associated_product(cart_with_item, product):
    _, item = cart_with_item

    assert item.product.pk == product.pk
    assert item.product.name == product.name


def test_product_property_second_access_does_not_hit_db(
    cart_with_item, django_assert_num_queries
):
    _, item = cart_with_item

    first = item.product  # noqa: F841 — priming access

    with django_assert_num_queries(0):
        second = item.product

    assert second is first


def test_product_cache_is_not_shared_across_item_instances(product_factory):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    p1 = product_factory(name="Prod1")
    p2 = product_factory(name="Prod2")
    item1 = Item.objects.create(
        cart=cart, content_type=ct, object_id=p1.pk,
        unit_price=Decimal("10.00"), quantity=1,
    )
    item2 = Item.objects.create(
        cart=cart, content_type=ct, object_id=p2.pk,
        unit_price=Decimal("20.00"), quantity=1,
    )

    assert item1.product.pk == p1.pk
    assert item2.product.pk == p2.pk


def test_product_setter_updates_content_type_and_object_id(cart_with_item, product_factory):
    _, item = cart_with_item
    new_product = product_factory(name="Replacement")

    item.product = new_product

    assert item.object_id == new_product.pk
    assert item.content_type == ContentType.objects.get_for_model(FakeProduct)


# --------------------------------------------------------------------------- #
# unit_price validation
# --------------------------------------------------------------------------- #

def test_negative_unit_price_fails_validation():
    cart = CartModel.objects.create()
    item = Item(cart=cart, quantity=1, unit_price=Decimal("-1.00"))

    with pytest.raises(ValidationError) as exc_info:
        item.full_clean()

    assert "unit_price" in exc_info.value.message_dict


def test_zero_unit_price_passes_validation(product):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    item = Item(
        cart=cart,
        content_type=ct,
        object_id=product.pk,
        quantity=1,
        unit_price=Decimal("0.00"),
    )

    item.full_clean()  # must not raise


def test_positive_unit_price_passes_validation(product):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    item = Item.objects.create(
        cart=cart,
        content_type=ct,
        object_id=product.pk,
        unit_price=Decimal("99.99"),
        quantity=1,
    )

    item.full_clean()  # must not raise


# --------------------------------------------------------------------------- #
# Cross-cart uniqueness
# --------------------------------------------------------------------------- #

def test_same_product_in_two_different_carts_is_allowed(product):
    cart1 = CartModel.objects.create()
    cart2 = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)

    Item.objects.create(
        cart=cart1, content_type=ct, object_id=product.pk,
        unit_price=Decimal("5.00"), quantity=1,
    )
    Item.objects.create(
        cart=cart2, content_type=ct, object_id=product.pk,
        unit_price=Decimal("5.00"), quantity=2,
    )

    assert Item.objects.filter(object_id=product.pk).count() == 2


def test_two_different_products_in_same_cart_is_allowed(product_factory):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    p1 = product_factory(name="A")
    p2 = product_factory(name="B")

    Item.objects.create(
        cart=cart, content_type=ct, object_id=p1.pk,
        unit_price=Decimal("5.00"), quantity=1,
    )
    Item.objects.create(
        cart=cart, content_type=ct, object_id=p2.pk,
        unit_price=Decimal("10.00"), quantity=1,
    )

    assert cart.items.count() == 2
