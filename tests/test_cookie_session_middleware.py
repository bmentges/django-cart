"""End-to-end regression tests for the CookieSessionAdapter / Cart
integration via ``CartCookieMiddleware``.

P0-A from docs/ANALYSIS.md: before the middleware existed, setting
``CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"``
produced silent data loss — the adapter wrote cookies only to an
in-memory dict, so the browser never received ``Set-Cookie: CART-ID=…``
and every request created a fresh ``cart.models.Cart`` row.

These tests exercise the full request pipeline (URL → middleware →
view → Cart → CookieSessionAdapter) through Django's test ``Client``.
They complement ``tests/test_session_adapters.py`` which tests the
adapter in isolation, and ``tests/test_http_integration.py`` which
covers the default ``DjangoSessionAdapter``.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import Client

from cart.cart import CART_ID
from cart.models import Cart as CartModel


pytestmark = pytest.mark.django_db


@pytest.fixture
def cookie_adapter_settings(settings):
    """Wire CookieSessionAdapter + CartCookieMiddleware through settings.

    Replaces MIDDLEWARE rather than mutating the list — pytest-django's
    ``settings`` fixture watches the setting, not the list object, so
    in-place ``.append()`` wouldn't be restored at teardown.
    """
    settings.CARTS_SESSION_ADAPTER_CLASS = "cart.session.CookieSessionAdapter"
    settings.MIDDLEWARE = list(settings.MIDDLEWARE) + [
        "cart.middleware.CartCookieMiddleware",
    ]
    return settings


def test_first_request_sets_cart_id_cookie_on_response(cookie_adapter_settings):
    """With the middleware wired in, the first visit must emit a
    ``CART-ID`` cookie so the browser can echo it back next time."""
    client = Client()

    response = client.get("/cart/")

    assert response.status_code == 200
    assert CART_ID in response.cookies
    assert response.cookies[CART_ID].value  # non-empty
    # Exactly one cart row was created for this visitor.
    assert CartModel.objects.count() == 1


def test_cart_persists_across_sequential_requests_via_cookie(
    cookie_adapter_settings, product
):
    """Item added in request 1 must still be in the cart in request 2 —
    the end-to-end CookieSessionAdapter contract."""
    client = Client()

    client.post(f"/cart/add/{product.pk}/", {"quantity": 3})
    response = client.get("/cart/")

    import json

    payload = json.loads(response.content)
    assert payload["count"] == 3
    assert any(v["object_id"] == product.pk for v in payload["items"].values())
    # Still exactly one cart row — no abandoned duplicates.
    assert CartModel.objects.count() == 1


def test_sequential_requests_do_not_create_new_cart_rows(cookie_adapter_settings):
    """Three consecutive GETs must all see the same cart — the P0-A
    regression manifested as N rows for N requests."""
    client = Client()

    client.get("/cart/")
    client.get("/cart/")
    client.get("/cart/")

    assert CartModel.objects.count() == 1


def test_different_clients_get_isolated_cart_rows(cookie_adapter_settings, product):
    """Two separate cookie jars → two separate carts. Sanity check that
    the middleware doesn't leak state between visitors."""
    client_a = Client()
    client_b = Client()

    client_a.post(f"/cart/add/{product.pk}/", {"quantity": 2})
    client_b.post(f"/cart/add/{product.pk}/", {"quantity": 7})

    import json

    payload_a = json.loads(client_a.get("/cart/").content)
    payload_b = json.loads(client_b.get("/cart/").content)

    assert payload_a["count"] == 2
    assert payload_b["count"] == 7
    assert CartModel.objects.count() == 2


def test_cookie_value_matches_created_cart_id(cookie_adapter_settings):
    """The cookie value is the cart's integer primary key, serialised
    as a string — the adapter's contract with ``Cart.__init__``."""
    client = Client()

    response = client.get("/cart/")
    cart = CartModel.objects.get()

    assert response.cookies[CART_ID].value == str(cart.pk)


def test_middleware_is_noop_when_request_never_constructed_a_cart():
    """Pages that never touch ``Cart(request)`` must still get a normal
    response — the middleware's guard on ``request._cart_session``
    prevents a crash on the majority of non-cart routes.

    Unit-level rather than HTTP-level: driving this through Client +
    an admin route would couple the test to whichever default handler
    renders the template, which adds no coverage on top of asserting
    the guard directly.
    """
    from django.http import HttpResponse
    from django.test import RequestFactory

    from cart.middleware import CartCookieMiddleware

    sentinel = HttpResponse("ok")
    middleware = CartCookieMiddleware(get_response=lambda request: sentinel)
    request = RequestFactory().get("/whatever/")
    assert not hasattr(request, "_cart_session")

    response = middleware(request)

    assert response is sentinel
    assert CART_ID not in response.cookies


def test_cart_after_checkout_is_replaced_by_fresh_one(
    cookie_adapter_settings, product
):
    """Post-checkout, the next request's ``Cart(request)`` finds no
    ``checked_out=False`` cart for the cookie's id, so it creates a
    new one — and the middleware rotates the cookie to point at it."""
    client = Client()

    client.post(f"/cart/add/{product.pk}/", {"quantity": 1})
    client.post("/cart/checkout/")

    response = client.get("/cart/")
    import json

    payload = json.loads(response.content)
    assert payload["is_empty"] is True
    assert payload["checked_out"] is False
    # Two rows: the checked-out one + the fresh one.
    assert CartModel.objects.count() == 2
