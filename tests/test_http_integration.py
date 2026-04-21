"""HTTP-level integration tests via Django's test client.

Unlike the (removed) legacy tests/test_integration.py — which used
``MagicMock`` requests and tested at the Cart-class level despite its
name — these tests exercise the full request pipeline: URL routing,
session middleware, view dispatch, and Cart construction from a real
request. Failures here surface wiring issues that unit-level tests
can't: middleware misconfiguration, session adapter regressions,
URL reverse bugs, CSRF surprises.

The minimal views under test live at tests/test_app/views.py and
return JSON so assertions stay terse. Template-render coverage
(`{% load cart_tags %}` against real templates) is owned by P0-5
and arrives with that fix.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import Client

from cart.cart import CART_ID

pytestmark = pytest.mark.django_db


def _json(response):
    return json.loads(response.content)


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #


def test_get_cart_detail_returns_empty_cart_on_first_visit(client):
    response = client.get("/cart/")

    assert response.status_code == 200
    payload = _json(response)
    assert payload["is_empty"] is True
    assert payload["count"] == 0
    assert Decimal(payload["summary"]) == Decimal("0.00")


def test_post_cart_add_puts_item_in_cart(client, product):
    response = client.post(
        f"/cart/add/{product.pk}/",
        {"quantity": 2},
    )

    assert response.status_code == 200
    payload = _json(response)
    assert payload["count"] == 2
    assert Decimal(payload["summary"]) == Decimal("20.00")
    assert any(v["object_id"] == product.pk for v in payload["items"].values())


def test_post_cart_remove_empties_the_cart(client, product):
    client.post(f"/cart/add/{product.pk}/", {"quantity": 1})

    response = client.post(f"/cart/remove/{product.pk}/")

    assert response.status_code == 200
    payload = _json(response)
    assert payload["is_empty"] is True


def test_post_cart_update_changes_quantity(client, product):
    client.post(f"/cart/add/{product.pk}/", {"quantity": 1})

    response = client.post(f"/cart/update/{product.pk}/", {"quantity": 5})

    assert response.status_code == 200
    payload = _json(response)
    assert payload["count"] == 5


def test_post_cart_checkout_marks_cart_checked_out(client, product):
    client.post(f"/cart/add/{product.pk}/", {"quantity": 1})

    response = client.post("/cart/checkout/")

    assert response.status_code == 200
    payload = _json(response)
    assert payload["checked_out"] is True


# --------------------------------------------------------------------------- #
# Session persistence (the real reason for HTTP integration tests)
# --------------------------------------------------------------------------- #


def test_cart_persists_across_sequential_requests(client, product):
    client.post(f"/cart/add/{product.pk}/", {"quantity": 3})

    response = client.get("/cart/")

    payload = _json(response)
    assert payload["count"] == 3
    assert any(v["object_id"] == product.pk for v in payload["items"].values())


def test_different_clients_have_isolated_carts(db, product):
    client_a = Client()
    client_b = Client()

    client_a.post(f"/cart/add/{product.pk}/", {"quantity": 2})
    client_b.post(f"/cart/add/{product.pk}/", {"quantity": 7})

    assert _json(client_a.get("/cart/"))["count"] == 2
    assert _json(client_b.get("/cart/"))["count"] == 7


def test_cart_after_checkout_is_replaced_by_fresh_one(client, product):
    client.post(f"/cart/add/{product.pk}/", {"quantity": 1})
    client.post("/cart/checkout/")

    response = client.get("/cart/")

    payload = _json(response)
    assert payload["is_empty"] is True
    assert payload["checked_out"] is False


def test_session_stores_cart_id_after_first_visit(client):
    assert CART_ID not in client.session

    client.get("/cart/")

    assert CART_ID in client.session


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #


def test_cart_add_for_unknown_product_returns_404(db, client):
    response = client.post("/cart/add/99999/", {"quantity": 1})

    assert response.status_code == 404


def test_cart_add_with_invalid_quantity_returns_400(client, product):
    response = client.post(f"/cart/add/{product.pk}/", {"quantity": 0})

    assert response.status_code == 400
    assert "error" in _json(response)


def test_cart_remove_for_item_not_in_cart_returns_404(client, product):
    response = client.post(f"/cart/remove/{product.pk}/")

    assert response.status_code == 404


def test_get_on_post_only_endpoint_returns_405(client, product):
    response = client.get(f"/cart/add/{product.pk}/")

    assert response.status_code == 405


def test_post_on_get_only_endpoint_returns_405(client):
    response = client.post("/cart/")

    assert response.status_code == 405
