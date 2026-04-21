"""Cart Django model: field defaults, __str__, ordering."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from cart.models import Cart as CartModel

pytestmark = pytest.mark.django_db


def test_cart_default_checked_out_is_false():
    cart = CartModel.objects.create()

    assert cart.checked_out is False


def test_cart_creation_date_defaults_to_now():
    before = timezone.now()
    cart = CartModel.objects.create()
    after = timezone.now()

    assert before <= cart.creation_date <= after


def test_cart_queryset_is_ordered_newest_first():
    old = CartModel.objects.create(creation_date=timezone.now() - timedelta(days=5))
    new = CartModel.objects.create(creation_date=timezone.now())

    carts = list(CartModel.objects.all())

    assert carts[0].pk == new.pk
    assert carts[1].pk == old.pk


def test_cart_str_includes_pk_and_item_count():
    """Single consolidated str test replacing three redundant ones —
    `Cart #<pk> (<N> items)` format."""
    cart = CartModel.objects.create()

    rendered = str(cart)

    assert f"#{cart.pk}" in rendered
    assert "0 items" in rendered
