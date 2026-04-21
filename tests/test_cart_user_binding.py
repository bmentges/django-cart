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


def test_user_can_have_multiple_carts(
    cart, other_cart, product_factory, django_user_model
):
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


# --------------------------------------------------------------------------- #
# get_active_user_carts — P3: safer default for login-flow merge
# --------------------------------------------------------------------------- #


def test_get_active_user_carts_excludes_checked_out_carts(
    cart, other_cart, product, django_user_model
):
    """P3 regression: ``Cart.get_user_carts`` returns every cart
    associated with a user — including already-checked-out ones.
    The README's login-flow example filters on ``.filter(checked_out=False)``
    on top, but downstream callers that forget the filter will merge
    an already-checked-out cart (a past order) into the fresh guest
    cart, resurrecting old items. ``get_active_user_carts`` hard-codes
    the filter so the safer path is the obvious one."""
    user = django_user_model.objects.create_user(
        username="mergeuser",
        email="m@example.com",
        password="p",
    )
    cart.bind_to_user(user)
    cart.add(product, Decimal("10.00"))
    cart.checkout()

    other_cart.bind_to_user(user)
    other_cart.add(product, Decimal("10.00"))

    active = Cart.get_active_user_carts(user)

    assert active.count() == 1
    assert active.first().pk == other_cart.cart.pk


def test_get_user_carts_still_includes_checked_out_carts_for_back_compat(
    cart, product, django_user_model
):
    """get_user_carts() is unchanged — callers that genuinely want
    all carts (e.g. building an order-history view) keep working."""
    user = django_user_model.objects.create_user(
        username="historyuser",
        email="h@example.com",
        password="p",
    )
    cart.bind_to_user(user)
    cart.add(product, Decimal("10.00"))
    cart.checkout()

    all_carts = Cart.get_user_carts(user)

    assert all_carts.count() == 1
