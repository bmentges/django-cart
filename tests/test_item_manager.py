"""ItemManager behaviour: the `product=` kwarg shortcut for filter/get."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError, ObjectDoesNotExist

from cart.models import Cart as CartModel
from cart.models import Item
from tests.test_app.models import FakeProduct

pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_with_widget(product):
    cart = CartModel.objects.create()
    ct = ContentType.objects.get_for_model(FakeProduct)
    item = Item.objects.create(
        cart=cart,
        content_type=ct,
        object_id=product.pk,
        unit_price=Decimal("5.00"),
        quantity=1,
    )
    return cart, item


def test_filter_by_product_returns_matching_items(cart_with_widget, product):
    cart, item = cart_with_widget

    qs = Item.objects.filter(cart=cart, product=product)

    assert qs.count() == 1
    assert qs.first().pk == item.pk


def test_get_by_product_returns_the_item(cart_with_widget, product):
    cart, item = cart_with_widget

    assert Item.objects.get(cart=cart, product=product).pk == item.pk


def test_filter_by_unknown_product_returns_empty_queryset(
    cart_with_widget, product_factory
):
    cart, _ = cart_with_widget
    other = product_factory(name="Unknown")

    assert Item.objects.filter(cart=cart, product=other).count() == 0


def test_get_by_unknown_product_raises(cart_with_widget, product_factory):
    other = product_factory(name="Unknown")

    with pytest.raises(ObjectDoesNotExist):
        Item.objects.get(product=other)


def test_filter_with_product_and_other_kwargs(cart_with_widget, product):
    assert Item.objects.filter(product=product, quantity=1).count() == 1


def test_filter_with_nonexistent_object_id_returns_empty(db):
    ct = ContentType.objects.get_for_model(FakeProduct)

    assert Item.objects.filter(content_type=ct, object_id=99999).count() == 0


def test_get_with_unknown_model_field_raises_fielderror(db):
    with pytest.raises(FieldError):
        Item.objects.get(nonexistent_field="value")
