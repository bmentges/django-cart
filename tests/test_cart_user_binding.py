"""Cart.bind_to_user + Cart.get_user_carts: cart-to-user persistence."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cart.cart import Cart


pytestmark = pytest.mark.django_db


def test_bind_to_user_attaches_user_to_cart(cart, django_user_model):
    user = django_user_model.objects.create_user(
        username="bindtest",
        email="bind@example.com",
        password="pass123",
    )

    cart.bind_to_user(user)

    cart.cart.refresh_from_db()
    assert cart.cart.user == user


def test_get_user_carts_returns_carts_for_user(cart, product, django_user_model):
    user = django_user_model.objects.create_user(
        username="gucuser",
        email="guc@example.com",
        password="pass123",
    )
    cart.bind_to_user(user)
    cart.add(product, Decimal("10.00"), quantity=1)

    carts = Cart.get_user_carts(user)

    assert carts.count() == 1


def test_unbound_cart_has_no_user(cart):
    assert cart.cart.user is None


def test_user_can_have_multiple_carts(cart, other_cart, product_factory, django_user_model):
    user = django_user_model.objects.create_user(
        username="multiuser",
        email="multi@example.com",
        password="pass123",
    )
    cart.bind_to_user(user)
    cart.add(product_factory(name="A"), Decimal("10.00"), quantity=1)
    other_cart.bind_to_user(user)
    other_cart.add(product_factory(name="B"), Decimal("20.00"), quantity=2)

    carts = Cart.get_user_carts(user)

    assert carts.count() == 2
