"""Behavioural tests that django-cart runs under a swapped ``AUTH_USER_MODEL``.

Must be run with ``tests.settings_custom_user`` — that settings module
swaps ``AUTH_USER_MODEL`` to a ``custom_user_app.CustomUser`` defined
alongside these tests. Before the P1-B fix, loading the Django app
registry under this settings module fails at system-check time with::

    cart.Cart has a relation with model auth.User, which has been
    swapped out.

That failure blocks both ``makemigrations`` and the pytest invocation
itself — exactly the experience a downstream project with a custom
user model sees when they try to install django-cart on master.

Invoke as::

    pytest --ds=tests.settings_custom_user tests/test_cart_custom_user.py

CI runs this as a separate step; the primary pytest invocation keeps
the default ``auth.User`` setup because ``AUTH_USER_MODEL`` cannot be
swapped mid-process.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from cart.cart import Cart
from cart.models import Cart as CartModel

pytestmark = pytest.mark.django_db


def test_user_model_really_is_the_custom_one():
    """Fixture sanity — confirms the dedicated settings module is
    actually in use. If someone runs this file under the default
    settings by accident, the rest of the suite's claims are
    meaningless."""
    user_model = get_user_model()

    assert user_model.__name__ == "CustomUser"
    assert user_model._meta.app_label == "custom_user_app"


def test_cart_user_fk_resolves_to_the_custom_user_model():
    field = CartModel._meta.get_field("user")

    assert field.remote_field.model is get_user_model()


def test_bind_to_user_writes_custom_user_pk():
    user_model = get_user_model()
    user = user_model.objects.create_user(username="alice", password="pw")
    request = RequestFactory().get("/")
    request.session = {}
    cart = Cart(request)

    cart.bind_to_user(user)

    cart.cart.refresh_from_db()
    assert cart.cart.user_id == user.pk
    assert cart.cart.user == user


def test_get_user_carts_queries_by_custom_user_model():
    user_model = get_user_model()
    user = user_model.objects.create_user(username="bob", password="pw")
    request = RequestFactory().get("/")
    request.session = {}
    cart = Cart(request)
    cart.bind_to_user(user)

    carts = Cart.get_user_carts(user)

    assert list(carts) == [cart.cart]
